# -*- coding: utf-8 -*-
"""Navegador do ASSISTENTE: Edge (ja vem no Windows) ou Chrome, com perfil PROPRIO (nao mexe no navegador da pessoa), controlado por CDP.
Aparece so no login das IAs de nuvem; depois fica escondido fora da tela e so o assistente mexe nele. A pessoa so ve se pedir."""
import http.client, json, os, subprocess, threading, time, urllib.request
from pathlib import Path
from . import paths

PORTA = 9333
LOCK = threading.RLock()   # o navegador do assistente tem UMA aba na frente por vez: ChatGPT, Gemini e WhatsApp revezam sob este lock
class NavegadorErro(RuntimeError):
    pass


def _locais():
    return [os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
            os.environ.get("LOCALAPPDATA", "")]


# id -> (nome, caminhos relativos a Program Files / Program Files (x86) / LocalAppData, prefixo do ProgId que o Windows usa para o navegador padrao)
NAVEGADORES = {
    "chrome": ("Google Chrome", [r"Google\Chrome\Application\chrome.exe"], "ChromeHTML"),
    "edge": ("Microsoft Edge", [r"Microsoft\Edge\Application\msedge.exe"], "MSEdgeHTM"),
    "brave": ("Brave", [r"BraveSoftware\Brave-Browser\Application\brave.exe"], "BraveHTML"),
    "vivaldi": ("Vivaldi", [r"Vivaldi\Application\vivaldi.exe"], "Vivaldi"),
    "opera": ("Opera", [r"Programs\Opera\opera.exe", r"Opera\opera.exe"], "Opera"),
}


def instalados():
    """{id: caminho do .exe} dos navegadores baseados em Chromium (os unicos que o assistente consegue controlar por CDP)."""
    achados = {}
    for id_, (_, rels, _) in NAVEGADORES.items():
        for base in _locais():
            for rel in rels:
                p = Path(base) / rel
                if base and p.exists():
                    achados.setdefault(id_, str(p))
    return achados


def padrao_do_windows():
    """id do navegador padrao do Windows (so se for Chromium), ou None (ex.: Firefox nao da para controlar por CDP)."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice") as k:
            progid = winreg.QueryValueEx(k, "ProgId")[0]
    except Exception:
        return None
    return next((i for i, (_, _, pref) in NAVEGADORES.items() if progid.startswith(pref)), None)


def escolhido(instal=None, padrao="__auto__", preferido=None):
    """Qual navegador o assistente usa: 1) o que a pessoa escolheu; 2) o PADRAO do Windows (se for Chromium); 3) Chrome; 4) Edge (todo Windows tem)."""
    instal = instal if instal is not None else instalados()
    if preferido is None:
        from . import perfil
        preferido = perfil.carregar().get("navegador") or "auto"
    if preferido in instal:
        return preferido
    padrao = padrao_do_windows() if padrao == "__auto__" else padrao
    for c in (padrao, "chrome", "edge", *instal):
        if c in instal:
            return c
    raise NavegadorErro("não encontrei nenhum navegador compatível (Chrome, Edge, Brave, Vivaldi ou Opera) neste PC")


def executavel():
    return instalados()[escolhido()]


def info():
    """Para a tela: lista, o que esta em uso e por que."""
    instal = instalados()
    try:
        usado = escolhido(instal)
    except NavegadorErro:
        usado = None
    from . import perfil
    return {"instalados": {i: NAVEGADORES[i][0] for i in instal}, "usado": usado, "preferido": perfil.carregar().get("navegador") or "auto",
            "padrao_windows": padrao_do_windows()}


def perfil_dir():
    """Perfil PROPRIO do assistente, separado por navegador (nao mexe nas suas abas, senhas nem historico)."""
    d = paths.dados_dir() / ("navegador-" + escolhido())
    d.mkdir(exist_ok=True)
    return d


def trocar(id_):
    """Muda o navegador do assistente (fecha o que estiver aberto para o novo assumir)."""
    from . import perfil
    if id_ != "auto" and id_ not in instalados():
        raise NavegadorErro("esse navegador não está instalado")
    if rodando():
        try:
            import websocket
            ws = websocket.create_connection(_json("/json/version")["webSocketDebuggerUrl"], suppress_origin=True, timeout=5)
            ws.send(json.dumps({"id": 1, "method": "Browser.close"}))
            ws.close()
        except Exception:
            pass
        for _ in range(20):
            if not rodando():
                break
            time.sleep(0.25)
    perfil.atualizar(navegador=id_)


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
