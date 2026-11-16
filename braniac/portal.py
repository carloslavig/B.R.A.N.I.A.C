# -*- coding: utf-8 -*-
"""PORTAL REMOTO (16/11/2026): porta de entrada web para usar o Braniac de qualquer lugar, com o PC como servidor.
Servidor separado em 127.0.0.1:8780 (o Braniac continua so em 127.0.0.1:8765). Um tunel cloudflared expoe SO esta porta.
Seguranca: senha so como hash scrypt; trava por IP e global; dispositivo novo exige codigo de 6 digitos enviado ao WhatsApp do Dono
(outbox); cookies HttpOnly+Secure+SameSite=Strict; Origin checado; sessao com validade; registro e revogacao de dispositivos; log.
Depois do login o portal repassa tudo ao Braniac (menos /api/remoto*), trocando Host/Origin e tirando cookies.
Uso: python -m braniac.portal --definir-senha USUARIO SENHA | --servir"""
import hashlib
import http.client
import json
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DADOS = Path(__file__).resolve().parent / "data"
ARQ = DADOS / "portal.json"
LOG = DADOS / "portal.log"
URL_ARQ = DADOS / "portal_url.txt"
OUTBOX = DADOS / "outbox_dono.txt"
PORTA, DESTINO = 8780, 8765
SESSAO_S, CONFIAVEL_S, CODIGO_S = 24 * 3600, 30 * 24 * 3600, 300
_L = threading.Lock()
_falhas = {}          # ip -> [tempos]
_falhas_g = []        # tempos de todas as falhas
_codigos = {}         # id do dispositivo -> (codigo, expira, tentativas)


