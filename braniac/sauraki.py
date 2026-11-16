# -*- coding: utf-8 -*-
"""SAURAKI (Sistema Autonomo Unificado de Raciocinio, Aprendizado, Conhecimento e Inteligencia) - camada VISUAL do Braniac: escritorio virtual 2D.
Este modulo so MONTA o retrato (snapshot) do que o Braniac ja registra: agentes (assuntos.py), recados (barramento), situacao (Compasso), arquivos de estado e
logs (so a HORA da ultima atividade), propostas aguardando o Dono, autonomia e servicos. 100% codigo comum: nenhuma chamada de IA, nenhum agente novo.
Estado so e afirmado quando ha dado real; o que nao e observavel vira None ("dado nao disponivel"). Nunca devolve conteudo de WhatsApp, segredo ou token."""
import json
import time
from datetime import datetime

from .store import DATA

JANELA_EXECUTANDO_S = 180            # atividade nos ultimos 3 min = executando
JANELA_CONSULTANDO_S = 30            # pedido a outro agente nos ultimos 30 s = consultando
NOMES = {"Alma": "A.L.M.A."}         # nome de exibicao (o nome tecnico segue sendo o do registro)
ESTADOS = ("ocioso", "analisando", "planejando", "executando", "consultando", "aguardando_autorizacao", "aguardando_servico", "concluido", "erro", "desconectado")

# fonte de "ultima atividade" de cada agente: arquivos (relativos a data/) cuja data de modificacao conta. So a HORA e usada, nunca o conteudo.
FONTES = {
    "Jarvis": ("dono.log", "atendimentos.log", "vigia.log"),
    "Alma": ("alma/diario.jsonl",),
    "Forja": ("manutencao.json", "automelhoria.json"),
    "Ilhéu": ("airbnb.log",),
    "Claudinho": ("claudinho/achados.jsonl", "claudinho/estado.json"),
    "Tino": ("erros_jarvis.jsonl", "erros_detectados.json"),
    "Valério": ("financeiro.json",),
    "Nando": ("candidaturas.json",),
    "Cofre": ("financeiro.json",),
    "Compasso": ("agenda_envios.log", "compasso/situacao.json"),
    "Correio": ("correio.json",),
    "Garimpeiro": ("vagas.json",),
    "Monza": ("monza.json",),
    "Zelo": ("atendimentos.log",),
    "Vaquinha": ("vaquinha.json",),
    "Lupa": ("parceiro/lote.json",),
}
# agentes cujo funcionamento depende de algo que pode estar desligado (arquivo de estado -> chave booleana)
SEM_FONTE = "sem registro de atividade para este agente (dado não disponível)"


def _mtime(rel):
    try:
        return (DATA / rel).stat().st_mtime
    except OSError:
        return 0.0


