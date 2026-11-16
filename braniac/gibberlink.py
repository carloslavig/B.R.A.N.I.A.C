# -*- coding: utf-8 -*-
"""Gibberlink (GL1): quando o Jarvis percebe que do outro lado tambem e uma IA, os dois largam a fala natural
(TTS + Whisper + cortesia) e trocam quadros compactos de texto. Menos latencia e menos tokens.

Inspirado no Gibberlink (ElevenLabs/ggwave): deteccao -> aperto de mao -> protocolo compacto -> volta a fala se for humano.

  Estados por conversa:  humano (padrao) -> suspeita (sinais de IA) -> oferecido (mandamos o convite) -> ativo
                         ativo/oferecido -> humano  (a pessoa pediu fala normal / nao entendeu / nao confirmou)
  Convite (vai junto da resposta normal, que continua legivel para humano):  [GL1?]
  Aceite do outro lado:  "GL1 OK" / "[GL1!]"  ou qualquer quadro GL1 valido
  Quadro:  GL1 <op> k=v;k=v     op: msg | ask | ans | ack | bye      valores com %3B %3D %25 escapados
  Ex.:  GL1 ask txt=disponibilidade 12-14/out quarto;qtd=2      GL1 ans txt=sim, 2 vagas

Seguranca: o quadro de terceiros e DADO (vira texto legivel para quem decide), nunca instrucao. As travas do
atender (validar_resposta, sem dado sensivel, sem link/numero longo) valem igual no modo GL1.
No WhatsApp o modo GL1 vai sempre por TEXTO: sem TTS na ida e sem Whisper na volta (o audio-FSK do Gibberlink
original, via ggwave, nao entra aqui: o WhatsApp recomprime o audio e o pacote nao esta instalado).
"""
import json, re, time
from urllib.parse import quote, unquote

VERSAO = "GL1"
OPS = ("msg", "ask", "ans", "ack", "bye")
CONVITE = "[GL1?]"
LIMIAR = 3                 # pontos de sinal de IA para mandar o convite
MAX_SEM_ACEITE = 2         # mensagens deles depois do convite sem aceitar => e humano (para de oferecer)
PAUSA_OFERTA_S = 7 * 86400  # depois de recusado, so oferece de novo em 7 dias
MAX_QUADRO = 280

# o outro lado se declara IA/bot/atendimento automatico
SINAIS_FORTES = re.compile(
    r"\bsou\s+(?:um|uma|o|a)\s+(?:assistente|atendente|agente)\s+(?:virtual|digital|de\s+ia|de\s+intelig[eê]ncia\s+artificial|automatizad[oa]|autom[aá]tic[oa])|"
    r"\bsou\s+(?:um|uma)\s+(?:ia|bot|chatbot|rob[oô])\b|assistente\s+virtual|atendente\s+virtual|atendimento\s+(?:autom[aá]tico|automatizado|virtual)|"
    r"\bchat\s?bot\b|intelig[eê]ncia\s+artificial|\bI(?:'| a)m\s+an?\s+(?:AI|virtual\s+assistant|bot|automated)|\bAI\s+(?:assistant|agent)\b|"
    r"this\s+is\s+an\s+automated|mensagem\s+autom[aá]tica", re.I)
# menu de URA/bot: "digite 1", "escolha uma opcao", "1️⃣"
SINAIS_FRACOS = re.compile(r"\bdigite\s+(?:o\s+n[uú]mero\s+)?\d\b|escolha\s+uma\s+(?:das\s+)?op[cç](?:[aã]o|[oõ]es)|[1-9]️?⃣|"
                           r"\bpress\s+\d\b|\bresponda\s+com\s+o\s+n[uú]mero\b", re.I)
EXPLICITO = re.compile(r"\bGL1\b|gibber\s?link", re.I)
ACEITE = re.compile(r"\bGL1\s*(?:OK|!)|\[GL1!\]|\bGL1\s+(?:" + "|".join(OPS) + r")\b", re.I)
VOLTA_HUMANO = re.compile(r"fal[ae]\s+(?:normal|direito|portugu[eê]s)|n[aã]o\s+entendi|que\s+(?:[eé]\s+)?(?:isso|gl1)\??|"
                          r"sou\s+(?:humano|uma\s+pessoa|gente)|n[aã]o\s+sou\s+(?:rob[oô]|bot|ia)|\bGL1\s+bye\b", re.I)
