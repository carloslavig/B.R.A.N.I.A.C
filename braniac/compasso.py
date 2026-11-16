# -*- coding: utf-8 -*-
"""ROTINAS DA Compasso (pedido do Dono, 10/10/2026): a Compasso guarda as rotinas da familia (e do proprio Jarvis) e, na hora certa,
ACIONA o Jarvis para executar. Protocolo completo em data/compasso/PROTOCOLO-ROTINAS.md.

Protocolo de acionamento (Compasso -> Jarvis), em 4 passos, tudo LOCAL e sem IA online:
 1. AGENDA   - rotinas ficam em data/compasso/rotinas.json (estruturado; ver NOVA_ROTINA). So a funcao `tick` decide se uma rotina venceu.
 2. PEDIDO   - a Compasso nao age sozinha: ela monta um PEDIDO {id, rotina, acao, para, texto} e o registra em data/compasso/pedidos.jsonl.
 3. CHECAGEM - o Jarvis valida o pedido ANTES de executar: acao na lista branca ACOES, contato na lista CONTATOS_PERMITIDOS,
               rotina ATIVA (ativar e decisao do Dono), dentro do horario 08h-21h, no maximo 1 vez por dia por rotina e TETO_DIARIO no total,
               texto sem nada de pagamento/senha/codigo (TERMOS_PROIBIDOS). Falhou uma checagem -> nao executa e registra o motivo.
 4. RESULTADO - o Jarvis executa so a acao pedida, grava o resultado no pedido e conta na sala (/sala) e no relatorio do bom dia.
Nada aqui le, pede ou guarda chave, senha ou segredo. Nenhuma acao aciona o Claude (custo) nem mexe em anuncio, reserva ou dinheiro."""
import json, re, threading, unicodedata
from datetime import datetime
from .store import DATA

PASTA = DATA / "compasso"
ARQ = PASTA / "rotinas.json"
PEDIDOS = PASTA / "pedidos.jsonl"
HORA_MIN, HORA_MAX = 8, 21          # ninguem recebe mensagem de rotina de madrugada
TETO_DIARIO = 10                    # pedidos EXECUTADOS por dia, somando todas as rotinas
LOCK = threading.Lock()
DIAS = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]

# lista branca: o que a Compasso pode pedir ao Jarvis. Qualquer outra coisa e recusada.
ACOES = {
    "perguntar_contato": "Jarvis manda por WhatsApp a mensagem (texto) da rotina para um contato da familia e a resposta segue o atendimento normal.",
    "lembrar_dono": "Jarvis manda um lembrete por WhatsApp para o Dono.",
    "verificar_youtube": "Jarvis confere o status dos cortes/canal do YouTube (so leitura, local) e manda o resumo ao Dono.",
    "audio_contato": "Jarvis manda um AUDIO (voz dele) por WhatsApp para um contato da familia; se o audio falhar 2x, manda o mesmo texto escrito.",
}
# o bom dia em audio pode sair mais cedo (15/10, pedido do Dono para o Irmao as 6h); as demais acoes continuam 08h-21h
HORA_MIN_POR_ACAO = {"audio_contato": 6}
TEXTO_MAX = {"audio_contato": 1500}
# apelido -> chave do contexto.contato(); so a familia/dono. Leads, hospedes e estabelecimentos NUNCA entram em rotina.
CONTATOS_PERMITIDOS = {"dono": "dono", "mae": "mae", "mae": "mae", "mainha": "mae",
                       "parceira": "parceira", "parceira": "parceira", "irmao": "irmao"}
TERMOS_PROIBIDOS = re.compile(r"cart[aã]o|cpf|senha|c[oó]digo|token|pix|transfer|pagamento|pagar|boleto|conta banc|ag[eê]ncia|chave|segredo|login", re.I)

NOVA_ROTINA = {   # formato de cada rotina (documentacao viva; `criar` preenche os padroes)
    "id": "slug-curto", "titulo": "texto", "acao": "uma das ACOES", "para": "apelido em CONTATOS_PERMITIDOS (vazio = Dono)",
    "horario": "HH:MM", "dias": "lista de DIAS (vazio = todos)", "textos": ["variacoes da mensagem; roda uma por dia"],
    "motivo": "por que existe", "ativa": False, "ate": "AAAA-MM-DD ou vazio", "criada_por": "Dono/Jarvis/Compasso", "criada_em": "data",
    "ultima": "AAAA-MM-DD da ultima execucao",
}


