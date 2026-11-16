# -*- coding: utf-8 -*-
"""PORTA LAN TEMPORARIA (07/11/2026): uma porta (8766) so na rede local para o Claude do Mac mandar ARQUIVOS ao PC.
Nao ha como provar 'conta Anthropic' pela rede: a prova e a CHAVE (data/porta_lan.key, nova a cada subida). Cada pedido leva
HMAC-SHA256(chave, ts|nonce|metodo|caminho|sha256-do-corpo): sem a chave nao entra, pedido repetido ou velho e recusado.
So IP de rede privada, 5 erros bloqueiam o IP por 10 min, o servidor se desliga sozinho. Arquivo vai para data/recebidos_lan/
(quarentena: nunca abre nem executa; executavel e recusado). Uso: python -m braniac.porta_lan [--minutos 120] [--ip 192.168.x.x]"""
import argparse
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .store import DATA

PORTA = 8766
PASTA = DATA / "recebidos_lan"
CHAVE = DATA / "porta_lan.key"
LIMITE = 200 * 1024 * 1024
JANELA = 60
EXEC = {".exe", ".bat", ".cmd", ".ps1", ".msi", ".scr", ".vbs", ".lnk", ".dll", ".com", ".jar", ".reg", ".hta"}
_erros = {}          # ip -> [horarios dos erros]
_nonces = {}         # nonce -> ts
_trava = threading.Lock()


def _bloqueado(ip):
    with _trava:
        e = [t for t in _erros.get(ip, []) if time.time() - t < 600]
        _erros[ip] = e
        return len(e) >= 5


def _erro(ip):
    with _trava:
        _erros.setdefault(ip, []).append(time.time())


def assinatura(chave, ts, nonce, metodo, caminho, sha):
    return hmac.new(chave.encode(), f"{ts}|{nonce}|{metodo}|{caminho}|{sha}".encode(), hashlib.sha256).hexdigest()


def nome_seguro(nome):
    n = os.path.basename((nome or "").replace("\\", "/"))
    n = re.sub(r"[^\w.\- ]", "_", n).strip(" .")[:120]
    return n or "arquivo"


def nova_chave():
    PASTA.mkdir(parents=True, exist_ok=True)
    k = secrets.token_hex(32)
    CHAVE.write_text(k, encoding="utf-8")
    return k


class _H(BaseHTTPRequestHandler):
    chave = ""

    def log_message(self, *a):
        pass

    def _json(self, cod, obj):
        d = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(cod)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(d)))
        self.end_headers()
        self.wfile.write(d)

    def _auth(self, sha):
        """None se ok; senao (codigo, motivo)."""
        ip = self.client_address[0]
        try:
            if not ipaddress.ip_address(ip).is_private:
                return 403, "ip fora da rede local"
        except ValueError:
            return 403, "ip invalido"
        if _bloqueado(ip):
            return 429, "bloqueado por excesso de erros"
        h = self.headers
        ts, nonce, sig = h.get("X-Braniac-Ts", ""), h.get("X-Braniac-Nonce", ""), h.get("X-Braniac-Sig", "")
        ok = ts.isdigit() and abs(time.time() - int(ts)) <= JANELA and 8 <= len(nonce) <= 64
        if ok:
            esperado = assinatura(self.chave, ts, nonce, self.command, self.path, sha)
            ok = hmac.compare_digest(esperado, sig)
        if ok:
            with _trava:
                for n in [n for n, t in _nonces.items() if time.time() - t > JANELA * 2]:
                    del _nonces[n]
                if nonce in _nonces:
                    ok = False
                else:
                    _nonces[nonce] = time.time()
        if not ok:
            _erro(ip)
            return 401, "nao autorizado"
        return None

    def do_GET(self):
        if self.path == "/ola":                     # sem chave: so mostra que a porta existe (o Mac acha o PC por aqui)
            return self._json(200, {"braniac": "porta-lan"})
        if self.path == "/ping":
            r = self._auth("")
            return self._json(*r) if r else self._json(200, {"ok": True, "hora": time.strftime("%H:%M:%S")})
        self._json(404, {"erro": "nao existe"})

    def do_POST(self):
        if not self.path.startswith("/arquivo?nome="):
            return self._json(404, {"erro": "nao existe"})
        sha = self.headers.get("X-Body-Sha256", "").lower()
        try:
            tam = int(self.headers.get("Content-Length", ""))
        except ValueError:
            return self._json(411, {"erro": "falta Content-Length"})
        r = self._auth(sha)                        # a assinatura cobre o hash declarado: so le o corpo depois de autenticar
        if r:
            return self._json(*r)
        if not re.fullmatch(r"[0-9a-f]{64}", sha) or tam > LIMITE:
            return self._json(413, {"erro": "hash invalido ou arquivo acima de 200 MB"})
        from urllib.parse import parse_qs, urlparse
        nome = nome_seguro(parse_qs(urlparse(self.path).query).get("nome", [""])[0])
        if os.path.splitext(nome)[1].lower() in EXEC:
            return self._json(415, {"erro": "executavel recusado"})
        PASTA.mkdir(parents=True, exist_ok=True)
        tmp = PASTA / f".parcial-{secrets.token_hex(4)}"
        h, falta = hashlib.sha256(), tam
        with open(tmp, "wb") as f:
            while falta > 0:
                b = self.rfile.read(min(1 << 20, falta))
                if not b:
                    break
                f.write(b)
                h.update(b)
                falta -= len(b)
        if falta or h.hexdigest() != sha:
            tmp.unlink(missing_ok=True)
            return self._json(400, {"erro": "arquivo incompleto ou corrompido"})
        dest = PASTA / f"{time.strftime('%Y%m%d-%H%M%S')}-{nome}"
        os.replace(tmp, dest)
        self._json(200, {"ok": True, "salvo_como": dest.name, "bytes": tam})


def iniciar(minutos=120, ip=None, porta=PORTA):
    """Sobe o servidor numa thread; devolve (servidor, chave). Desliga sozinho em `minutos`."""
    ip = ip or ip_lan()
    chave = nova_chave()
    H = type("H", (_H,), {"chave": chave})
    srv = ThreadingHTTPServer((ip, porta), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    t = threading.Timer(minutos * 60, srv.shutdown)
    t.daemon = True
    t.start()
    return srv, chave


def ip_lan():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutos", type=int, default=120)
    ap.add_argument("--ip", default=None)
    a = ap.parse_args()
    srv, _ = iniciar(a.minutos, a.ip)
    print(f"Porta LAN ligada em {srv.server_address[0]}:{srv.server_address[1]} por {a.minutos} min. Chave em {CHAVE}. Arquivos em {PASTA}")
    try:
        time.sleep(a.minutos * 60 + 2)
    except KeyboardInterrupt:
        srv.shutdown()
    print("Porta LAN encerrada.")
