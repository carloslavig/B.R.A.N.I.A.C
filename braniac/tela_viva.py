# -*- coding: utf-8 -*-
"""TELA VIVA (10/11/2026): mostra no escritorio a aba do Chrome do Braniac (CDP, porta 9222) e repassa clique/tecla do Dono.
So 127.0.0.1, so dominios da lista, nunca digita em campo de credencial, e fica SOMENTE LEITURA enquanto o Braniac esta mexendo no WhatsApp."""
import base64
import json
import urllib.request

DOMINIOS = ("web.whatsapp.com", "airbnb.com.br", "chatgpt.com", "gemini.google.com")
CDP = "http://127.0.0.1:9222"
TECLAS = {"Enter": 13, "Backspace": 8, "Tab": 9, "Escape": 27, "ArrowUp": 38, "ArrowDown": 40, "ArrowLeft": 37, "ArrowRight": 39}


class TelaErro(Exception):
    pass


def _aba(dominio):
    if dominio not in DOMINIOS:
        raise TelaErro("dominio nao permitido")
    try:
        abas = json.load(urllib.request.urlopen(f"{CDP}/json", timeout=3))
    except Exception:
        raise TelaErro("Chrome do Braniac fechado")
    for a in abas:
        if a.get("type") == "page" and dominio in a.get("url", ""):
            return a
    raise TelaErro("aba nao esta aberta")


class _Sessao:
    def __init__(self, aba):
        import websocket
        self.ws = websocket.create_connection(aba["webSocketDebuggerUrl"], timeout=8, suppress_origin=True)
        self.n = 0

    def cmd(self, metodo, params=None):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": metodo, "params": params or {}}))
        while True:
            r = json.loads(self.ws.recv())
            if r.get("id") == self.n:
                if "error" in r:
                    raise TelaErro(str(r["error"].get("message"))[:80])
                return r.get("result", {})

    def fechar(self):
        try:
            self.ws.close()
        except Exception:
            pass


def captura(dominio):
    """{'img': jpeg base64, 'w': largura css, 'h': altura css}. Nao traz a aba para a frente."""
    s = _Sessao(_aba(dominio))
    try:
        v = s.cmd("Page.getLayoutMetrics").get("cssVisualViewport", {})
        img = s.cmd("Page.captureScreenshot", {"format": "jpeg", "quality": 55})["data"]
        return {"img": img, "w": v.get("clientWidth"), "h": v.get("clientHeight")}
    finally:
        s.fechar()


def _agente_agindo():
    from . import whatsapp
    if whatsapp.LOCK.acquire(blocking=False):
        whatsapp.LOCK.release()
        return False
    return True


def acao(dominio, tipo, x=None, y=None, texto=None, tecla=None):
    """tipo: 'clique' (x,y em px css), 'texto' (insere texto), 'tecla' (Enter, Backspace, setas...). Devolve 'ok'."""
    if dominio == "web.whatsapp.com" and _agente_agindo():
        raise TelaErro("o Jarvis esta mexendo no WhatsApp agora; tente em instantes")
    s = _Sessao(_aba(dominio))
    try:
        if tipo == "clique":
            x, y = float(x), float(y)
            for t in ("mousePressed", "mouseReleased"):
                s.cmd("Input.dispatchMouseEvent", {"type": t, "x": x, "y": y, "button": "left", "clickCount": 1})
        elif tipo in ("texto", "tecla"):
            senha = s.cmd("Runtime.evaluate", {"expression": "!!(document.activeElement&&document.activeElement.type==='password')", "returnByValue": True})
            if senha.get("result", {}).get("value"):
                raise TelaErro("campo de senha: digite direto no Chrome, nao pelo painel")
            if tipo == "texto":
                s.cmd("Input.insertText", {"text": str(texto or "")[:500]})
            else:
                if tecla not in TECLAS:
                    raise TelaErro("tecla nao permitida")
                for t in ("rawKeyDown", "keyUp"):
                    s.cmd("Input.dispatchKeyEvent", {"type": t, "key": tecla, "windowsVirtualKeyCode": TECLAS[tecla]})
        else:
            raise TelaErro("acao desconhecida")
        return "ok"
    finally:
        s.fechar()