class RotinaErro(Exception):
    pass


def _norm(x):
    x = unicodedata.normalize("NFKD", (x or "").lower()).encode("ascii", "ignore").decode()
    return " ".join(x.split())


def _ler():
    try:
        return json.loads(ARQ.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"rotinas": []}


def _gravar(d):
    PASTA.mkdir(parents=True, exist_ok=True)
    tmp = ARQ.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(ARQ)


def listar():
    return _ler()["rotinas"]


def obter(rid):
    return next((r for r in listar() if r["id"] == rid), None)


def validar(r):
    """Levanta RotinaErro se a rotina fugir do protocolo. Vale na criacao e de novo antes de cada execucao."""
    if r.get("acao") not in ACOES:
        raise RotinaErro(f"ação '{r.get('acao')}' fora da lista permitida ({', '.join(ACOES)})")
    if r.get("acao") in ("perguntar_contato", "audio_contato") and _norm(r.get("para")) not in CONTATOS_PERMITIDOS:
        raise RotinaErro(f"contato '{r.get('para')}' não pode receber rotina (só família: {', '.join(sorted(set(CONTATOS_PERMITIDOS)))})")
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", r.get("horario", "")):
        raise RotinaErro("horário precisa ser HH:MM")
    h = int(r["horario"][:2])
    hmin = HORA_MIN_POR_ACAO.get(r.get("acao"), HORA_MIN)
    if not hmin <= h <= HORA_MAX:
        raise RotinaErro(f"horário fora da janela {hmin:02d}h-{HORA_MAX:02d}h")
    if any(d not in DIAS for d in r.get("dias") or []):
        raise RotinaErro(f"dias válidos: {', '.join(DIAS)}")
    for t in r.get("textos") or []:
        if TERMOS_PROIBIDOS.search(t):
            raise RotinaErro("texto da rotina não pode falar de pagamento, senha, código ou dados bancários")
        if len(t) > TEXTO_MAX.get(r.get("acao"), 500):
            raise RotinaErro(f"texto da rotina muito longo (máx. {TEXTO_MAX.get(r.get('acao'), 500)})")
    if r.get("complemento") and (TERMOS_PROIBIDOS.search(r["complemento"]) or len(r["complemento"]) > 4500):
        raise RotinaErro("complemento escrito não pode falar de pagamento, senha, código ou dados bancários (máx. 4500)")
    if r.get("acao") in ("perguntar_contato", "lembrar_dono", "audio_contato") and not r.get("textos"):
        raise RotinaErro("essa ação precisa de pelo menos um texto")
    return r


def criar(rid, titulo, acao, horario, textos=None, para="", dias=None, motivo="", ate="", criada_por="Dono", ativa=False):
    """Guarda uma rotina NOVA. Nasce DESATIVADA por padrao: so o Dono ativa (ativar)."""
    r = {"id": _norm(rid).replace(" ", "-")[:40], "titulo": titulo.strip(), "acao": acao, "para": para, "horario": horario, "dias": list(dias or []),
         "textos": [t.strip() for t in (textos or []) if t.strip()], "motivo": motivo, "ativa": bool(ativa), "ate": ate,
         "criada_por": criada_por, "criada_em": datetime.now().strftime("%Y-%m-%d %H:%M"), "ultima": ""}
    validar(r)
    with LOCK:
        d = _ler()
        if any(x["id"] == r["id"] for x in d["rotinas"]):
            raise RotinaErro(f"já existe rotina '{r['id']}'")
        d["rotinas"].append(r)
        _gravar(d)
    return r


def ativar(rid, ligado=True):
    """Liga/desliga uma rotina. Chamado quando o DONO pede (Jarvis, ferramenta compasso)."""
    with LOCK:
        d = _ler()
        for r in d["rotinas"]:
            if r["id"] == rid:
                r["ativa"] = bool(ligado)
                _gravar(d)
                return r
    raise RotinaErro(f"rotina '{rid}' não existe")


def remover(rid):
    with LOCK:
        d = _ler()
        antes = len(d["rotinas"])
        d["rotinas"] = [r for r in d["rotinas"] if r["id"] != rid]
        if len(d["rotinas"]) == antes:
            raise RotinaErro(f"rotina '{rid}' não existe")
        _gravar(d)


