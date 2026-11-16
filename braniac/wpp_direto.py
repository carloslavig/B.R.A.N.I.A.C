# -*- coding: utf-8 -*-
"""WhatsApp SEM aba do Chrome (27/10/2026): sidecar Node/Baileys em 127.0.0.1:8766 (wpp_baileys/server.js).
O Chrome continua como reserva ate o Dono parear o QR; so entao a aba do WhatsApp Web pode ser fechada."""
import json
import os
import subprocess
import urllib.request
from pathlib import Path

PORTA = 8766
BASE = f"http://127.0.0.1:{PORTA}"
PASTA = Path(__file__).resolve().parent / "wpp_baileys"


def _chamar(rota, corpo=None, timeout=20):
    req = urllib.request.Request(BASE + rota, data=json.dumps(corpo).encode() if corpo is not None else None,
                                 headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}") | {"http": e.code}
    except (OSError, ValueError):
        return {"estado": "parado"}


def status():
    return _chamar("/status", timeout=3)


def iniciar():
    """Sobe o sidecar (sem janela) se preciso e manda gerar o QR agora. Precisa de `npm install` feito em wpp_baileys/."""
    if status().get("estado") == "parado":      # parado = sidecar fora do ar ("ocioso" = no ar, sem QR)
        if not (PASTA / "node_modules").exists():
            return False
        subprocess.Popen(["node", "server.js"], cwd=PASTA, creationflags=0x08000000 | 0x00000008,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env={**os.environ, "WPP_PORTA": str(PORTA)})
        import time
        for _ in range(20):
            time.sleep(0.5)
            if status().get("estado") != "parado":
                break
    return bool(_chamar("/conectar", {}).get("ok"))


def conectado():
    return status().get("estado") == "conectado"


def enviar(para, texto):
    return _chamar("/enviar", {"para": para, "texto": texto})


def enviar_arquivo(para, caminho, legenda="", voz=False):
    return _chamar("/enviar_arquivo", {"para": para, "caminho": str(caminho), "legenda": legenda, "voz": voz}, timeout=90)


def novas(desde=0):
    r = _chamar("/inbox?desde=%d" % desde)
    return r if isinstance(r, list) else []


def baixar(id_msg, destino):
    return _chamar("/baixar", {"id": id_msg, "destino": str(destino)}, timeout=90)


# ---- nomes -> numero (o Baileys fala em numero; o resto do Braniac fala em nome de contato) ----
CONTATOS = Path(__file__).resolve().parent / "data" / "wpp_contatos.json"


def _chave(n):
    import unicodedata
    return " ".join("".join(c for c in unicodedata.normalize("NFD", n.lower()) if not unicodedata.combining(c)).split())


def _contatos():
    try:
        return json.loads(CONTATOS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def aprender(desde=0):
    """Aprende nome->numero com quem mandou mensagem (pushName) e devolve o maior seq visto. Nao sobrescreve nome ja conhecido."""
    c, maior = _contatos(), desde
    for m in novas(desde):
        maior = max(maior, m["seq"])
        if m.get("nome") and not m.get("minha") and m["de"].endswith("@s.whatsapp.net"):
            c.setdefault(_chave(m["nome"]), m["de"])
    CONTATOS.parent.mkdir(exist_ok=True)
    CONTATOS.write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")
    return maior


def jid_de(nome):
    """So nome IGUAL ao conhecido (a trava de destino do Chrome conferia o titulo; aqui nao ha tela para conferir). Senao devolve None e vale o Chrome."""
    return _contatos().get(_chave(nome))
