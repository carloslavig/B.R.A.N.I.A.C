# -*- coding: utf-8 -*-
"""CAIXA DE AVISOS na fila HTTPS (13/11/2026): tudo o que o Braniac diz ao par fica aqui, inteiro e numerado, e o par le com GET /avisos?desde=N.
Motivo: o plano B do Link (ntfy.sh gratis) tem cota de ~250 mensagens/dia e acabou de madrugada, travando a esteira o dia todo.
Enquanto o par ler a caixa (ultima leitura ha menos de ATIVA_S), o aviso conta como entregue sem gastar o ntfy."""
import hashlib
import json
import threading
import time

ATIVA_S = 30 * 60          # par que leu a caixa nos ultimos 30 min esta lendo por ela
REPETIDO_S = 6 * 3600      # o mesmo texto de novo em menos de 6 h e reenvio (o vigia tenta a cada 5 min), nao aviso novo
_LOCK = threading.Lock()


def _arq():
    from ..store import DATA
    return DATA / "link" / "avisos.json"


def _ler():
    try:
        return json.loads(_arq().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"seq": 0, "avisos": [], "leituras": {}}


def _gravar(d):
    _arq().parent.mkdir(parents=True, exist_ok=True)
    tmp = _arq().with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    tmp.replace(_arq())


def guardar(par, texto, agora=None):
    """Poe o aviso na caixa do par. Devolve o numero (o mesmo de antes se for reenvio do mesmo texto)."""
    agora = agora or time.time()
    h = hashlib.sha256(str(texto).encode()).hexdigest()[:16]
    with _LOCK:
        d = _ler()
        for a in reversed(d["avisos"]):
            if a["par"] == par and a["h"] == h and agora - a["quando"] < REPETIDO_S:
                return a["seq"]
        d["seq"] += 1
        d["avisos"] = (d["avisos"] + [{"seq": d["seq"], "par": par, "quando": agora, "h": h, "texto": str(texto)}])[-500:]
        _gravar(d)
        return d["seq"]


def ler(par, desde=0, agora=None):
    """O que o par ainda nao viu (seq > desde). Marca a leitura: a partir dai a caixa vale como entrega."""
    with _LOCK:
        d = _ler()
        d["leituras"][par] = agora or time.time()
        _gravar(d)
    novos = [{"seq": a["seq"], "quando": a["quando"], "texto": a["texto"]} for a in d["avisos"] if a["par"] == par and a["seq"] > int(desde or 0)]
    return {"avisos": novos, "ultimo": d["seq"]}


def ativa(par, agora=None):
    return (agora or time.time()) - _ler()["leituras"].get(par, 0) < ATIVA_S