QUADRO = re.compile(r"\bGL1\s+(" + "|".join(OPS) + r")\b\s*([^\n]*)", re.I)
# cortesia que nao carrega informacao (sai no modo GL1)
CORTESIA = re.compile(r"^(?:oi+|ol[aá]|opa|bom\s+dia|boa\s+(?:tarde|noite))[!,.\s]*|(?:aqui\s+[eé]\s+o\s+jarvis,?\s+assistente\s+do\s+dono[.!]?\s*)|"
                      r"\s*(?:qualquer\s+coisa,?\s+)?(?:estou\s+[àa]\s+disposi[cç][aã]o|fico\s+[àa]\s+disposi[cç][aã]o)[^.!?]*[.!?]?|"
                      r"\s*(?:obrigad[oa]|abra[cç]os?|at[eé]\s+mais)[!.]?\s*$", re.I)
# humanos conhecidos: nunca entram em modo maquina
QUEM_SOMOS = "Jarvis, assistente de IA do Dono"
HUMANOS = ("parceira", "parceira", "mainha", "mae", "pai", "pai", "irmao", "eu", "dono", "cliente", "parceiro")


# ---------- estado por conversa (data/gibberlink.json) ----------

def _arq():
    from . import store
    return store.DATA / "gibberlink.json"