def resumo():
    rs = listar()
    if not rs:
        return "A Compasso ainda não tem rotinas guardadas."
    return "\n".join(f"{'🟢' if r['ativa'] else '⏸'} {r['id']} · {r['horario']} {'/'.join(r['dias']) or 'todo dia'} · {r['titulo']}"
                     + (f" → {r['para']}" if r.get("para") else "") + (f" (até {r['ate']})" if r.get("ate") else "") for r in rs)


# ---------- protocolo de acionamento ----------

def _pedidos_hoje(hoje):
    try:
        linhas = [json.loads(l) for l in PEDIDOS.read_text(encoding="utf-8").splitlines() if l.strip()]
    except (OSError, ValueError):
        return []
    return [x for x in linhas if str(x.get("id", "")).startswith(hoje.replace("-", ""))]


def _anotar_pedido(p):
    PASTA.mkdir(parents=True, exist_ok=True)
    with PEDIDOS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(p, ensure_ascii=False) + "\n")


def vencidas(agora):
    """Rotinas ativas cujo horario de hoje ja passou e que ainda nao rodaram hoje."""
    hoje = agora.strftime("%Y-%m-%d")
    out = []
    for r in listar():
        if not r.get("ativa") or r.get("ultima") == hoje:
            continue
        if r.get("ate") and hoje > r["ate"]:
            continue
        if r.get("dias") and DIAS[agora.weekday()] not in r["dias"]:
            continue
        if agora.strftime("%H:%M") >= r["horario"]:
            out.append(r)
    return out


def montar_pedido(r, agora):
    """Passo 2: a Compasso monta o pedido ao Jarvis. Texto = uma das variacoes aprovadas (roda pelo dia do ano), nunca gerado por IA."""
    textos = r.get("textos") or [""]
    return {"id": agora.strftime("%Y%m%d-%H%M%S-") + r["id"], "de": "Compasso", "para_agente": "Jarvis", "rotina": r["id"], "acao": r["acao"],
            "contato": r.get("para") or "dono", "texto": textos[agora.timetuple().tm_yday % len(textos)], "status": "pedido",
            "complemento": r.get("complemento", "")}


def checar(p, r, agora):
    """Passo 3: o Jarvis confere o pedido. Devolve None se pode executar, ou o motivo da recusa."""
    try:
        validar(r)
    except RotinaErro as e:
        return str(e)
    if not r.get("ativa"):
        return "rotina desativada"
    if not HORA_MIN_POR_ACAO.get(r["acao"], HORA_MIN) <= agora.hour <= HORA_MAX:
        return "fora do horário permitido"
    if p["acao"] != r["acao"] or p["texto"] not in (r.get("textos") or [""]):
        return "pedido diferente da rotina guardada"
    feitos = [x for x in _pedidos_hoje(agora.strftime("%Y-%m-%d")) if x.get("status") == "feito"]
    if any(x["rotina"] == r["id"] for x in feitos):
        return "essa rotina já rodou hoje"
    if len(feitos) >= TETO_DIARIO:
        return f"teto diário de {TETO_DIARIO} execuções atingido"
    return None


def _nome_whatsapp(apelido):
    from . import contexto
    chave = CONTATOS_PERMITIDOS.get(_norm(apelido), "dono")
    padrao = {"dono": "Eu", "mae": "mainha", "parceira": "Parceira", "irmao": "Irmao"}.get(chave, apelido)
    return contexto.contato(chave) or padrao


def executar(p, enviar):
    """Passo 4: o Jarvis executa SO a acao do pedido. `enviar(nome_whatsapp, texto)` devolve o texto de resultado do envio."""
    if p["acao"] == "perguntar_contato":
        return enviar(_nome_whatsapp(p["contato"]), p["texto"])
    if p["acao"] == "audio_contato":
        nome = _nome_whatsapp(p["contato"])
        from . import voz, wpp_voz
        wav = voz.falar_wav(p["texto"])
        for _ in range(2):
            r = str(wpp_voz.enviar_voz(nome, wav))
            if r.startswith("✅"):
                if p.get("complemento"):
                    enviar(nome, p["complemento"])         # o resumo escrito que o audio promete vai logo depois
                return r
        return enviar(nome, p["texto"] + ("\n\n" + p["complemento"] if p.get("complemento") else ""))   # audio falhou 2x: tudo por escrito
    if p["acao"] == "lembrar_dono":
        return enviar(_nome_whatsapp("dono"), "💗 Lembrete da Compasso: " + p["texto"])
    if p["acao"] == "verificar_youtube":
        from .cortes import comandos
        return enviar(_nome_whatsapp("dono"), "📺 Compasso pediu e o Jarvis conferiu o canal/cortes:\n" + comandos.status()
                      + (f"\n\n{p['texto']}" if p["texto"] else ""))
    return "acao desconhecida"


