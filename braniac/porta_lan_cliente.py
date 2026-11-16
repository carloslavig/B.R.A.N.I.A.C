# -*- coding: utf-8 -*-
"""Cliente da porta LAN do Braniac (roda no Mac; so biblioteca padrao do Python 3).
  python3 porta_lan_cliente.py achar                       # procura o PC na rede (porta 8766)
  python3 porta_lan_cliente.py --ip 192.168.0.10 --chave-arquivo chave.txt ping
  python3 porta_lan_cliente.py --ip 192.168.0.10 --chave-arquivo chave.txt enviar arq1 arq2 ...
A chave (64 caracteres hex) e o conteudo de braniac/data/porta_lan.key no PC; o Dono copia para o Mac. Nao imprima a chave."""
import argparse
import concurrent.futures
import hashlib
import hmac
import http.client
import json
import os
import secrets
import socket
import time
from urllib.parse import quote

PORTA = 8766


def _assinar(chave, metodo, caminho, sha):
    ts, nonce = str(int(time.time())), secrets.token_hex(12)
    sig = hmac.new(chave.encode(), f"{ts}|{nonce}|{metodo}|{caminho}|{sha}".encode(), hashlib.sha256).hexdigest()
    return {"X-Braniac-Ts": ts, "X-Braniac-Nonce": nonce, "X-Braniac-Sig": sig}


def pedido(ip, chave, metodo, caminho, corpo=None, sha=""):
    h = _assinar(chave, metodo, caminho, sha)
    if corpo is not None:
        h["X-Body-Sha256"] = sha
        h["Content-Length"] = str(os.path.getsize(corpo))
    c = http.client.HTTPConnection(ip, PORTA, timeout=600)
    if corpo is None:
        c.request(metodo, caminho, headers=h)
    else:
        with open(corpo, "rb") as f:
            c.request(metodo, caminho, body=f, headers=h)
    r = c.getresponse()
    return r.status, json.loads(r.read() or b"{}")


def _sha(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _tem(ip):
    try:
        c = http.client.HTTPConnection(ip, PORTA, timeout=0.6)
        c.request("GET", "/ola")
        return ip if b"porta-lan" in c.getresponse().read() else None
    except OSError:
        return None


def achar():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("10.255.255.255", 1))
    base = s.getsockname()[0].rsplit(".", 1)[0]
    s.close()
    with concurrent.futures.ThreadPoolExecutor(64) as ex:
        return [i for i in ex.map(_tem, [f"{base}.{n}" for n in range(1, 255)]) if i]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip")
    ap.add_argument("--chave-arquivo")
    ap.add_argument("comando", choices=["achar", "ping", "enviar"])
    ap.add_argument("arquivos", nargs="*")
    a = ap.parse_args()
    if a.comando == "achar":
        print(achar() or "nao achei")
        raise SystemExit
    chave = open(a.chave_arquivo).read().strip()
    if a.comando == "ping":
        print(pedido(a.ip, chave, "GET", "/ping"))
    else:
        for arq in a.arquivos:
            print(arq, pedido(a.ip, chave, "POST", "/arquivo?nome=" + quote(os.path.basename(arq)), arq, _sha(arq)))
