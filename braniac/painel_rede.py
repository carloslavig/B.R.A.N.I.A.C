# -*- coding: utf-8 -*-
"""Painel da esteira do Parceiro na rede local (celular, tablet), SO leitura.

Porta propria (8772) em todas as interfaces, separada do Braniac (127.0.0.1:8765): aqui so existem a tela do /parceiro,
os dados em lista branca (lote_parceiro.publico, o mesmo resumo que o Mac do Parceiro ve) e o manifesto/icone para
instalar como app. Qualquer outra rota responde 404: nada do resto do Braniac sai para a rede.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORTA = 8772
UI = Path(__file__).parent / "ui"

MANIFESTO = {"name": "Esteira do Parceiro", "short_name": "Esteira", "start_url": "/", "scope": "/", "display": "standalone",
             "background_color": "#16151A", "theme_color": "#16151A", "lang": "pt-BR",
             "icons": [{"src": "/icone-192.png", "sizes": "192x192", "type": "image/png"},
                       {"src": "/icone-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}]}


def _icone(lado):
    arq = UI / f"parceiro-icone-{lado}.png"
    if not arq.exists():   # desenha uma vez: a grade dos 50 videos, alguns prontos
        from PIL import Image, ImageDraw
        im = Image.new("RGB", (lado, lado), "#16151A")
        d = ImageDraw.Draw(im)
        m, n = lado * 0.2, 5
        passo = (lado - 2 * m) / n
        for i in range(n * n):
            x, y = m + (i % n) * passo, m + (i // n) * passo
            d.rounded_rectangle([x + passo * .08, y + passo * .08, x + passo * .92, y + passo * .92], radius=passo * .18,
                                fill="#2FA36B" if i < 12 else ("#C9A227" if i == 12 else "#2A2930"))
        im.save(arq)
    return arq.read_bytes()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a):   # so IP, hora e rota: ajuda a ver se o celular chegou ate aqui
        try:
            with open(Path(__file__).parent / "data" / "painel_rede.log", "a", encoding="utf-8") as f:
                f.write(f"{self.log_date_time_string()} {self.client_address[0]} {fmt % a}\n")
        except OSError:
            pass

    def _enviar(self, corpo, tipo, codigo=200):
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        rota = self.path.split("?")[0]
        try:
            if rota in ("/", "/parceiro"):
                return self._enviar((UI / "parceiro.html").read_bytes(), "text/html; charset=utf-8")
            if rota == "/api/parceiro":
                from .link import lote_parceiro
                return self._enviar(json.dumps(lote_parceiro.publico(), ensure_ascii=False).encode(), "application/json; charset=utf-8")
            if rota == "/manifest.webmanifest":
                return self._enviar(json.dumps(MANIFESTO, ensure_ascii=False).encode(), "application/manifest+json")
            if rota in ("/icone-192.png", "/icone-512.png"):
                return self._enviar(_icone(int(rota[7:10])), "image/png")
        except Exception as e:
            return self._enviar(json.dumps({"erro": str(e)}).encode(), "application/json", 500)
        self._enviar(b"{}", "application/json", 404)


def servir(porta=PORTA, host="0.0.0.0"):
    ThreadingHTTPServer((host, porta), Handler).serve_forever()


def iniciar(porta=PORTA):
    """Sobe em segundo plano junto com o Braniac; se a porta ja estiver em uso (rodando avulso), so avisa."""
    def rodar():
        try:
            servir(porta)
        except OSError as e:
            print("painel da rede local nao subiu:", e, flush=True)
    threading.Thread(target=rodar, daemon=True, name="painel_rede").start()
    _matar_tuneis_velhos()           # túnel rápido que sobrou de um Braniac anterior (vazavam um por reinício)
    if not endereco_fixo():          # endereço fixo (porteiro com senha no E:) substitui o túnel rápido
        threading.Thread(target=vigiar_tunel, daemon=True, name="painel_tunel").start()


# Endereço FIXO do painel (Dono, 16/11/2026: "não quero que ele fique me mandando link novo"): porteiro com login e senha em
# E:\painel-esteira (Tailscale Funnel, HTTPS). O endereço vai ao Dono SÓ quando ele pede (esteira_parceiro acao "painel").
# Enquanto o fixo não existe, o túnel rápido antigo segue de reserva, mas calado: nunca manda link sozinho.
ENDERECO_FIXO = Path(r"E:\painel-esteira\endereco.txt")


def endereco_fixo():
    try:
        return ENDERECO_FIXO.read_text(encoding="utf-8-sig").strip() or None
    except OSError:
        return None


def endereco():
    """Resposta do Jarvis quando o Dono pede o link do painel."""
    if endereco_fixo():   # raiz = Braniac inteiro (portal); :8443 = só o painel (usuário do Parceiro)
        base = endereco_fixo().rstrip("/")
        return f"Braniac de qualquer lugar (login dono): {base}/  · painel da esteira dentro dele: {base}/parceiro  · só o painel (Parceiro): {base}:8443/"
    if url_publica():
        return f"Painel da esteira (link provisório, o fixo ainda não foi ativado): {url_publica()}"
    return "O painel da esteira ainda não tem endereço fora de casa."


def _matar_tuneis_velhos(porta=PORTA):
    import subprocess
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Get-CimInstance Win32_Process -Filter \"name='cloudflared.exe'\" | ? CommandLine -match "
                        f"'--url http://127.0.0.1:{porta}' | % {{ Stop-Process -Id $_.ProcessId -Force }}"],
                       timeout=30, capture_output=True, creationflags=0x08000000)
    except Exception:
        pass


def _url_arq():
    from .store import DATA
    return DATA / "parceiro" / "painel_url.txt"


def url_publica():
    try:
        return _url_arq().read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def vigiar_tunel(intervalo=120):
    import re
    import shutil
    import subprocess
    import time
    exe = shutil.which("cloudflared") or next((p for p in (r"C:\Program Files (x86)\cloudflared\cloudflared.exe", r"C:\Program Files\cloudflared\cloudflared.exe") if Path(p).exists()), None)
    if not exe:
        return
    while True:
        proc = subprocess.Popen([exe, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{PORTA}"], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                text=True, encoding="utf-8", errors="replace", creationflags=0x08000000)
        for linha in proc.stderr:            # lê até o fim: o cloudflared não pode travar com o pipe cheio
            m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", linha)
            if m and m.group(0) != url_publica():   # só guarda; o Dono pede quando quiser (nunca avisa sozinho)
                _url_arq().parent.mkdir(parents=True, exist_ok=True)
                _url_arq().write_text(m.group(0), encoding="utf-8")
        proc.wait()
        if endereco_fixo():                  # o fixo ficou pronto: o provisório não volta
            return
        time.sleep(intervalo)                # caiu: sobe de novo


if __name__ == "__main__":
    print(f"Painel da esteira na rede local: http://<IP deste PC>:{PORTA}/", flush=True)
    servir()
