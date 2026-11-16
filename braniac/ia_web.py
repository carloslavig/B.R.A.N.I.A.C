# -*- coding: utf-8 -*-
"""IAs de nuvem pelas abas logadas do Chrome do agente (porta 9222), uma por site: ChatGPT, Gemini, Grok, DeepSeek.
Sem API: digita, envia, espera a resposta estabilizar e le o texto. Nunca resolve captcha nem login: se aparecer, levanta IAWebErro
e o roteador pula para o proximo provedor. Uso restrito a assuntos gerais/criativos: NUNCA conteudo de WhatsApp, dados pessoais de terceiros ou segredos.
Os termos de cada site podem proibir automacao: uso por conta do Dono."""
import http.client, itertools, json, time
import websocket

HOST, PORT = "127.0.0.1", 9222
_ids = itertools.count(1)


class IAWebErro(RuntimeError):
    pass


# entrada: seletor da caixa; enviar: seletor do botao (None = tecla Enter); resposta: seletor das respostas (a ultima vale);
# parar: expressao JS que e verdadeira enquanto ainda esta respondendo; nova: URL de conversa nova
SITES = {
    "chatgpt": {
        "dominio": "chatgpt.com", "nova": "https://chatgpt.com/",
        # as REUNIOES do conselho de IAs ficam todas neste projeto do ChatGPT (Dono, 06/10), para nao misturar com o resto do historico
        "projeto": "https://chatgpt.com/g/g-p-seu_projeto-reunioes-das-ias/project",
        "entrada": "#prompt-textarea, div.ProseMirror[contenteditable=true]", "enviar": '[data-testid="send-button"], button[aria-label*="Enviar"]',
        "resposta": '[data-message-author-role="assistant"], [data-markdown-text-style="assistant-message"]',
        "parar": "!!document.querySelector('[data-testid=\"stop-button\"]')",
        "deslogado": "!!document.querySelector('[data-testid=\"login-button\"]')",
    },
    "gemini": {
        "dominio": "gemini.google.com", "nova": "https://gemini.google.com/app",
        "entrada": "rich-textarea .ql-editor", "enviar": 'button[aria-label="Enviar mensagem"]',
        "resposta": "model-response .model-response-text, model-response message-content",
        "parar": "[...document.querySelectorAll('button')].some(b=>/parar|stop|interromper/i.test(b.getAttribute('aria-label')||''))",
        "deslogado": "[...document.querySelectorAll('a,button')].some(e=>/fazer login|sign in/i.test(e.innerText||''))",
    },
    "grok": {
        "dominio": "grok.com", "nova": "https://grok.com/",
        "entrada": ".ProseMirror", "enviar": '[data-testid="chat-submit"]',
        "resposta": ".response-content-markdown",
        "parar": "[...document.querySelectorAll('button')].some(b=>/parar|stop/i.test(b.getAttribute('aria-label')||''))",
        "deslogado": "[...document.querySelectorAll('a,button')].some(e=>/^(sign in|log in|entrar)$/i.test((e.innerText||'').trim()))",
    },
    "deepseek": {   # 24/10/2026: 4o membro do conselho (conta do Dono); envia pelo botao redondo, a resposta e o ultimo bloco .ds-markdown
        "dominio": "chat.deepseek.com", "nova": "https://chat.deepseek.com/",
        "entrada": "textarea", "enviar": ".ds-button--primary.ds-button--filled.ds-button--circle",   # Enter nao envia la
        "resposta": ".ds-markdown",
        "parar": "[...document.querySelectorAll('[role=button],button')].some(b=>/parar|stop/i.test(b.getAttribute('aria-label')||''))",
        "deslogado": "!!document.querySelector('input[type=password]') || /sign_in/.test(location.pathname)",
    },
    "kimi": {   # 24/10/2026: 5o membro (Dono loga com Google em kimi.ai); seletor da resposta ainda nao conferido logado
        "dominio": "kimi.com", "nova": "https://www.kimi.com/",
        "entrada": ".chat-input-editor", "enviar": ".send-button-container",
        "resposta": ".segment-content-box, .markdown-container, .markdown",
        "parar": "!!document.querySelector('.send-button-container.stop, [class*=stop]')",
        "deslogado": "!!document.querySelector('.login-button-text')",
    },
    "meta": {   # 27/10/2026: Meta AI, uso principal = IMAGENS realistas (gerar_imagem); seletor da resposta de texto NAO conferido logado
        "dominio": "meta.ai", "nova": "https://www.meta.ai/",
        "entrada": "textarea[placeholder^='Pergunte'], input[placeholder^='Pergunte'], input[placeholder^='Descreva']", "enviar": 'button[aria-label="Enviar"]',
        "resposta": "[data-testid*=message], [class*=markdown], [class*=response]",
        "parar": "[...document.querySelectorAll('button')].some(b=>/parar|stop/i.test(b.getAttribute('aria-label')||''))",
        "deslogado": "false",
    },
}