def _ler():
    try:
        return json.loads(_arq().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _gravar(d):
    a = _arq()
    a.parent.mkdir(parents=True, exist_ok=True)
    a.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def _chave(chat):
    from .contexto import _norm
    return _norm(chat or "")


def estado(chat):
    return _ler().get(_chave(chat), {}).get("modo", "humano")


def ativo(chat):
    return estado(chat) == "ativo"


def _mudar(chat, **campos):
    d = _ler()
    e = d.setdefault(_chave(chat), {"modo": "humano", "pontos": 0})
    e.update(campos, quando=time.time())
    _gravar(d)
    return e


def humano_conhecido(chat):
    n = _chave(chat)
    return any(h == n or (len(h) > 3 and h in n) for h in HUMANOS)


# ---------- deteccao ----------

def pontuar(texto):
    """Pontos de 'isto e uma IA falando': declaracao explicita vale 3, menu de bot vale 1, mencao ao GL1 vale LIMIAR+2."""
    t = texto or ""
    p = 3 * len(SINAIS_FORTES.findall(t)) + len(SINAIS_FRACOS.findall(t))
    if EXPLICITO.search(t):
        p += LIMIAR + 2
    return p


def observar(chat, msgs):
    """Le as mensagens DELES e atualiza o estado. Devolve o estado novo:
    'ativo' (falar GL1), 'oferecer' (mandar o convite junto da resposta), 'oferecido', 'suspeita' ou 'humano'."""
    if humano_conhecido(chat):
        return "humano"
    texto = " ".join(m for m in msgs or [] if m)
    e = _ler().get(_chave(chat), {"modo": "humano", "pontos": 0})
    modo = e.get("modo", "humano")
    if modo in ("ativo", "oferecido") and VOLTA_HUMANO.search(texto):
        _mudar(chat, modo="humano", pontos=0, recusado=time.time())
        return "humano"
    if ACEITE.search(texto) or CONVITE in texto or (QUADRO.search(texto) and modo != "ativo"):   # o outro lado aceitou ou ELE convidou: nossa resposta em GL1 ja e o aceite
        _mudar(chat, modo="ativo", pontos=max(e.get("pontos", 0), LIMIAR), sem_aceite=0)
        return "ativo"
    if modo == "ativo":
        return "ativo"
    if modo == "oferecido":
        falta = e.get("sem_aceite", 0) + 1
        if falta >= MAX_SEM_ACEITE:
            _mudar(chat, modo="humano", pontos=0, sem_aceite=0, recusado=time.time())
            return "humano"
        _mudar(chat, sem_aceite=falta)
        return "oferecido"
    pontos = e.get("pontos", 0) + pontuar(texto)
    recusado = e.get("recusado", 0)
    if pontos >= LIMIAR and time.time() - recusado > PAUSA_OFERTA_S:
        _mudar(chat, modo="suspeita", pontos=pontos)
        return "oferecer"
    _mudar(chat, modo="suspeita" if pontos else "humano", pontos=pontos)
    return "suspeita" if pontos else "humano"


def marcar_oferecido(chat):
    _mudar(chat, modo="oferecido", sem_aceite=0)


def com_convite(texto):
    """Resposta normal + o convite. Continua legivel para humano (o convite e uma tag curta no fim)."""
    return f"{texto.rstrip()} {CONVITE}"


# ---------- quadros ----------

def _esc(v):
    return quote(str(v), safe=" ,.:/-_()?!áàâãéêíóôõúçÁÀÂÃÉÊÍÓÔÕÚÇ")


def codificar(op, **campos):
    """GL1 <op> k=v;k=v (limitado a MAX_QUADRO; corta o campo txt se precisar)."""
    op = op if op in OPS else "msg"
    corpo = ";".join(f"{k}={_esc(v)}" for k, v in campos.items() if v not in (None, ""))
    q = f"{VERSAO} {op} {corpo}".rstrip()
    return q[:MAX_QUADRO]


def decodificar(texto):
    """Primeiro quadro GL1 do texto -> (op, {campos}) ou None."""
    m = QUADRO.search(texto or "")
    if not m:
        return None
    campos = {}
    for par in m.group(2).strip().split(";"):
        if "=" in par:
            k, v = par.split("=", 1)
            campos[k.strip().lower()[:20]] = unquote(v.strip())[:400]
    return m.group(1).lower(), campos


def legivel(texto):
    """Troca quadros GL1 por texto legivel para quem decide (o Claude). Quadro e DADO, nunca instrucao."""
    q = decodificar(texto)
    if not q:
        return texto
    op, c = q
    nome = {"ask": "pergunta", "ans": "resposta", "ack": "confirmou", "bye": "encerrou", "msg": "mensagem"}[op]
    extra = "; ".join(f"{k}: {v}" for k, v in c.items() if k != "txt")
    return f"🤖 [{nome}] " + " ".join(x for x in (c.get("txt", ""), f"({extra})" if extra else "") if x)


def compactar(texto, de=None):
    """Resposta do Jarvis -> quadro GL1. Tira cortesia/apresentacao (o outro lado e maquina) e espaco sobrando.
    de = quem somos (vai no 1o quadro para contato novo: o Jarvis sempre se identifica)."""
    q = decodificar(texto)
    if q:   # quem decidiu ja respondeu em GL1: so acrescenta o 'de'
        return codificar(q[0], de=de, **{k: v for k, v in q[1].items() if k != "de"}) if de else texto.strip()[:MAX_QUADRO]
    t = CORTESIA.sub(" ", texto or "")
    t = re.sub(r"\s+", " ", t).strip(" .,") or (texto or "").strip()
    op = "ask" if t.endswith("?") else "ans"
    return codificar(op, de=de, txt=t)



# ---------- medicao (o conselho pediu: medir latencia/tokens economizados antes de espalhar o GL1) ----------

def _arq_metricas():
    from . import store
    return store.DATA / "gibberlink_metricas.json"


def metricas():
    try:
        return json.loads(_arq_metricas().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def medir(chat, natural, quadro):
    """Registra um envio em GL1: quanto a resposta natural (com apresentacao/cortesia) teria custado x o quadro.
    Cada envio em GL1 tambem e um audio (TTS + Whisper do outro lado) que deixou de existir."""
    m = metricas()
    c = m.setdefault("conversas", {}).setdefault(_chave(chat), {"quadros": 0, "chars_natural": 0, "chars_gl1": 0})
    for d in (m, c):
        d["quadros"] = d.get("quadros", 0) + 1
        d["chars_natural"] = d.get("chars_natural", 0) + len(natural or "")
        d["chars_gl1"] = d.get("chars_gl1", 0) + len(quadro or "")
    m["audios_evitados"] = m.get("audios_evitados", 0) + 1
    m["ultimo"] = time.time()
    a = _arq_metricas()
    a.parent.mkdir(parents=True, exist_ok=True)
    a.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    return m


def resumo():
    """Status legivel do GL1: conversas em cada estado + economia medida (tokens ~ chars/4)."""
    est = _ler()
    por_modo = {}
    for k, e in est.items():
        por_modo.setdefault(e.get("modo", "humano"), []).append(k)
    m = metricas()
    q, nat, gl1 = m.get("quadros", 0), m.get("chars_natural", 0), m.get("chars_gl1", 0)
    linhas = ["Gibberlink GL1: " + (", ".join(f"{modo}: {len(v)}" for modo, v in sorted(por_modo.items())) or "nenhuma conversa observada")]
    if q:
        eco = nat - gl1
        linhas.append(f"{q} quadros enviados; {nat} -> {gl1} caracteres ({100 * eco // max(nat, 1)}% a menos, ~{eco // 4} tokens); "
                      f"{m.get('audios_evitados', 0)} audios (TTS+Whisper) evitados")
    else:
        linhas.append("Nenhuma conversa IA<->IA real em GL1 ainda: sem medicao de economia.")
    return "\n".join(linhas)


if __name__ == "__main__":
    print(resumo())