def _ler():
    try:
        return json.loads(ARQ.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _gravar(d):
    DADOS.mkdir(exist_ok=True)
    ARQ.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def _log(msg):
    with LOG.open("a", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")


def _avisar(texto):
    with OUTBOX.open("a", encoding="utf-8") as f:
        f.write(("\n---\n" if OUTBOX.exists() and OUTBOX.stat().st_size else "") + texto)


def _hash(senha, sal):
    return hashlib.scrypt(senha.encode(), salt=bytes.fromhex(sal), n=2 ** 14, r=8, p=1, dklen=32).hex()


def definir_senha(usuario, senha):
    d = _ler()
    sal = secrets.token_hex(16)
    d.update(usuario=usuario.lower(), sal=sal, hash=_hash(senha, sal))
    d.setdefault("dispositivos", {})
    d.setdefault("sessoes", {})
    _gravar(d)


def _tok(t):
    return hashlib.sha256(t.encode()).hexdigest()


def _bloqueado(ip):
    agora = time.time()
    with _L:
        _falhas_g[:] = [t for t in _falhas_g if agora - t < 3600]
        r = [t for t in _falhas.get(ip, []) if agora - t < 900]
        _falhas[ip] = r
        return len(r) >= 5 or len(_falhas_g) >= 20


def _falhou(ip, motivo):
    with _L:
        _falhas.setdefault(ip, []).append(time.time())
        _falhas_g.append(time.time())
    _log(f"FALHA {motivo} ip={ip}")
    time.sleep(1)


def _nome_disp(ua):
    so = next((n for k, n in (("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"), ("Windows", "Windows"), ("Mac OS", "Mac"), ("Linux", "Linux")) if k in ua), "?")
    nav = next((n for k, n in (("Edg/", "Edge"), ("Firefox", "Firefox"), ("Chrome", "Chrome"), ("Safari", "Safari")) if k in ua), "navegador")
    return f"{so} · {nav}"


def _sessao_valida(tok):
    """Devolve (dispositivo_id) se a sessao existe, nao expirou e o dispositivo nao foi revogado."""
    if not tok:
        return None
    with _L:
        d = _ler()
        s = d.get("sessoes", {}).get(_tok(tok))
        if not s or s["exp"] < time.time() or d["dispositivos"].get(s["disp"], {}).get("status") != "ativo":
            return None
        return s["disp"]


def _cookie(h, nome):
    m = re.search(rf"(?:^|;\s*){nome}=([A-Za-z0-9_-]+)", h or "")
    return m.group(1) if m else None


PAG_LOGIN = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>Braniac</title>
<style>body{font:16px system-ui;background:#0e1411;color:#e6efe8;display:grid;place-items:center;min-height:100vh;margin:0}
form{width:min(340px,90vw);display:grid;gap:12px}h1{font-size:22px;margin:0 0 4px}input,button{font:inherit;padding:12px;border-radius:10px;border:1px solid #2c3d33;background:#16201a;color:inherit}
button{background:#3ecf8e;color:#06130c;border:0;font-weight:600}#m{min-height:1.2em;color:#f2b8b8;font-size:14px}</style>
<form id=f><h1>Braniac · acesso remoto</h1><input id=u placeholder=Usuário autocomplete=username autocapitalize=off>
<input id=s type=password placeholder=Senha autocomplete=current-password><input id=c placeholder="Código do WhatsApp" inputmode=numeric hidden>
<button>Entrar</button><div id=m></div></form>
<script>f.onsubmit=async e=>{e.preventDefault();m.textContent='';const r=await fetch('/portal/login',{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify({usuario:u.value,senha:s.value,codigo:c.value})});const j=await r.json().catch(()=>({}));
if(j.ok)location='/';else if(j.precisa_codigo){c.hidden=false;c.focus();m.style.color='#9fd';m.textContent='Dispositivo novo: digite o código enviado ao seu WhatsApp.'}else m.textContent=j.erro||'Erro'}</script>"""

PAG_DISP = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>Dispositivos</title>
<style>body{font:15px system-ui;background:#0e1411;color:#e6efe8;max-width:720px;margin:20px auto;padding:0 16px}table{width:100%;border-collapse:collapse}
td,th{padding:8px 6px;border-bottom:1px solid #2c3d33;text-align:left;font-size:13px}button{padding:6px 10px;border-radius:8px;border:0;background:#c0392b;color:#fff}a{color:#3ecf8e}</style>
<h2>Dispositivos conectados</h2><p><a href="/">← Braniac</a> · <button onclick="x('/portal/api/revogar-todos')">Sair de todos</button> <button onclick="x('/portal/logout')" style="background:#555">Sair</button></p>
<table id=t></table><script>
async function x(u,b){await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})});if(u.includes('logout'))location='/portal/login';else l()}
async function l(){const j=await (await fetch('/portal/api/dispositivos')).json();t.innerHTML='<tr><th>Dispositivo<th>IP<th>Último acesso<th>Logins<th></tr>'+j.map(d=>
`<tr><td>${d.nome}${d.atual?' <b>(este)</b>':''}<br><small>desde ${d.primeiro}</small><td>${d.ip}<td>${d.ultimo}<td>${d.logins}<td>${d.status=='ativo'?`<button onclick="x('/portal/api/revogar',{id:'${d.id}'})">Revogar</button>`:'revogado'}</tr>`).join('')}l()</script>"""


def montar():
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def _ip(self):
            return self.headers.get("Cf-Connecting-Ip") or self.client_address[0]

        def _resp(self, corpo, codigo=200, tipo="application/json", extra=()):
            b = corpo if isinstance(corpo, bytes) else (corpo if isinstance(corpo, str) else json.dumps(corpo, ensure_ascii=False)).encode()
            self.send_response(codigo)
            for k, v in (("Content-Type", tipo + "; charset=utf-8"), ("Content-Length", str(len(b))), ("Cache-Control", "no-store"),
                         ("X-Content-Type-Options", "nosniff"), ("X-Frame-Options", "DENY"), ("Referrer-Policy", "no-referrer"),
                         ("Strict-Transport-Security", "max-age=31536000")) + tuple(extra):
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(b)

        def _corpo(self):
            n = int(self.headers.get("Content-Length") or 0)
            try:
                return json.loads(self.rfile.read(min(n, 20000)) or b"{}") if n else {}
            except ValueError:
                return {}

        def _origem_ok(self):
            o = self.headers.get("Origin")
            return o is None or o.split("://", 1)[-1] == self.headers.get("Host")

        def do_GET(self):
            self._tratar()

        do_POST = do_PUT = do_DELETE = do_GET

        def _tratar(self):
            p = self.path.split("?")[0]
            post = self.command != "GET"
            if post and not self._origem_ok():
                return self._resp({"erro": "origem negada"}, 403)
            if p == "/portal/login":
                return self._login() if post else self._resp(PAG_LOGIN, tipo="text/html")
            disp = _sessao_valida(_cookie(self.headers.get("Cookie"), "bsess"))
            if not disp:
                if self.command == "GET" and "text/html" in (self.headers.get("Accept") or ""):
                    self.send_response(302)
                    self.send_header("Location", "/portal/login")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                return self._resp({"erro": "nao autenticado"}, 401)
            if p.startswith("/portal/"):
                return self._admin(p, disp, post)
            if p in ("/", "/index.html"):          # a interface antiga nao existe mais: a entrada e o B.R.A.N.I.A.C 1 (/b2)
                self.send_response(302)
                self.send_header("Location", "/b2")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if p.startswith("/api/remoto"):
                return self._resp({"erro": "bloqueado no acesso remoto"}, 403)
            self._proxy(disp)

        def _login(self):
            ip = self._ip()
            if _bloqueado(ip):
                return self._resp({"erro": "Muitas tentativas. Aguarde alguns minutos."}, 429)
            b = self._corpo()
            d = _ler()
            if not d.get("hash"):
                return self._resp({"erro": "Portal sem senha definida."}, 503)
            ok_u = secrets.compare_digest(str(b.get("usuario", "")).lower(), d["usuario"])
            ok_s = secrets.compare_digest(_hash(str(b.get("senha", "")), d["sal"]), d["hash"])
            if not (ok_u and ok_s):
                _falhou(ip, "senha")
                return self._resp({"erro": "Usuário ou senha incorretos."}, 401)
            did = _cookie(self.headers.get("Cookie"), "bdev")
            novo_cookie = ()
            if not did:
                did = secrets.token_urlsafe(24)
                novo_cookie = (("Set-Cookie", f"bdev={did}; Max-Age={10 * 365 * 86400}; Path=/; HttpOnly; Secure; SameSite=Strict"),)
            disp = d["dispositivos"].get(did)
            if not disp or disp["status"] != "ativo" or disp["confianca"] < time.time():
                cod = str(b.get("codigo", "")).strip()
                reg = _codigos.get(did)
                if not cod or not reg or reg[1] < time.time():
                    c = f"{secrets.randbelow(10 ** 6):06d}"
                    _codigos[did] = (c, time.time() + CODIGO_S, 0)
                    _avisar(f"Braniac remoto: dispositivo novo ({_nome_disp(self.headers.get('User-Agent', ''))}, IP {ip}) tentando entrar. "
                            f"Código: {c} (vale 5 min). Se não foi você, ignore e use 'Sair de todos' nos dispositivos.")
                    _log(f"CODIGO enviado ip={ip}")
                    return self._resp({"precisa_codigo": True}, 200, extra=novo_cookie)
                if reg[2] >= 3 or not secrets.compare_digest(cod, reg[0]):
                    _codigos[did] = (reg[0], reg[1], reg[2] + 1)
                    _falhou(ip, "codigo")
                    return self._resp({"erro": "Código incorreto."}, 401, extra=novo_cookie)
                _codigos.pop(did, None)
                disp = {"nome": _nome_disp(self.headers.get("User-Agent", "")), "primeiro": time.strftime("%d/%m/%Y %H:%M"), "logins": 0,
                        "status": "ativo", "confianca": time.time() + CONFIAVEL_S}
            tok = secrets.token_urlsafe(32)
            with _L:
                d = _ler()
                disp.update(ip=ip, ultimo=time.strftime("%d/%m/%Y %H:%M"), logins=disp["logins"] + 1)
                d["dispositivos"][did] = disp
                d["sessoes"] = {k: v for k, v in d["sessoes"].items() if v["exp"] > time.time()}
                d["sessoes"][_tok(tok)] = {"disp": did, "exp": time.time() + SESSAO_S}
                _gravar(d)
            _log(f"LOGIN ok ip={ip} disp={disp['nome']}")
            self._resp({"ok": True}, 200, extra=novo_cookie + (("Set-Cookie", f"bsess={tok}; Max-Age={SESSAO_S}; Path=/; HttpOnly; Secure; SameSite=Strict"),))

        def _admin(self, p, atual, post):
            if p == "/portal/dispositivos":
                return self._resp(PAG_DISP, tipo="text/html")
            if p == "/portal/api/dispositivos":
                d = _ler()
                return self._resp([dict(v, id=k, atual=k == atual) for k, v in d["dispositivos"].items()])
            if not post:
                return self._resp({"erro": "nao encontrado"}, 404)
            with _L:
                d = _ler()
                if p == "/portal/api/revogar":
                    i = self._corpo().get("id")
                    if i in d["dispositivos"]:
                        d["dispositivos"][i]["status"] = "revogado"
                elif p == "/portal/api/revogar-todos":
                    for v in d["dispositivos"].values():
                        v["status"] = "revogado"
                    d["sessoes"] = {}
                elif p == "/portal/logout":
                    d["sessoes"] = {k: v for k, v in d["sessoes"].items() if v["disp"] != atual}
                else:
                    return self._resp({"erro": "nao encontrado"}, 404)
                _gravar(d)
            _log(f"ADMIN {p} disp={atual}")
            self._resp({"ok": True})

        def _proxy(self, disp):
            n = int(self.headers.get("Content-Length") or 0)
            corpo = self.rfile.read(min(n, 50_000_000)) if n else None
            h = {k: v for k, v in self.headers.items() if k.lower() not in ("host", "origin", "cookie", "connection", "content-length", "accept-encoding", "cf-connecting-ip")}
            h["Host"] = f"127.0.0.1:{DESTINO}"
            if self.headers.get("Origin"):
                h["Origin"] = f"http://127.0.0.1:{DESTINO}"
            try:
                c = http.client.HTTPConnection("127.0.0.1", DESTINO, timeout=300)
                c.request(self.command, self.path, body=corpo, headers=h)
                r = c.getresponse()
            except OSError:
                return self._resp({"erro": "Braniac fora do ar no PC"}, 502)
            self.send_response(r.status)
            for k, v in r.getheaders():
                if k.lower() not in ("connection", "transfer-encoding", "content-length", "strict-transport-security", "set-cookie"):
                    self.send_header(k, v)
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Connection", "close")      # sem tamanho conhecido: fecha ao terminar (serve streaming/SSE)
            self.end_headers()
            self.close_connection = True
            try:
                while True:
                    b = r.read1(8192) if hasattr(r, "read1") else r.read(8192)
                    if not b:
                        break
                    self.wfile.write(b)
                    self.wfile.flush()
            except OSError:
                pass
            finally:
                c.close()
    return H


def tunel(intervalo=120):
    """cloudflared rapido so para a porta do portal; o endereco muda se o PC reiniciar: o novo vai ao Dono pelo outbox."""
    exe = shutil.which("cloudflared") or next((p for p in (r"C:\Program Files (x86)\cloudflared\cloudflared.exe", r"C:\Program Files\cloudflared\cloudflared.exe") if Path(p).exists()), None)
    if not exe:
        return
    while True:
        proc = subprocess.Popen([exe, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{PORTA}"], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                text=True, encoding="utf-8", errors="replace", creationflags=0x08000000)
        for linha in proc.stderr:
            m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", linha)
            if m:   # 16/11: só guarda; nunca avisa sozinho (o Dono recebia um link novo a cada queda). Pedir o link: Jarvis/esteira_parceiro 'painel'
                URL_ARQ.write_text(m.group(0), encoding="utf-8")
        proc.wait()
        from . import painel_rede
        if painel_rede.endereco_fixo():   # endereço fixo (Tailscale) pronto: o link provisório não volta
            return
        time.sleep(intervalo)


def servir(com_tunel=True):
    srv = ThreadingHTTPServer(("127.0.0.1", PORTA), montar())
    srv.daemon_threads = True
    from . import painel_rede
    painel_rede._matar_tuneis_velhos(PORTA)      # quick tunnel que sobrou de um Braniac anterior
    if com_tunel and not painel_rede.endereco_fixo():   # 16/11: endereço fixo (Tailscale) no lugar do link que mudava
        threading.Thread(target=tunel, daemon=True, name="portal_tunel").start()
    print(f"Portal remoto em http://127.0.0.1:{PORTA}", flush=True)
    srv.serve_forever()


def iniciar():
    threading.Thread(target=servir, daemon=True, name="portal").start()


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--definir-senha":
        definir_senha(sys.argv[2], sys.argv[3])
        print("senha gravada (hash)")
    else:
        servir()
