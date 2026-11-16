# -*- coding: utf-8 -*-
"""DELEGACAO (27/10/2026): so o JARVIS fala com o Dono. Quando o Dono quer saber algo, o Jarvis vai ate o agente do assunto, PERGUNTA (barramento: pedido),
o agente responde com os dados que realmente tem (barramento: resposta) e o Jarvis repassa. A tela do escritorio mostra isso (o Jarvis anda ate a sala do agente).
Cada agente tem seu bloco de dados (funcoes abaixo, so codigo e arquivos locais: nada de IA para consultar). Agentes que lidam com dinheiro, agenda, saude ou
familia sao 'locais': a resposta e montada SEM IA online. Nenhum agente manda mensagem ao Dono sozinho: avisos passam por `via_jarvis`."""
import json
import re
import subprocess
import threading
from datetime import date, datetime, timedelta

from .store import DATA

PERGUNTA = re.compile(r"(?i)\?|\b(?:como\s+(?:est[aá]|anda|t[aá]|vai|foi)|quanto|quantos?|quantas?|qual|quais|quando|onde|quem|o\s+que|situa[cç][aã]o|status|relat[oó]rio|resumo|andamento|"
                      r"progress[aã]o|lista\s+de\s+exames|prazos?\b|me\s+(?:fala|conta|diz|diga|mostra|passa)|tem\s+algum|j[aá]\s+(?:bati|chegou|caiu|entrou)|falta)\b")
ACAO = re.compile(r"(?i)^\s*(?:jarvis\W*)?(?:manda|mande|envia|envie|avisa|avise|abre|abra|cria|crie|liga|ligue|desliga|desligue|publica|publique|edita|edite|apaga|apague|"
                  r"gera|gere|toca|toque|pausa|pause|coloca|ponha|poe|p[oõ]e|marca|marque|anota|anote|lembra|lembre|responde|responda)\b")
# opiniao/impressao ('o que voce acha da Layla?') nao e fato: o Jarvis opina em cima dos fatos do banco e, sem nenhum, escala (outros agentes -> conselho)
OPINIAO = re.compile(r"(?i)\b(?:o\s+que\s+(?:voc[eê]|vc|tu)\s+(?:acha|pensa|sente)|(?:voc[eê]|vc)\s+(?:acha|gosta|curte|confia)|sua\s+opini[aã]o|opini[aã]o\s+sobre|acha\s+d[eao]s?\b|vale\s+a\s+pena)")
ENTIDADE = re.compile(r"\b[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÀ-ÿ]{2,}")
NAO_ENTIDADE = {"jarvis", "dono", "voce", "você", "como", "qual", "quem", "quando", "onde"}
MODO = threading.local()    # MODO.opiniao = _fatos devolve mais texto por fato (700 em vez de 240) e so o que casa com a pergunta


def eh_opiniao(texto):
    t = (texto or "").strip()
    return bool(t) and len(t) < 400 and not t.startswith("/") and bool(OPINIAO.search(t)) and not ACAO.match(t)


def _entidade(texto):
    """Nome proprio citado na pergunta (a 1a palavra da frase nao conta): 'o que acha da Layla?' -> 'Layla'. None se nao houver."""
    for m in ENTIDADE.finditer((texto or "")[1:]):
        if m.group(0).lower() not in NAO_ENTIDADE:
            return m.group(0)
    return None