def _aba(dominio, abrir=None):
    """WebSocket da aba do site; se nao existe e `abrir` (url) foi dado, abre uma aba nova (IA sob demanda). Devolve (ws, id_da_aba)."""
    for a in _abas_json():
        if a.get("type") == "page" and dominio in a.get("url", ""):
            return a["webSocketDebuggerUrl"], a["id"]
    if not abrir:
        raise IAWebErro(f"aba de {dominio} nao encontrada no Chrome do agente")
    c = http.client.HTTPConnection(HOST, PORT, timeout=10)
    c.request("PUT", "/json/new?" + abrir)
    a = json.loads(c.getresponse().read())
    c.close()
    time.sleep(3)
    return a["webSocketDebuggerUrl"], a["id"]


def _fechar_aba(id_aba):
    try:
        c = http.client.HTTPConnection(HOST, PORT, timeout=5)
        c.request("GET", "/json/close/" + id_aba)
        c.getresponse().read()
        c.close()
    except (OSError, http.client.HTTPException):
        pass


class _Aba:
    def __init__(self, site):
        self.site = site

    def __enter__(self):
        self.url, self.id_aba = _aba(self.site["dominio"], self.site.get("nova"))
        self.ws = websocket.create_connection(self.url, timeout=30, suppress_origin=True, max_size=16 * 1024 * 1024)
        return self

    def __exit__(self, *a):
        self.ws.close()
        if self.site.get("fechar", True):      # 27/10: IA do conselho abre sob demanda e fecha ao terminar (economiza ~250MB por aba)
            _fechar_aba(self.id_aba)

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
            self.cmd("Input.dispatchKeyEvent", {"type": tipo, "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13,
                                                "text": "\r" if tipo == "keyDown" else ""})


def _estado_js(site):
    return (f"JSON.stringify({{caixa: !!document.querySelector({json.dumps(site['entrada'])}), parar: {site['parar']},"
            f" deslogado: {site['deslogado']}, captcha: /verify you are human|confirme que voc|captcha/i.test(document.body.innerText.slice(0,3000)),"
            f" n: document.querySelectorAll({json.dumps(site['resposta'])}).length}})")


def _ultima_js(site):
    return (f"(function(){{var m=document.querySelectorAll({json.dumps(site['resposta'])});"
            f"return m.length? m[m.length-1].innerText : ''}})()")


def _devolver_foco_ao_whatsapp():
    """Chrome so renderiza/clica na aba da frente: ao terminar, o WhatsApp volta para a frente."""
    try:
        for alvo in _abas_json():
            if alvo.get("type") == "page" and "web.whatsapp.com" in alvo.get("url", ""):
                ws = websocket.create_connection(alvo["webSocketDebuggerUrl"], timeout=10, suppress_origin=True)
                for i, (m, p) in enumerate((("Target.activateTarget", {"targetId": alvo["id"]}), ("Page.bringToFront", {})), 1):
                    ws.send(json.dumps({"id": i, "method": m, "params": p}))
                    ws.recv()
                ws.close()
                return
    except Exception:
        pass


def _abas_json():
    c = http.client.HTTPConnection(HOST, PORT, timeout=5)
    c.request("GET", "/json")
    r = json.loads(c.getresponse().read())
    c.close()
    return r


def perguntar(nome_site, texto, timeout_s=150, nova_conversa=True, reuniao=False, projeto_url=None):
    """Envia `texto` ao site (chatgpt|gemini|grok) e devolve a resposta (str). Levanta IAWebErro se algo impedir.
    Trabalha sob o lock do WhatsApp (so uma aba fica na frente por vez) e devolve o foco ao WhatsApp no fim."""
    from . import whatsapp
    with whatsapp.LOCK:
        try:
            return _perguntar(nome_site, texto, timeout_s, nova_conversa, reuniao, projeto_url)
        finally:
            _devolver_foco_ao_whatsapp()


