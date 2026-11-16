# -*- coding: utf-8 -*-
"""Liga TUDO do Braniac de uma vez (botao da Area de Trabalho): Chrome do Braniac (porta 9222) com WhatsApp, ChatGPT, Gemini, Grok e DeepSeek,
o servidor do Jarvis e a interface. Pode ser rodado varias vezes: so sobe o que ainda nao esta de pe."""
import http.client, json, subprocess, sys, time, urllib.request, webbrowser
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PY = sys.executable.replace("pythonw.exe", "python.exe")
ABAS = {"web.whatsapp.com": "https://web.whatsapp.com/",
        "chatgpt.com": "https://chatgpt.com/g/g-p-SEU_PROJETO-reunioes-das-ias/project",
        "gemini.google.com": "https://gemini.google.com/app", "grok.com": "https://grok.com/",
        "chat.deepseek.com": "https://chat.deepseek.com/", "kimi.com": "https://www.kimi.com/", "meta.ai": "https://www.meta.ai/"}
SEM_JANELA = 0x08000000


def _json(url, t=3):
    try:
        return json.load(urllib.request.urlopen(url, timeout=t))
    except Exception:
        return None


def chrome_ok():
    return _json("http://127.0.0.1:9222/json/version") is not None


def servidor_ok():
    if _json("http://127.0.0.1:8765/api/status", 8) is not None:
        return True
    import socket   # 10/11: servidor ocupado (Whisper) demorava a responder e subiam 2 servidores; porta aberta = ja esta de pe
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", 8765)) == 0


def abas():
    return [a for a in (_json("http://127.0.0.1:9222/json") or []) if a.get("type") == "page"]


def ligar(abrir_interface=True):
    p = print
    if not chrome_ok():
        p("Ligando o navegador do Braniac...")
        bat = RAIZ / "monitor" / "start-chrome-debug.bat"
        subprocess.Popen([str(bat)], cwd=str(bat.parent), creationflags=SEM_JANELA)
        for _ in range(45):
            time.sleep(1)
            if chrome_ok():
                break
    p("Navegador do Braniac:", "OK" if chrome_ok() else "NAO SUBIU")
    if chrome_ok():
        for dominio, url in ABAS.items():
            if not any(dominio in a.get("url", "") for a in abas()):
                c = http.client.HTTPConnection("127.0.0.1", 9222, timeout=10)
                c.request("PUT", "/json/new?" + url)
                c.getresponse().read()
                c.close()
                p("  aba aberta:", dominio)
    if not servidor_ok():
        p("Ligando o Braniac/Jarvis...")
        subprocess.Popen([PY, "-m", "braniac.server"], cwd=str(RAIZ), creationflags=SEM_JANELA)
        for _ in range(40):
            time.sleep(1)
            if servidor_ok():
                break
    p("Braniac/Jarvis:", "OK" if servidor_ok() else "NAO SUBIU")
    if servidor_ok():
        try:
            subprocess.run([PY, "-c", "from braniac import power; power.ligar()"], cwd=str(RAIZ), creationflags=SEM_JANELA, timeout=30)
        except Exception:
            pass
        if abrir_interface:   # o B.R.A.N.I.A.C 2 (janela em Rust) chama com --sem-interface: ele mesmo mostra a tela
            app = RAIZ / "braniac2-app" / "target" / "release" / "braniac2.exe"
            if app.exists():   # 24/10: o Dono quer o PROGRAMA, nao o navegador
                subprocess.Popen([str(app)], cwd=str(RAIZ))
            else:
                webbrowser.open("http://127.0.0.1:8765/b2")
    return chrome_ok() and servidor_ok()


if __name__ == "__main__":
    ok = ligar("--sem-interface" not in sys.argv)
    time.sleep(2 if ok else 12)      # se algo falhou, deixa a janela aberta tempo de ler
    sys.exit(0 if ok else 1)