def _json(rel):
    try:
        return json.loads((DATA / rel).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _fatos(assunto, texto, n=5):
    """Fatos validos do banco do assunto mais parecidos com a pergunta (nunca a fala crua do Dono)."""
    import time
    from . import assuntos
    try:
        pal = set(assuntos._norm(texto).split())
        c = assuntos._topico_db(assunto)
        rows = c.execute("SELECT texto,ts FROM fatos WHERE ativo=1 AND (validade IS NULL OR validade>?)", (time.time(),)).fetchall()
        c.close()
    except Exception:
        return []
    rows = [r for r in rows if not r[0].startswith("Dono disse em")]
    op = getattr(MODO, "opiniao", False)
    if op:
        rows = [r for r in rows if assuntos._pontua(r[0], pal)]      # opiniao: ficha sem relacao com a pergunta so atrapalha
    return [t[:700 if op else 240] for t, _ in sorted(rows, key=lambda r: (-assuntos._pontua(r[0], pal), -r[1]))[:6 if op else n]]


def _git(n=3):
    try:
        r = subprocess.run(["git", "log", f"-{n}", "--format=%s"], cwd=str(DATA.parent), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20,
                           creationflags=0x08000000)
        return [l.strip()[:100] for l in r.stdout.splitlines() if l.strip()]
    except Exception:
        return []


# ---------- bloco de dados de cada agente: devolvem (texto, resumo_curto) ----------
def _cofre(p):
    from . import financeiro
    est = financeiro._estado()
    corpo = financeiro.resposta()
    if est.get("movs"):
        hoje = date.today()
        ent = lambda d: sum(m["valor"] for m in est["movs"] if m["valor"] > 0 and date.fromisoformat(m["data"]) > hoje - timedelta(days=d))
        corpo += f"\nGanhos (entradas na conta): últimos 7 dias {financeiro._brl(ent(7))}; últimos 14 dias {financeiro._brl(ent(14))}."
    av = est.get("avaliacao") or {}
    resumo = f"saldo {financeiro._brl(est['saldo'])}, meta {av.get('nivel', '?')}, faltam {financeiro._brl(av.get('falta', 0))}" if est.get("saldo") is not None else "ainda sem leitura da conta"
    return corpo, resumo


def _vaquinha(p):
    from . import vaquinha
    est = vaquinha._estado()
    if not est.get("ativo"):
        return vaquinha.resposta(), "vaquinha ainda não ligada"
    if est.get("encerrada"):
        return f"Vaquinha ENCERRADA em 28/10: meta batida, total R$ {est.get('arrecadado', 0):.2f}. O site agradece a todos.".replace(".", ",", 1), "vaquinha encerrada, meta batida"
    meta, r, g = est.get("meta", vaquinha.META), est.get("arrecadado", 0.0), est.get("gasto")
    brl = lambda v: f"R$ {v:.2f}".replace(".", ",")
    linhas = [f"Recebido {brl(r)} de {brl(meta)} ({r / meta * 100:.0f}%). FALTAM {brl(max(meta - r, 0))} para a meta." + (f" Gasto {brl(g)}; saldo {brl(r - g)}." if g is not None else " Gasto: a Parceira ainda não informou."),
              f"Última informação da Parceira: {est.get('informado_em', 'nenhuma ainda')}. Site: https://vaquinha-exemplo.vercel.app (mostra {brl(est['publicado']) if est.get('publicado') is not None else 'nada ainda'})."]
    if est.get("aguardando"):
        linhas.append("Estou esperando a Parceira responder " + ("quanto já gastamos." if est.get("falta") == "gasto" else "os valores."))
    return "\n".join(linhas), f"recebido {brl(r)} de {brl(meta)}, faltam {brl(max(meta - r, 0))}" + (f", gasto {brl(g)}" if g is not None else "")


def _compasso(p):
    from . import agenda
    dias = 7 if re.search(r"(?i)semana", p) else 1
    return agenda.listar("", dias), "agenda " + ("da semana" if dias > 1 else "de hoje")


def _ilheu(p):
    from . import airbnb_vigia
    est = airbnb_vigia._estado()
    pend = [c for c in (est.get("consultas") or {}).values() if c.get("estado") == "consulta"]
    r = airbnb_vigia.resumo()
    linhas = [f"Atendimento automático do Airbnb: {'LIGADO' if r['ligado'] else 'DESLIGADO'}. Regra: nenhuma reserva é aceita sem o OK do Dono, da Mãe ou da Parceira."]
    linhas.append(f"Esperando o OK de vocês: {len(pend)}" + (" (" + ", ".join(c.get("hospede", "?") for c in pend[:4]) + ")" if pend else "") + ".")
    return "\n".join(linhas), f"{len(pend)} esperando OK; automático {'ligado' if r['ligado'] else 'desligado'}"


def _tino(p):
    from . import qualidade
    trocas, n, _ = qualidade.medir(14)
    pct = round(100 * n / trocas) if trocas else 0
    return f"Qualidade do Jarvis (14 dias): {n} correção(ões) suas em {trocas} trocas (~{pct}%). Regras do conselho já estão no banco.", f"{n}/{trocas} corrigidas"


def _claudinho(p):
    from . import claudinho
    r = claudinho.resumo(48)
    return ("Gerência (Claudinho), últimas 48 h: " + (", ".join(f"{n} {k.replace('_', ' ')}" for k, n in r.items()) if r else "nenhuma resposta ruim do Jarvis encontrada") + ". Regras no guia do Claudinho."), f"{sum(r.values())} achado(s)"


def _nando(p):
    from . import candidaturas
    r = candidaturas.resumo()
    return ("Fila de candidaturas: " + (", ".join(f"{n} {k}" for k, n in r.items()) if r else "vazia") + ". Ainda não me inscrevo sozinho."), f"{sum(r.values())} na fila"


def _generico(assunto, rotulo):
    def f(p):
        fatos = _fatos(assunto, p)
        return (f"{rotulo}:\n" + "\n".join(f"- {t}" for t in fatos)) if fatos else f"{rotulo}: não tenho fato registrado sobre isso.", f"{len(fatos)} fato(s) válido(s)"
    return f


def _cabo_tito(p):
    from . import exercito
    return exercito.resposta(p)


def _forja(p):
    from . import manutencao
    m = manutencao.ultimo()
    from . import sauraki
    linhas = [f"Manutenção da madrugada ({m.get('quando', 'nunca rodou')}): " + (f"{m.get('passaram', 0)} testes ok, {m.get('falharam', 0)} falha(s)." if m else "sem registro.")]
    linhas.append(f"Propostas de melhoria esperando o OK do Dono: {sauraki._propostas_pendentes()}.")
    commits = _git(3)
    if commits:
        linhas.append("Últimas mudanças no código: " + "; ".join(commits))
    return "\n".join(linhas), f"{m.get('passaram', 0)} testes ok, {m.get('falharam', 0)} falha(s)" if m else "sem manutenção registrada"


def _ada(p):
    base, resumo = _generico("programacao", "Programação (ficha da Ada)")(p)
    commits = _git(3)
    return base + ("\nÚltimos commits: " + "; ".join(commits) if commits else ""), resumo


def _correio(p):
    e = _json("correio.json")
    if not e:
        return "Ainda não conferi a caixa de e-mail (o Gmail não está conectado).", "gmail não conectado"
    import time
    return f"Última conferência da caixa: {time.strftime('%d/%m %H:%M', time.localtime(e.get('ts', 0)))}. Só leio remetente e assunto.", "caixa conferida"


def _garimpeiro(p):
    e = _json("vagas.json")
    return (f"Última busca de vagas: {e.get('dia', 'nunca')}; {len(e.get('vistos', []))} vagas já vistas." if e else "Ainda não rodei a busca de vagas."), f"última busca {e.get('dia', 'nunca')}" if e else "sem busca ainda"


def _alma(p):
    base, resumo = _generico("familia", "Família (ficha da Alma)")(p)
    return base, resumo


def _lupa(p):
    from .link import lote_parceiro
    d = lote_parceiro.resumo()
    if not d["por_etapa"]:
        return "Nenhum vídeo do Parceiro em produção agora.", "nenhum vídeo em produção"
    linhas = [f"{et}: {', '.join(cs)}" for et, cs in d["por_etapa"].items() if et != "pendencia"]
    linhas += [f"Pendência {x['numero']} {x['cidade']}: {x['motivo']}" for x in d["pendencias"]]
    return lote_parceiro.esteira("status") + "\n\nVídeos do Parceiro (lote do Braniac):\n" + "\n".join(linhas), f"{sum(len(c) for c in d['por_etapa'].values())} cidades, {len(d['pendencias'])} pendência(s)"


def _mapa(p):
    from . import pendencias
    return pendencias.fala(), f"{pendencias.painel()['total']} pendência(s)"


# nome do agente -> (id do assunto, local_only, funcao). local_only = a resposta nunca passa por IA online.
AGENTES = {
    "Cofre": ("trabalho", True, _cofre), "Vaquinha": ("vaquinha", True, _vaquinha), "Compasso": ("rotina", True, _compasso), "Ilhéu": ("airbnb", True, _ilheu),
    "Cabo Tito": ("exercito", True, _cabo_tito), "Alma": ("familia", True, _alma), "Correio": ("correio", True, _correio),
    "Sultão": ("loja", False, _generico("loja", "Loja (ficha do Sultão)")), "Forja": ("braniac", False, _forja), "Ada": ("programacao", False, _ada),
    "Garimpeiro": ("garimpo", True, _garimpeiro), "Tino": ("qualidade", True, _tino), "Claudinho": ("gerencia", True, _claudinho), "Nando": ("candidaturas", True, _nando), "Lupa": ("parceiro", True, _lupa), "Mapa": ("pendencias", True, _mapa), "Valério": ("investimentos", True, _generico("investimentos", "Investimentos (ficha do Valério)")),
}
# palavras que levam a um agente especifico (alem das palavras do registro de assuntos)
PALAVRAS = {
    "Cofre": r"saldo|infinite\s?pay|extrato|financeir|meta\b|\bmetas\b|ganhos?|renda|dinheiro|grana|1\.?600|corridas?|uber|conta\s+banc",
    "Vaquinha": r"vaquinha|arrecad|vakinha",
    "Mapa": r"pend[eê]nci|pendente",   # 15/11: pendências só quando o Dono pergunta
    "Lupa": r"parceiro|xand[aã]o|prefeitura|v[ií]deos? d[aeo]s? (cidades|prefeituras)",
}


def eh_consulta(texto):
    t = (texto or "").strip()
    return (bool(t) and len(t) < 400 and not t.startswith("/") and bool(PERGUNTA.search(t)) and not ACAO.match(t)
            and not re.search(r"(?i)whats|\bzap\b|\bwpp\b|telegram", t))        # WhatsApp/Telegram tem caminho proprio (ler conversa, nao lidas)


TEMPO_AGENTE = 20             # segundos que o Jarvis espera cada agente antes de responder com o aviso de demora
LIMITE = threading.local()    # LIMITE.perm = agentes liberados na conversa em curso (None = sem restricao)


def escolher(texto, maximo=2):
    """Agentes que devem ser consultados para esta pergunta (ordem de relevancia)."""
    perm = getattr(LIMITE, "perm", None)
    if perm is not None:
        return [n for n in _escolher(texto, 9) if n in perm][:maximo]
    return _escolher(texto, maximo)


def _escolher(texto, maximo):
    from . import assuntos
    pontos = {}
    for nome, rx in PALAVRAS.items():
        if re.search(rx, texto, re.I):
            pontos[nome] = pontos.get(nome, 0) + 3
    ids = {a["id"]: a["agente"] for a in assuntos.listar()}
    for id_, p in assuntos.detectar(texto):
        ag = ids.get(id_)
        if ag in AGENTES:
            pontos[ag] = pontos.get(ag, 0) + p
    if "Forja" in pontos and not re.search(r"(?i)braniac|c[oó]digo|manuten|teste|servidor|\bbug|erro|programa", texto):
        pontos.pop("Forja")                  # 28/10: 'meta pra pagar as contas do mes' puxava a Forja e enchia a resposta de ruido
    if "Cabo Tito" in pontos:
        from . import exercito
        if exercito.eh_pergunta(texto):      # 29/10: prazo/exames do Exercito e do Tito; Cofre/Alma entravam por palavra solta ('meta', 'saude')
            for outro in ("Cofre", "Alma"):
                if outro in pontos and not re.search(PALAVRAS.get(outro, r"(?!)"), texto, re.I):
                    pontos.pop(outro)
    if "Vaquinha" in pontos and not re.search(PALAVRAS["Vaquinha"], texto, re.I):
        pontos.pop("Vaquinha")               # 'exames do exercito'/'meta' casam por palavra solta, mas so se falou da vaquinha e dela
    if "Vaquinha" in pontos and "Cofre" in pontos and not re.search(r"(?i)1\.?600|saldo|infinite|ganhos?|financeir", texto):
        pontos.pop("Cofre")                  # 'como esta a vaquinha' e do agente da vaquinha, nao do financeiro
    return [n for n, _ in sorted(pontos.items(), key=lambda x: -x[1])][:maximo]


def consultar(agente, pergunta):
    """O Jarvis pergunta; o agente responde. Registra pedido/resposta no barramento. Devolve {'agente','texto','resumo','local_only'}."""
    from . import barramento
    assunto, local, fn = AGENTES[agente]
    try:
        barramento.enviar("Jarvis", agente, "pedido", "ele quer saber: " + pergunta.replace("[AVALIACAO-AUTOMATICA]", "").strip()[:100])
    except Exception:
        pass
    out, op = {}, getattr(MODO, "opiniao", False)

    def _rodar():
        MODO.opiniao = op                    # MODO e por thread: leva o modo da conversa para a thread do agente
        try:
            out["r"] = fn(pergunta)
        except Exception as e:
            out["r"] = f"Não consegui levantar os dados agora ({str(e)[:80]}).", "erro ao levantar os dados"
        try:                                 # atrasado ou nao, a resposta chega ao Jarvis pelo barramento
            barramento.enviar(agente, "Jarvis", "resposta", f"{out['r'][1][:140]}")
        except Exception:
            pass

    t = threading.Thread(target=_rodar, daemon=True, name=f"agente-{agente}")
    t.start()
    t.join(TEMPO_AGENTE)                     # agente travado nao segura a conversa
    if "r" not in out:
        return {"agente": agente, "texto": f"O agente {agente} demorou para responder agora; tente de novo em instantes.", "resumo": "demorou", "local_only": local}
    texto, resumo = out["r"]
    return {"agente": agente, "texto": texto, "resumo": resumo, "local_only": local}


def _varrer(texto):
    """Opiniao sobre um nome proprio que nenhum agente reivindicou: procura o nome em TODO o banco (todos os assuntos). Devolve o resultado do atender ou None."""
    ent = _entidade(texto)
    if not ent:
        return None
    from . import banco
    achado, _ = banco.consultar(ent, n=6)
    achado = (achado or "").strip()
    return {"texto": f"Falei com o banco do Jarvis. O que ele tem sobre {ent}:\n\n{achado}" if achado else f"Procurei {ent} no banco inteiro e não achei registro.",
            # local_only False: consultar() sem tipo devolve so a camada publica, que pode ir a IA online
            "agentes": ["Banco"], "local_only": False, "vazio": not achado, "entidade": ent}


DIRETOS = ("Cabo Tito", "Mapa")   # respondem direto e saem em áudio para o Dono


def atender(texto, forcar=None):
    """Consulta os agentes certos e devolve {'texto', 'agentes', 'local_only', 'vazio'} ou None se a pergunta nao e de nenhum agente.
    Opiniao ('o que acha de X?'): ate 3 agentes, fichas completas; sem agente do assunto, varre o banco inteiro pelo nome."""
    op = eh_opiniao(texto)
    nomes = list(forcar) if forcar else (escolher(texto, 3 if op else 2) if eh_consulta(texto) else [])
    if not nomes:
        return _varrer(texto) if op and not forcar else None
    MODO.opiniao = op
    try:
        res = [consultar(n, texto) for n in nomes]
    finally:
        MODO.opiniao = False
    if len(res) == 1 and res[0]["agente"] in DIRETOS:      # resposta direta (Cabo Tito, Mapa), sem "Falei com..." nem rotulo
        return {"texto": res[0]["texto"], "agentes": nomes, "local_only": res[0]["local_only"]}
    blocos = [f"🔹 {r['agente']}:\n{r['texto']}" for r in res]
    intro = "Falei com " + " e com ".join(r["agente"] for r in res) + (". O que ele tem:" if len(res) == 1 else ". O que eles têm:") + "\n\n"
    return {"texto": intro + "\n\n".join(blocos), "agentes": nomes, "local_only": any(r["local_only"] for r in res)}


def via_jarvis(agente, enviar):
    """Envolve o envio de um agente: o aviso passa pelo barramento (agente -> Jarvis) e e o JARVIS quem fala com a pessoa."""
    def f(texto):
        try:
            from . import barramento
            barramento.enviar(agente, "Jarvis", "alerta", str(texto)[:140])
        except Exception:
            pass
        return enviar(texto)
    return f