def _perguntar(nome_site, texto, timeout_s, nova_conversa, reuniao=False, projeto_url=None):
    site = SITES[nome_site]
    with _Aba(site) as a:
        try:  # janela minimizada = abas 'hidden' e a resposta nunca renderiza: restaura e deixa fora da area visivel
            j = a.cmd("Browser.getWindowForTarget")
            if (j.get("bounds") or {}).get("windowState") == "minimized":
                a.cmd("Browser.setWindowBounds", {"windowId": j["windowId"], "bounds": {"windowState": "normal"}})
                a.cmd("Browser.setWindowBounds", {"windowId": j["windowId"],
                                                  "bounds": {"left": -2600, "top": 40, "width": 1280, "height": 900}})
        except IAWebErro:
            pass
        a.cmd("Target.activateTarget", {"targetId": a.url.rstrip("/").split("/")[-1]})
        a.cmd("Page.bringToFront")
        time.sleep(0.8)
        if nova_conversa:
            a.cmd("Page.navigate", {"url": projeto_url or (site.get("projeto") if reuniao else None) or site["nova"]})   # reuniao: abre a conversa DENTRO do projeto
            time.sleep(4)
            for _ in range(10):  # espera a conversa NOVA carregar (sem respostas antigas na tela) antes de digitar
                est = json.loads(a.js(_estado_js(site)))
                if est["caixa"] and est["n"] == 0:
                    break
                time.sleep(1)
        est = json.loads(a.js(_estado_js(site)))
        if est["captcha"]:
            raise IAWebErro("captcha/verificacao: precisa do Dono")
        if est["deslogado"] or not est["caixa"]:
            raise IAWebErro(f"{nome_site}: deslogado ou caixa de mensagem indisponivel")
        n0 = est["n"]
        texto_antes = a.js(_ultima_js(site)) or ""  # o que ja estava na tela: nunca vale como resposta
        a.js(f"document.querySelector({json.dumps(site['entrada'])}).focus()")
        a.cmd("Input.insertText", {"text": texto})
        time.sleep(0.8)
        if site["enviar"]:
            a.js(f"(function(){{var b=document.querySelector({json.dumps(site['enviar'])}); if(b) b.click()}})()")
        else:
            a.enter()
        fim = time.time() + timeout_s
        anterior, estavel_desde = "", None
        alvo_id = a.url.rstrip("/").split("/")[-1]
        while time.time() < fim:
            time.sleep(1.5)
            try:   # aba escondida e 'congelada' pelo Chrome (a resposta para de aparecer e parece cortada): mantem na frente enquanto espera
                a.cmd("Target.activateTarget", {"targetId": alvo_id})
                a.cmd("Page.bringToFront")
            except IAWebErro:
                pass
            est = json.loads(a.js(_estado_js(site)))
            if est["captcha"]:
                raise IAWebErro("captcha/verificacao: precisa do Dono")
            if est["n"] <= n0:
                continue
            atual = a.js(_ultima_js(site)) or ""
            if texto_antes and atual == texto_antes:
                continue
            if " ".join(atual.split())[:80] == " ".join(texto.split())[:80]:
                continue  # em alguns sites a bolha da PERGUNTA usa o mesmo seletor: isso e eco, ainda nao e a resposta
            if est["parar"] or atual != anterior:
                anterior, estavel_desde = atual, None
                continue
            estavel_desde = estavel_desde or time.time()
            if time.time() - estavel_desde >= 8 and atual.strip():
                return atual.strip()
        raise IAWebErro(f"{nome_site}: tempo esgotado esperando a resposta")


_IMGS_JS = ("JSON.stringify([...document.querySelectorAll('img')].filter(i=>i.naturalWidth>=512).map(i=>i.currentSrc||i.src))")


def gerar_imagem(prompt, timeout_s=180):
    """Pede uma imagem ao Meta AI (aba logada) e salva em data/imagens/. Devolve a lista de arquivos. So prompt de imagem: nada pessoal."""
    from pathlib import Path
    from . import whatsapp
    from .store import DATA
    site = SITES["meta"]
    with whatsapp.LOCK:
        try:
            with _Aba(site) as a:
                a.cmd("Target.activateTarget", {"targetId": a.url.rstrip("/").split("/")[-1]})
                a.cmd("Page.bringToFront")
                a.cmd("Page.navigate", {"url": site["nova"]})
                time.sleep(5)
                if a.js("!!document.querySelector('input[type=password]')"):
                    raise IAWebErro("meta: precisa de login (o Dono entra na aba do Meta AI)")
                if not a.js(f"!!document.querySelector({json.dumps(site['entrada'])})"):
                    raise IAWebErro("meta: caixa de mensagem indisponivel")
                antes = set(json.loads(a.js(_IMGS_JS)))
                a.js(f"document.querySelector({json.dumps(site['entrada'])}).focus()")
                a.cmd("Input.insertText", {"text": "Gere uma imagem realista: " + prompt})
                time.sleep(0.8)
                a.js(f"(function(){{var b=document.querySelector({json.dumps(site['enviar'])}); if(b) b.click()}})()")
                fim, ult, desde = time.time() + timeout_s, None, None
                while time.time() < fim:
                    time.sleep(2)
                    novas = [u for u in json.loads(a.js(_IMGS_JS)) if u not in antes]
                    if novas and novas == ult:
                        desde = desde or time.time()
                        if time.time() - desde >= 6:
                            break
                    else:
                        ult, desde = novas, None
                else:
                    raise IAWebErro("meta: nao apareceu imagem (login/limite?)")
                pasta = DATA / "imagens"
                pasta.mkdir(exist_ok=True)
                saidas = []
                for i, u in enumerate(ult[:4], 1):
                    b64 = a.js("fetch(%s).then(r=>r.blob()).then(b=>new Promise(o=>{var f=new FileReader();f.onload=()=>o(f.result.split(',')[1]);f.readAsDataURL(b)}))" % json.dumps(u))
                    import base64
                    p = pasta / f"meta-{time.strftime('%Y%m%d-%H%M%S')}-{i}.jpg"
                    p.write_bytes(base64.b64decode(b64))
                    saidas.append(str(p))
                return saidas
        finally:
            _devolver_foco_ao_whatsapp()