def _contar(texto):
    try:
        from . import rotina, sala
        sala.registrar("sistema", texto, "aviso")
        rotina.registrar(texto)
    except Exception:
        pass


def tick(agora=None, enviar=None):
    """Chamado pelo laco das rotinas do Jarvis (rotina.tick, ~10 min). Devolve a lista de pedidos processados."""
    agora = agora or datetime.now()
    if enviar is None:
        from .rotina import _enviar as enviar
    feitos = []
    try:
        acompanhar(agora)
    except Exception:
        pass
    try:    # AGENDA do Dono e da Compasso (15/10): os lembretes de compromisso sao dela; ela pede ao Jarvis que mande o aviso ao Dono
        from . import agenda, contexto
        for t in agenda.lembretes(agora, lambda texto: enviar(contexto.contato("dono") or "Eu", texto)):
            _contar(f"Compasso lembrou o Dono de '{t}' (agenda).")
    except Exception:
        pass
    for r in vencidas(agora):
        p = montar_pedido(r, agora)
        motivo = checar(p, r, agora)
        if motivo:
            p.update(status="recusado", motivo=motivo)
            if motivo in ("fora do horário permitido",):
                continue                                   # tenta de novo no proximo tick dentro da janela, sem poluir o log
        else:
            try:
                res = str(executar(p, enviar))
            except Exception as e:
                res = f"erro: {str(e)[:120]}"
            ok = res.startswith("✅")
            p.update(status="feito" if ok else "falhou", resultado=res[:200])
        _anotar_pedido(p)
        tentativas = sum(1 for x in _pedidos_hoje(agora.strftime("%Y-%m-%d")) if x.get("rotina") == r["id"] and x.get("status") == "falhou")
        if p["status"] in ("feito", "recusado") or tentativas >= 3:   # 'falhou' (WhatsApp fechado etc.) tenta de novo, no maximo 3 vezes no dia
            with LOCK:
                d = _ler()
                for x in d["rotinas"]:
                    if x["id"] == r["id"]:
                        x["ultima"] = agora.strftime("%Y-%m-%d")
                _gravar(d)
        _contar(f"Compasso acionou o Jarvis para a rotina '{r['titulo']}': {p['status']}" + (f" ({p.get('motivo') or p.get('resultado', '')[:80]})" if p["status"] != "feito" else "."))
        feitos.append(p)
    return feitos


# ---------- COMPASSO: agente de rotina das IAs e do Dono (26/10/2026) ----------
# A rotina saiu da Alma. O Compasso guarda as rotinas (acima), os lembretes da agenda do Dono e acompanha o que os outros agentes fazem
# pelo barramento (tipo 'status'); a Alma ficou so com observar/aprender/cuidar (alma_cuida.py).
SITUACAO = PASTA / "agentes.json"


def _migrar():
    """Rotinas e pedidos antigos viviam em data/alma/: copia uma vez para data/compasso/ (nada e apagado)."""
    antigo = DATA / "alma"
    for nome in ("rotinas.json", "pedidos.jsonl"):
        if (antigo / nome).exists() and not (PASTA / nome).exists():
            PASTA.mkdir(parents=True, exist_ok=True)
            (PASTA / nome).write_bytes((antigo / nome).read_bytes())


def acompanhar(agora=None):
    """Le a caixa do Compasso no barramento e guarda o ultimo status de cada agente. Devolve quantos recados leu."""
    from . import barramento
    agora = agora or datetime.now()
    try:
        s = json.loads(SITUACAO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        s = {}
    n = 0
    for m in barramento.caixa("Compasso", n=50):
        barramento.marcar_lida(m["id"])
        if m["tipo"] == "status":
            s[m["de"]] = {"quando": datetime.fromtimestamp(m["ts"]).strftime("%d/%m %H:%M"), "texto": m["texto"][:160]}
            n += 1
    if n:
        PASTA.mkdir(parents=True, exist_ok=True)
        SITUACAO.write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
    return n


def painel_agentes():
    """{agente: {quando, texto}} do ultimo status que cada agente mandou ao Compasso."""
    acompanhar()
    try:
        return json.loads(SITUACAO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


_migrar()
