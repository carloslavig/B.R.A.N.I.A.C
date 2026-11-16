# -*- coding: utf-8 -*-
"""Monitor das conversas do Dono (13/11/2026): o Jarvis acompanha a lista do WhatsApp e, por padrao, FICA QUIETO.
So age quando o Dono escreve num chat um comando dirigido a ele. Hoje: "Jarvis, se apresente" -> manda ali um AUDIO
com a apresentacao padrao. Audio do Dono (so mostra a duracao na lista) nao e lido: la ele precisa escrever o comando."""
import re

PEDIDO = re.compile(r"(?i)\bjarvis\b[\s,:;!.-]*(?:(?:por favor|pf|pfv|agora|aqui|pode|ent[aã]o)[\s,]+)*(?:se\s+apresent\w*|apresent\w*[- ]?se|se\s+apresenta)\b")

APRESENTACAO = ("Oi, aqui é o Jarvis. Eu sou o assistente de inteligência artificial do Dono, um sistema autônomo que ele criou "
                "para ajudar no atendimento e nas tarefas do dia a dia. Qualquer coisa que precisarem, é só falar comigo por aqui.")


def pedido_de_apresentacao(resumo):
    """True se a previa da conversa (ultima mensagem DO DONO) pede para o Jarvis se apresentar."""
    return bool(PEDIDO.search(resumo or ""))


def apresentar(nome, enviar_voz=None, gerar=None):
    """Manda a apresentacao em audio para `nome`. Devolve o resultado (comeca com ✅ se enviou)."""
    from . import contexto
    if enviar_voz is None or gerar is None:
        from . import voz, wpp_voz
        enviar_voz, gerar = wpp_voz.enviar_voz, voz.falar_wav
    r = enviar_voz(nome, gerar(APRESENTACAO))
    if str(r).startswith("✅"):
        contexto.marcar_apresentado(nome)
    return r


# ---------- comando por VOZ: o Dono nao le bem, entao fala. A lista so mostra a duracao do audio dele ----------
import json
import time

from .store import DATA

ARQ_ENVIOS = DATA / "audios_jarvis.json"
DURACAO = re.compile(r"(?:^|\|)\s*(\d{1,2}):(\d{2})\s*$")
MAX_AUDIO_S, JANELA_JARVIS_S, MAX_POR_HORA = 60, 600, 6


def _norm(n):
    return re.sub(r"\W+", "", (n or "").lower())


def registrar_envio(nome, agora=None):
    """Chamado por wpp_voz.enviar_voz: guarda quando o Jarvis mandou audio nesse chat (tambem aparece como 'nosso' na lista)."""
    try:
        v = json.loads(ARQ_ENVIOS.read_text(encoding="utf-8"))
    except Exception:
        v = []
    v = [x for x in v if (agora or time.time()) - x[1] < 3600][-40:] + [[_norm(nome), agora or time.time()]]
    DATA.mkdir(exist_ok=True)
    ARQ_ENVIOS.write_text(json.dumps(v), encoding="utf-8")


def audio_curto_do_dono(linha, agora=None):
    """True se a ultima mensagem do chat e um audio NOSSO curto que o Jarvis nao enviou agora a pouco (= o Dono falou no celular)."""
    if not linha.get("nossa"):
        return False
    m = DURACAO.search(linha.get("resumo") or "")
    if not m or int(m.group(1)) * 60 + int(m.group(2)) > MAX_AUDIO_S:
        return False
    try:
        v = json.loads(ARQ_ENVIOS.read_text(encoding="utf-8"))
    except Exception:
        v = []
    return not any(x[0] == _norm(linha["nome"]) and (agora or time.time()) - x[1] < JANELA_JARVIS_S for x in v)


def ouvir_audio_do_dono(nome):
    """Transcreve o ultimo audio do Dono nesse chat (Whisper local). Devolve o texto ou ''."""
    from . import wpp_voz
    txt, erro = wpp_voz.ouvir_ultimo_audio(nome, 1, so_nossos=True)
    return txt or ""


# ---------- comandos do Dono dentro de uma conversa (texto ou voz) ----------
_J = r"\bjarvis\b[\s,:;!.-]*(?:(?:por favor|pf|pfv|agora|ent[aã]o|olha|ei|aqui)[\s,]+)*"
SILENCIAR = re.compile(_J + r"(?:(?:pare|para|parar)\s+de\s+(?:falar|responder|mandar)|n[aã]o\s+quero\s+que\s+(?:voc[eê]|vc|tu)\s+(?:responda|fale|diga|mande)"
                       r"|n[aã]o\s+(?:responda|fale|responde|fala)\b|(?:fique|fica)\s+(?:quieto|calado|em\s+sil[eê]ncio))", re.I)
LIBERAR = re.compile(_J + r"(?:(?:pode\s+)?(?:volt\w+)\s+a\s+(?:responder|falar)|pode\s+(?:responder|falar)\s+(?:de\s+novo|novamente|nessa\s+conversa|com\s+ele|com\s+ela))", re.I)
FALAR = re.compile(_J + r"(?:fale|fala|diga|diz|avise|avisa|passe|passa|repasse|repassa|mande|manda)\s+"
                   r"(?:isso(?:\s+(?:daqui|aqui))?|essa\s+informa\w+|a\s+informa\w+|que|pra\s+(?:ela|ele|pessoa)|para\s+(?:ela|ele|a\s+pessoa))\b[\s:,.-]*"
                   r"(?:(?:pra|para)\s+(?:ela|ele|a\s+pessoa)\b[\s:,.-]*)?(?P<c>.*)", re.I | re.S)
MAX_FALA = 600


def interpretar(texto):
    """(acao, conteudo) do comando do Dono: 'silenciar' | 'liberar' | 'apresentar' | 'falar' (conteudo = o que dizer) ; (None, '') se nao for comando."""
    t = texto or ""
    if SILENCIAR.search(t):
        return "silenciar", ""
    if LIBERAR.search(t):
        return "liberar", ""
    if PEDIDO.search(t):
        return "apresentar", ""
    m = FALAR.search(t)
    if m and m.group("c").strip():
        return "falar", re.sub(r"\s+", " ", m.group("c")).strip()[:MAX_FALA]
    return None, ""


def falar(nome, texto):
    """Diz `texto` em audio (voz do Jarvis) nessa conversa, a pedido do Dono."""
    from . import voz, wpp_voz
    return wpp_voz.enviar_voz(nome, voz.falar_wav(texto))


def executar(nome, acao, conteudo, apresentar_fn=None, falar_fn=None):
    """Silenciar: o Jarvis NAO responde mais esse chat (so fala se o Dono mandar 'fale/passe isso'). Liberar desfaz."""
    from . import contexto
    if acao == "silenciar":
        contexto.silenciar(nome, True)
        return "silenciado (sem aviso na conversa)"
    if acao == "liberar":
        contexto.silenciar(nome, False)
        return "liberado"
    if acao == "apresentar":
        return (apresentar_fn or apresentar)(nome)
    if acao == "falar":
        return (falar_fn or falar)(nome, conteudo)
    return "nada"
