# -*- coding: utf-8 -*-
"""MUDO do Jarvis (pedido do Dono, 08/10/2026): quando ele estiver falando demais.

Mudo = o Jarvis NAO FALA em voz alta (alto-falante do notebook). O texto continua aparecendo normalmente.
Opcoes: 10 min, 1 hora ou ate desmutar. Interruptor separado (padrao DESLIGADO): tambem nao mandar AUDIO no WhatsApp
para o Dono (vai por escrito). Audios para clientes e hospedes NUNCA sao afetados por este modulo.
Se o Jarvis estiver falando na hora de mutar, a fala e cortada (a escuta observa o evento CORTAR)."""
import json, re, threading, time, unicodedata

CORTAR = threading.Event()   # setado ao mutar: a fala em andamento para na hora
_lock = threading.Lock()
SEMPRE = -1                  # 'ate' = -1: mudo ate desmutar


def _arq():
    from . import store       # lido na hora: os testes isolam store.DATA
    return store.DATA / "mudo.json"


def _ler():
    try:
        d = json.loads(_arq().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _gravar(d):
    a = _arq()
    a.parent.mkdir(parents=True, exist_ok=True)
    a.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def ativo(agora=None):
    """True se o Jarvis esta mudo agora (o prazo de 10 min / 1 h expira sozinho)."""
    ate = _ler().get("ate", 0)
    return ate == SEMPRE or (ate > 0 and (agora or time.time()) < ate)


def mutar(minutos=None):
    """minutos=None (ou 0): ate desmutar. Corta a fala que estiver tocando."""
    with _lock:
        d = _ler()
        d["ate"] = SEMPRE if not minutos else time.time() + float(minutos) * 60
        _gravar(d)
    CORTAR.set()
    return estado()


def desmutar():
    with _lock:
        d = _ler()
        d["ate"] = 0
        _gravar(d)
    CORTAR.clear()
    return estado()


def definir_whatsapp_dono(ligado):
    """Interruptor: com o mudo ativo, tambem nao manda AUDIO no WhatsApp para o Dono (manda texto)."""
    with _lock:
        d = _ler()
        d["whatsapp_dono"] = bool(ligado)
        _gravar(d)
    return estado()


def bloqueia_audio_dono():
    """Audio para o DONO no WhatsApp deve virar texto agora? So se mudo ativo E o interruptor ligado."""
    return ativo() and bool(_ler().get("whatsapp_dono", False))


def estado():
    d = _ler()
    ate = d.get("ate", 0)
    mudo = ativo()
    restante = None if not mudo or ate == SEMPRE else max(1, int((ate - time.time()) / 60 + 0.99))
    return {"mudo": mudo, "ate_desmutar": mudo and ate == SEMPRE, "restante_min": restante,
            "whatsapp_dono": bool(d.get("whatsapp_dono", False))}


def _norm(x):
    s = "".join(c for c in unicodedata.normalize("NFD", str(x).lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", s)).strip()


_MUTAR = re.compile(r"^(?:jarvis )?(?:silencio|cala a boca|cala boca|fica quieto|fica calado|mudo|modo mudo|muta|mutar|para de falar|pare de falar)(?: jarvis)?(?: por favor)?$")
_DESMUTAR = re.compile(r"^(?:jarvis )?(?:desmuta|desmutar|tira do mudo|sai do mudo|pode falar|pode voltar a falar|volta a falar)(?: jarvis)?(?: por favor)?$")


def comando(texto):
    """'mutar' / 'desmutar' / None. So frases CURTAS que sao so o comando ('Jarvis, silencio', 'cala a boca', 'mudo')."""
    n = _norm(texto)
    if not n or len(n) > 40:
        return None
    if _MUTAR.match(n):
        return "mutar"
    if _DESMUTAR.match(n) and ativo():   # 'pode falar' so desmuta se estiver mudo (senao e conversa normal: 'pode falar, sou todo ouvidos')
        return "desmutar"
    return None