def _json(rel):
    try:
        return json.loads((DATA / rel).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _propostas_pendentes():
    n = 0
    try:
        for f in (DATA / "propostas").glob("*.md"):
            if "AGUARDANDO APROVA" in f.read_text(encoding="utf-8", errors="replace")[:600].upper():
                n += 1
    except OSError:
        pass
    return n


def _agentes_registrados():
    """[(nome_tecnico, especialidade)] do registro real (assuntos) + o Jarvis (orquestrador de todos os canais)."""
    out = [("Jarvis", "Entrada de todas as conversas; orquestra os agentes e as ferramentas")]
    try:
        from . import assuntos
        for a in assuntos.listar():
            if a["agente"] and a["agente"] not in {n for n, _ in out}:
                out.append((a["agente"], a["descricao"]))
    except Exception:
        pass
    return out


def _agentes_empresa():
    """[(nome, papel)] da empresa de desenvolvimento (2o andar). O nome do agente nunca colide com os do 1o andar."""
    try:
        from . import empresa_dev, modulos
        modulos.exigir("programacao")
        usados = {n for n, _ in _agentes_registrados()}
        return [(a["nome"], a["papel"], a.get("sala") or empresa_dev.sala_de(a)) for a in empresa_dev.agentes() if a["nome"] not in usados]
    except Exception:
        return []


def _agentes_marketing():
    """[(nome, papel, sala)] da Fornalha (3o andar)."""
    try:
        from . import empresa_mkt, modulos
        modulos.exigir("marketing")
        usados = {n for n, _ in _agentes_registrados()} | {n for n, _, _ in _agentes_empresa()}
        return [(a["nome"], a["papel"], a.get("sala", "Marketing")) for a in empresa_mkt.agentes() if a["nome"] not in usados]
    except Exception:
        return []


def _agentes_invest():
    """[(nome, papel, sala)] da Quantix (4o andar)."""
    try:
        from . import empresa_inv, modulos
        modulos.exigir("investimentos")
        usados = {n for n, _ in _agentes_registrados()} | {n for n, _, _ in _agentes_empresa()} | {n for n, _, _ in _agentes_marketing()}
        return [(a["nome"], a["papel"], a.get("sala", "Mesa")) for a in empresa_inv.agentes() if a["nome"] not in usados]
    except Exception:
        return []


def _agentes_compras():
    """[(nome, papel, sala)] da Pechincha (6o andar)."""
    try:
        from . import empresa_compras, modulos
        modulos.exigir("compras")
        usados = {n for n, _ in _agentes_registrados()} | {n for n, _, _ in _agentes_empresa()} | {n for n, _, _ in _agentes_marketing()} | {n for n, _, _ in _agentes_invest()} | {n for n, _, _ in _agentes_cortes()}
        return [(a["nome"], a["papel"], a.get("sala", "Mesa")) for a in empresa_compras.agentes() if a["nome"] not in usados]
    except Exception:
        return []


def _agentes_cortes():
    """[(nome, papel, sala)] da Claquete (5o andar)."""
    try:
        from . import empresa_cortes, modulos
        modulos.exigir("cortes_video")
        usados = {n for n, _ in _agentes_registrados()} | {n for n, _, _ in _agentes_empresa()} | {n for n, _, _ in _agentes_marketing()} | {n for n, _, _ in _agentes_invest()}
        return [(a["nome"], a["papel"], a.get("sala", "Mesa")) for a in empresa_cortes.agentes() if a["nome"] not in usados]
    except Exception:
        return []


def _fala_do_barramento(agora):
    """{agente: {ts, texto, tipo}} do ultimo recado ENVIADO por ele + quem pediu algo a alguem recentemente."""
    ult, consultas = {}, {}
    try:
        from . import barramento
        for m in barramento.historico(120):
            privado = m["tipo"] == "dono_disse"      # o que o Dono diz ao Jarvis nunca vira texto na tela
            ult[m["de"]] = {"ts": m["ts"], "texto": "" if privado else m["texto"][:140], "tipo": m["tipo"], "para": m["para"]}
            if m["tipo"] in ("pedido", "dono_disse") and agora - m["ts"] <= JANELA_CONSULTANDO_S:
                consultas[m["de"]] = m["para"]
    except Exception:
        pass
    return ult, consultas


def _logs():
    """{agente: [{ts, onde, texto}]} (os 8 mais novos): recados do barramento + historico dos tickets (NexoDev) e pedidos (Fornalha).
    O que o Dono diz ao Jarvis nunca entra."""
    L = {}
    def add(nome, ts, onde, txt):
        if nome and txt:
            L.setdefault("Claude" if nome == "senior" else nome, []).append({"ts": ts, "onde": onde, "texto": str(txt)[:240]})
    try:
        from . import barramento
        for m in barramento.historico(300):
            if m["tipo"] != "dono_disse":
                add(m["de"], m["ts"], f"{m['tipo']} → {m['para']}", m["texto"])
    except Exception:
        pass
    for rel, rot in (("empresa_dev/tickets.json", "ticket"), ("empresa_mkt/pedidos.json", "pedido")):
        dados = _json(rel)
        for t in (dados if isinstance(dados, list) else []):
            for h in t.get("historico") or []:
                add(h.get("quem"), h.get("ts"), f"{rot} {t.get('id')}", h.get("txt"))
    return {n: sorted(v, key=lambda m: m["ts"] or 0)[-8:][::-1] for n, v in L.items()}


def _estado_agente(nome, ultima, consultas, agora):
    """(estado|None, motivo). Cada estado so aparece quando ha dado real por tras."""
    if nome == "Vaquinha" and not _json("vaquinha.json").get("ativo"):
        return "desconectado", "agente ainda não ligado (falta logar o banco)"
    if nome == "Forja" and _json("manutencao.json").get("testes_ok") is False:
        return "erro", "a manutenção da madrugada reportou teste falhando"
    if nome == "Vaquinha" and _json("vaquinha.json").get("ultimo_erro"):
        return "erro", "último deploy do site falhou"
    if nome == "Ilhéu":
        pend = [c for c in (_json("airbnb_estado.json").get("consultas") or {}).values() if c.get("estado") == "consulta"]
        if pend:
            return "aguardando_autorizacao", f"{len(pend)} reserva(s)/hóspede(s) esperando o OK de vocês"
    if nome in ("Forja", "Alma") and _propostas_pendentes():
        return "aguardando_autorizacao", f"{_propostas_pendentes()} proposta(s) de melhoria esperando aprovação do Dono"
    if nome in consultas:
        return "consultando", f"pediu algo a {consultas[nome]} pelo barramento"
    if ultima and agora - ultima <= JANELA_EXECUTANDO_S:
        return "executando", "atividade registrada agora há pouco"
    if nome not in FONTES:
        return None, SEM_FONTE
    return "ocioso", "sem atividade recente"


def snapshot(status=None, agora=None):
    """Retrato completo para a tela. `status` = o /api/status ja montado pelo servidor (evita recalcular)."""
    agora = agora or time.time()
    s = status or {}
    falas, consultas = _fala_do_barramento(agora)
    logs = _logs()
    situacao = {}
    try:
        from . import compasso
        situacao = compasso.painel_agentes()
    except Exception:
        pass
    agentes = []
    andar2 = {n: (p, sl) for n, p, sl in _agentes_empresa()}
    andar3 = {n: (p, sl) for n, p, sl in _agentes_marketing()}
    andar4 = {n: (p, sl) for n, p, sl in _agentes_invest()}
    andar5 = {n: (p, sl) for n, p, sl in _agentes_cortes()}
    andar6 = {n: (p, sl) for n, p, sl in _agentes_compras()}
    for n in andar6:
        FONTES.setdefault(n, ("empresa_compras/pedidos.json",))
    for n in andar5:
        FONTES.setdefault(n, ("empresa_cortes/pedidos.json",))
        if andar5[n][1] == "Estúdio":      # Pena, Eco e Prisma: atividade do Estudio 3D
            FONTES[n] = ("empresa_cortes/estudio.json",)
    for n in andar4:
        FONTES.setdefault(n, ("empresa_inv/carteira.json",))
    for n in andar2:
        FONTES.setdefault(n, ("empresa_dev/tickets.json",))
    for n in andar3:
        FONTES.setdefault(n, ("empresa_mkt/pedidos.json",))
    for nome, esp in _agentes_registrados() + [(n, v[0]) for n, v in {**andar2, **andar3, **andar4, **andar5, **andar6}.items()]:
        ts_arq = max([_mtime(f) for f in FONTES.get(nome, ())] or [0.0])
        ts_bus = falas.get(nome, {}).get("ts", 0.0)
        ultima = max(ts_arq, ts_bus) or None
        est, motivo = _estado_agente(nome, ultima, consultas, agora)
        agentes.append({"nome": nome, "exibir": NOMES.get(nome, nome), "especialidade": esp, "estado": est, "motivo": motivo,
                        "andar": 6 if nome in andar6 else 5 if nome in andar5 else 4 if nome in andar4 else 3 if nome in andar3 else 2 if nome in andar2 else 1, "sala": (andar6.get(nome) or andar5.get(nome) or andar4.get(nome) or andar3.get(nome) or andar2.get(nome) or (0, None))[1], "ultima_atividade": ultima, "tarefa": falas.get(nome, {}).get("texto") or (situacao.get(nome) or {}).get("texto"),
                        "atividades": [m for m in [falas.get(nome)] if m and m["tipo"] != "dono_disse"], "inicio": None, "duracao_s": None, "log": logs.get(nome, []),
                        "avisos": ([motivo] if est in ("erro", "aguardando_autorizacao") else [])})
    cont = {k: sum(1 for a in agentes if a["estado"] == k) for k in ESTADOS}
    cont["sem_dado"] = sum(1 for a in agentes if a["estado"] is None)
    aut = s.get("autonomia") or {}
    servicos = [{"nome": "Atendimento WhatsApp", "ok": bool((s.get("atendimento_auto") or {}).get("ligado"))},
                {"nome": "Airbnb", "ok": bool((s.get("airbnb_auto") or {}).get("ligado"))},
                {"nome": "Microfone", "ok": (s.get("escuta_voz") or {}).get("estado") not in (None, "parada")},
                {"nome": "Gmail", "ok": bool((s.get("email") or {}).get("logado"))},
                {"nome": "Braniac", "ok": bool(s.get("ligado", True))}]
    uso = [{"nome": p["nome"], "ok": p["ok"], "hoje": p.get("hoje")} for p in (s.get("provedores") or [])]
    try:
        from . import termico
        rec = termico.atual()
    except Exception:
        rec = {}
    try:   # festa do escritorio (meta batida): data/sauraki_festa.json {"ate": epoch}; a tela leva so os ociosos para la
        from .store import DATA
        festa_ate = json.loads((DATA / "sauraki_festa.json").read_text(encoding="utf-8")).get("ate")
    except (OSError, ValueError):
        festa_ate = None
    return {"ts": agora, "festa_ate": festa_ate if festa_ate and festa_ate > agora else None, "simulado": False, "agentes": agentes, "contagem": cont, "total": len(agentes),
            "autonomia": {"armada": bool(aut.get("armada")), "restante_min": aut.get("restante_min"), "indefinida": bool(aut.get("indefinida"))},
            "servicos": servicos, "provedores": uso, "recursos": {k: rec.get(k) for k in ("gpu_c", "cpu_pct", "ram_pct", "quente")},
            "predios": _predios(), "esteira": _esteira(agora), "loja_conversa": _loja_conversa(), "link_conversa": _link_conversa(), "empresa": _empresa(), "conversa": _conversa(), "propostas_pendentes": _propostas_pendentes(), "tokens": None,
            "nota": "Estados não observáveis (analisando, planejando, concluído, aguardando serviço) aparecem como 'dado não disponível' até haver eventos reais."}


def _link_conversa():
    try:
        from .link import integracao
        return integracao.resumo()
    except Exception:
        return None


def _loja_conversa():
    try:
        from . import elo_loja
        return elo_loja.resumo()
    except Exception:
        return None


# andar da Esteira do Parceiro: uma estacao por etapa, com o agente que cuida dela (Pena, Eco, Prisma e Lupa sao do Estudio da Claquete;
# Busca, Fiscal e Entrega foram nomeados pelo Braniac em 14/11/2026)
ESTACOES = (("busca", "Busca", "baixa os PDFs do TCM-BA", ("reservada", "baixando_tcm")),
            ("fiscal", "Fiscal", "confere as contas com o Balanço", ("levantamento",)),
            ("pena", "Pena", "roteiro e cenas", ("roteiro",)),
            ("eco", "Eco", "voz e sincronia", ("voz", "sincronia")),
            ("prisma", "Prisma", "cenas 3D e render", ("render",)),
            ("lupa", "Lupa", "confere o vídeo pronto", ("conferencia",)),
            ("entrega", "Entrega", "entrega o vídeo no site", ("pronto",)))
JANELA_ESTEIRA_S = 15 * 60   # cidade que entrou na etapa ha menos de 15 min = estacao trabalhando


def _esteira(agora):
    """Retrato da esteira para o andar 3D: so o resumo publico (lote_parceiro.publico), nada de caminho, contato ou log."""
    try:
        from .link import lote_parceiro
        p = lote_parceiro.publico()
    except Exception:
        return None
    e, cidades = p.get("esteira") or {}, sorted((p.get("cidades") or {}).values(), key=lambda c: -(c.get("desde") or 0))
    atual = e.get("atual") or {}
    est = []
    for chave, agente, papel, etapas in ESTACOES:
        aqui = [c for c in cidades if c.get("etapa") in etapas]
        agora_aqui = atual.get("etapa") in etapas or any(agora - (c.get("desde") or 0) < JANELA_ESTEIRA_S for c in aqui)
        est.append({"chave": chave, "agente": agente, "papel": papel, "total": len(aqui),
                    "estado": "executando" if agora_aqui else "aguardando_servico" if aqui else "ocioso",
                    "cidades": [{"numero": c.get("numero"), "cidade": c.get("cidade")} for c in aqui[:4]]})
    pend = [c for c in cidades if c.get("etapa") == "pendencia"]
    return {"estacoes": est, "atual": {k: atual.get(k) for k in ("numero", "cidade", "etapa")} if atual else None,
            "prontos": len(e.get("prontos") or []), "meta": e.get("meta"), "pendencias": len(pend),
            "pendentes": [{"numero": c.get("numero"), "cidade": c.get("cidade")} for c in pend[:6]], "progresso_pct": e.get("progresso_pct"),
            "quadrados": [str(s.get("estado") or "fila") for s in e.get("slots") or []]}   # telão do andar: um estado por vídeo do lote


def _predios():
    try:
        from . import rede_jarvis
        return rede_jarvis.predios()
    except Exception:
        return []


def _empresa():
    try:
        from . import empresa_compras, empresa_cortes, empresa_dev, empresa_inv, empresa_mkt
        return {**empresa_dev.situacao(), "compras": empresa_compras.situacao(), "marketing": empresa_mkt.situacao(), "investimentos": empresa_inv.situacao(), "cortes": empresa_cortes.situacao()}
    except Exception:
        return None


def _conversa(n=40):
    try:
        from . import barramento
        return [{"id": m["id"], "ts": m["ts"], "de": m["de"], "para": m["para"], "tipo": m["tipo"], "texto": m["texto"][:140]} for m in barramento.historico(n)
                if m["tipo"] != "dono_disse"]       # o que o Dono diz NAO aparece na tela (privacidade)
    except Exception:
        return []


def demo(snap):
    """Copia do retrato SEM texto real (ex.: saldo, e-mails, falas): estados rotativos e falas ficticias, para gravar video. Marcada como simulada."""
    d = dict(snap)
    rot = ("ocioso", "analisando", "executando", "consultando", "concluido", "planejando")
    d["agentes"] = [dict(a, estado=rot[(i + int(snap["ts"] // 8)) % len(rot)], motivo="demonstração", tarefa=None, atividades=[], avisos=[], ultima_atividade=None)
                    for i, a in enumerate(snap["agentes"])]
    d["contagem"] = {k: sum(1 for a in d["agentes"] if a["estado"] == k) for k in ESTADOS}
    d["conversa"] = [{"id": 1, "ts": snap["ts"], "de": "Jarvis", "para": "Ilhéu", "tipo": "pedido", "texto": "(demo) hóspede pergunta o horário de check-in"},
                     {"id": 2, "ts": snap["ts"], "de": "Ilhéu", "para": "Jarvis", "tipo": "resposta", "texto": "(demo) check-in a partir das 14h"}]
    d["loja_conversa"] = d["link_conversa"] = {"ativa": False, "total": 0, "ultima": None}
    d["empresa"] = {}
    d["servicos"] = [{"nome": n, "ok": True} for n in ("Atendimento WhatsApp", "Airbnb", "Microfone", "Gmail", "Braniac")]
    d["provedores"] = []
    d.update(simulado=True, festa_ate=None, propostas_pendentes=0, nota="Modo demonstração: nada aqui é real.")
    return d
