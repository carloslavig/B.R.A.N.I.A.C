# -*- coding: utf-8 -*-
"""Adapters das IAs de nuvem (ChatGPT, Gemini) pelo navegador do assistente. UM adapter por IA, isolado: as paginas mudam e quebram a
automacao, entao cada IA e uma peca trocavel. Nunca resolve captcha nem login (a pessoa entra na propria conta). Uso: so perguntas gerais /
sobre a propria pessoa, nunca conteudo de terceiros. Os termos de cada site podem restringir automacao: e uma camada OPCIONAL."""
import itertools, json, time
from . import navegador

_ids = itertools.count(1)


class IAWebErro(RuntimeError):
    pass


ADAPTERS = {
    "chatgpt": {
        "titulo": "ChatGPT", "dominio": "chatgpt.com", "url": "https://chatgpt.com/",
        "entrada": "#prompt-textarea", "enviar": '[data-testid="send-button"]', "resposta": '[data-message-author-role="assistant"]',
        "parar": "!!document.querySelector('[data-testid=\"stop-button\"]')",
        "deslogado": "!!document.querySelector('[data-testid=\"login-button\"]') || /log in|entrar|sign up|cadastre/i.test((document.querySelector('header')||document.body).innerText.slice(0,400))",
    },
    "gemini": {
        "titulo": "Gemini", "dominio": "gemini.google.com", "url": "https://gemini.google.com/app",
        "entrada": "rich-textarea .ql-editor", "enviar": None, "resposta": "model-response .model-response-text, model-response message-content",
        "parar": "[...document.querySelectorAll('button')].some(b=>/parar|stop|interromper/i.test(b.getAttribute('aria-label')||''))",
        "deslogado": "[...document.querySelectorAll('a,button')].some(e=>/fazer login|sign in|^entrar$/i.test((e.innerText||'').trim()))",
    },
}


class _Aba:
    def __init__(self, site):
        self.site = site

    def __enter__(self):
        import websocket
        a = navegador.aba_de(self.site["dominio"])
        if not a:
            raise IAWebErro(f"{self.site['titulo']}: aba não aberta")
        self.id = a["id"]
        self.ws = websocket.create_connection(a["webSocketDebuggerUrl"], timeout=30, suppress_origin=True, max_size=16 * 1024 * 1024)
        return self

    def __exit__(self, *a):
        self.ws.close()

    def cmd(self, method, params=None):
        mid = next(_ids)
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == mid:
                if "error" in m:
                    raise IAWebErro(f"{method}: {m['error']}")
                return m.get("result", {})

    def js(self, expr):
        r = self.cmd("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True})
        if r.get("exceptionDetails"):
            raise IAWebErro(str(r["exceptionDetails"])[:200])
        return r.get("result", {}).get("value")

    def enter(self):
        for tipo in ("keyDown", "keyUp"):
            self.cmd("Input.dispatchKeyEvent", {"type": tipo, "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13, "text": "\r" if tipo == "keyDown" else ""})


def _estado_js(s):
    return (f"JSON.stringify({{caixa: !!document.querySelector({json.dumps(s['entrada'])}), parar: {s['parar']}, deslogado: {s['deslogado']},"
            f" captcha: /verify you are human|confirme que voc|captcha/i.test(document.body.innerText.slice(0,3000)),"
            f" n: document.querySelectorAll({json.dumps(s['resposta'])}).length}})")


def _ultima_js(s):
    return f"(function(){{var m=document.querySelectorAll({json.dumps(s['resposta'])});return m.length? m[m.length-1].innerText : ''}})()"


def logado(ia):
    """True/False se a pessoa ja entrou na conta; None se a aba ainda nao esta aberta/carregada."""
    s = ADAPTERS[ia]
    try:
        with _Aba(s) as a:
            est = json.loads(a.js(_estado_js(s)))
    except Exception:
        return None
    return bool(est["caixa"]) and not est["deslogado"]


def perguntar(ia, texto, timeout_s=150, url_conversa=None):
    with navegador.LOCK:
        return _perguntar(ia, texto, timeout_s, url_conversa)


def _perguntar(ia, texto, timeout_s, url_conversa):
    """Envia `texto` numa conversa NOVA da IA e devolve a resposta. `url_conversa` permite abrir dentro de um projeto especifico."""
    s = ADAPTERS[ia]
    navegador.abrir_aba(s["url"])
    with _Aba(s) as a:
        a.cmd("Page.navigate", {"url": url_conversa or s["url"]})
        time.sleep(4)
        for _ in range(12):
            est = json.loads(a.js(_estado_js(s)))
            if est["caixa"] and est["n"] == 0:
                break
            time.sleep(1)
        est = json.loads(a.js(_estado_js(s)))
        if est["captcha"]:
            raise IAWebErro("verificação de segurança: a pessoa precisa concluir no navegador")
        if est["deslogado"] or not est["caixa"]:
            raise IAWebErro(f"{s['titulo']}: conta não conectada")
        n0, antes = est["n"], a.js(_ultima_js(s)) or ""
        a.js(f"document.querySelector({json.dumps(s['entrada'])}).focus()")
        a.cmd("Input.insertText", {"text": texto})
        time.sleep(0.8)
        if s["enviar"]:
            a.js(f"(function(){{var b=document.querySelector({json.dumps(s['enviar'])}); if(b) b.click()}})()")
        else:
            a.enter()
        fim, anterior, estavel = time.time() + timeout_s, "", None
        while time.time() < fim:
            time.sleep(1.5)
            est = json.loads(a.js(_estado_js(s)))
            if est["n"] <= n0:
                continue
            atual = a.js(_ultima_js(s)) or ""
            if (antes and atual == antes) or " ".join(atual.split())[:80] == " ".join(texto.split())[:80]:
                continue
            if est["parar"] or atual != anterior:
                anterior, estavel = atual, None
                continue
            estavel = estavel or time.time()
            if time.time() - estavel >= 3 and atual.strip():
                return atual.strip()
        raise IAWebErro(f"{s['titulo']}: tempo esgotado esperando a resposta")
