# -*- coding: utf-8 -*-
"""Navegador do ASSISTENTE: Edge (ja vem no Windows) ou Chrome, com perfil PROPRIO (nao mexe no navegador da pessoa), controlado por CDP.
Aparece so no login das IAs de nuvem; depois fica escondido fora da tela e so o assistente mexe nele. A pessoa so ve se pedir."""
import http.client, json, os, subprocess, time, urllib.request
from pathlib import Path
from . import paths

PORTA = 9333
CANDIDATOS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


class NavegadorErro(RuntimeError):
    pass


def executavel():
    for c in CANDIDATOS:
        if Path(c).exists():
            return c
    raise NavegadorErro("não encontrei o Edge nem o Chrome neste PC")


def perfil_dir():
    d = paths.dados_dir() / "navegador"
    d.mkdir(exist_ok=True)
    return d


def _json(caminho, metodo="GET", timeout=4):
    c = http.client.HTTPConnection("127.0.0.1", PORTA, timeout=timeout)
    c.request(metodo, caminho)
    r = c.getresponse()
    corpo = r.read()
    c.close()
    return json.loads(corpo) if corpo else None


def rodando():
    try:
        return bool(_json("/json/version"))
    except Exception:
        return False


def iniciar(url="about:blank"):
    """Sobe o navegador do assistente (se ainda nao estiver de pe)."""
    if rodando():
        return
    subprocess.Popen([executavel(), f"--remote-debugging-port={PORTA}", f"--user-data-dir={perfil_dir()}", "--no-first-run",
                      "--no-default-browser-check", "--disable-background-timer-throttling", "--disable-renderer-backgrounding",
                      "--disable-backgrounding-occluded-windows", "--new-window", url])
    for _ in range(40):
        time.sleep(0.25)
        if rodando():
            return
    raise NavegadorErro("o navegador do assistente não iniciou")


def abas():
    return [a for a in (_json("/json") or []) if a.get("type") == "page"]


def aba_de(dominio):
    for a in abas():
        if dominio in a.get("url", ""):
            return a
    return None


def abrir_aba(url):
    """Abre (ou traz para a frente) uma aba. Garante o navegador de pe."""
    dom = url.split("/")[2]
    iniciar(url)
    a = aba_de(dom)
    if not a:
        _json("/json/new?" + url, "PUT")
        a = aba_de(dom)
    if a:
        _json("/json/activate/" + a["id"])
    return a


def _janela(a, bounds):
    import websocket
    ws = websocket.create_connection(a["webSocketDebuggerUrl"], timeout=10, suppress_origin=True)
    try:
        ws.send(json.dumps({"id": 1, "method": "Browser.getWindowForTarget", "params": {}}))
        r = json.loads(ws.recv())
        wid = r["result"]["windowId"]
        ws.send(json.dumps({"id": 2, "method": "Browser.setWindowBounds", "params": {"windowId": wid, "bounds": bounds}}))
        ws.recv()
    finally:
        ws.close()


def esconder():
    """Tira a janela da vista (fora da tela, sem minimizar: aba minimizada deixa de renderizar e a automacao para)."""
    for a in abas()[:1]:
        _janela(a, {"windowState": "normal"})
        _janela(a, {"left": -2600, "top": 40, "width": 1280, "height": 900})


def mostrar():
    for a in abas()[:1]:
        _janela(a, {"windowState": "normal"})
        _janela(a, {"left": 80, "top": 60, "width": 1100, "height": 800})
        _json("/json/activate/" + a["id"])
