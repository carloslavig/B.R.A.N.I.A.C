# -*- coding: utf-8 -*-
"""Spotify no PC do Dono.
Camada A (sem login): abre o app e usa as teclas de midia do Windows (play/pausa, proxima, anterior, volume) e abre a busca por URI.
Camada B (API oficial do Spotify, login uma vez): procura a musica/artista/playlist pedida e TOCA no app. O controle de reproducao pela API exige Spotify Premium.
Login: PKCE (sem segredo): voce cria um app em developer.spotify.com, cola o Client ID e aprova uma vez em /spotify/login (redirect http://127.0.0.1:8765/spotify/callback).
Tokens ficam so em braniac/data/spotify.json (acesso restrito ao seu usuario do Windows)."""
import base64, hashlib, json, os, re, secrets, subprocess, time, unicodedata, urllib.parse
import requests
from .store import DATA

ARQ = DATA / "spotify.json"
REDIRECT = "http://127.0.0.1:8765/spotify/callback"
ESCOPOS = "user-modify-playback-state user-read-playback-state user-read-currently-playing"
API = "https://api.spotify.com/v1"


class SpotifyErro(Exception):
    pass


def _norm(x):
    s = "".join(c for c in unicodedata.normalize("NFD", str(x).lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", s)).strip()


# ---------- estado salvo ----------

def _ler():
    try:
        return json.loads(ARQ.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _gravar(d):
    DATA.mkdir(exist_ok=True)
    ARQ.write_text(json.dumps(d), encoding="utf-8")


def definir_client_id(cid):
    d = _ler()
    d["client_id"] = (cid or "").strip()
    _gravar(d)


def logado():
    d = _ler()
    return bool(d.get("client_id") and d.get("refresh_token"))


def estado():
    d = _ler()
    return {"client_id": bool(d.get("client_id")), "logado": logado()}


# ---------- login (PKCE) ----------

def url_login():
    d = _ler()
    if not d.get("client_id"):
        raise SpotifyErro("falta o Client ID do app do Spotify (developer.spotify.com)")
    verificador = secrets.token_urlsafe(64)
    d["verificador"] = verificador
    d["estado"] = secrets.token_urlsafe(16)
    _gravar(d)
    desafio = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b"=").decode()
    q = urllib.parse.urlencode({"client_id": d["client_id"], "response_type": "code", "redirect_uri": REDIRECT, "scope": ESCOPOS,
                                "code_challenge_method": "S256", "code_challenge": desafio, "state": d["estado"]})
    return "https://accounts.spotify.com/authorize?" + q


def concluir_login(codigo, estado_recebido):
    d = _ler()
    if not codigo or estado_recebido != d.get("estado"):
        raise SpotifyErro("retorno do login invalido")
    r = requests.post("https://accounts.spotify.com/api/token", data={
        "grant_type": "authorization_code", "code": codigo, "redirect_uri": REDIRECT,
        "client_id": d["client_id"], "code_verifier": d.get("verificador", "")}, timeout=20)
    if r.status_code != 200:
        raise SpotifyErro(f"o Spotify recusou o login ({r.status_code})")
    _guardar_token(r.json())


def _guardar_token(j):
    d = _ler()
    d["access_token"] = j["access_token"]
    d["expira"] = time.time() + int(j.get("expires_in", 3600)) - 60
    if j.get("refresh_token"):
        d["refresh_token"] = j["refresh_token"]
    d.pop("verificador", None)
    _gravar(d)


def _token():
    d = _ler()
    if not d.get("refresh_token"):
        raise SpotifyErro("sem login no Spotify")
    if d.get("access_token") and time.time() < d.get("expira", 0):
        return d["access_token"]
    r = requests.post("https://accounts.spotify.com/api/token", data={
        "grant_type": "refresh_token", "refresh_token": d["refresh_token"], "client_id": d["client_id"]}, timeout=20)
    if r.status_code != 200:
        raise SpotifyErro("o login do Spotify expirou; entre de novo em /spotify/login")
    _guardar_token(r.json())
    return _ler()["access_token"]


def _api(metodo, caminho, **kw):
    r = requests.request(metodo, API + caminho, headers={"Authorization": "Bearer " + _token()}, timeout=20, **kw)
    return r


# ---------- camada A: teclas de midia e app ----------

VK_MIDIA = {"playpause": 0xB3, "proxima": 0xB0, "anterior": 0xB1, "volume_mais": 0xAF, "volume_menos": 0xAE, "mudo": 0xAD}


def tecla(nome, vezes=1):
    import ctypes
    u = ctypes.windll.user32
    for _ in range(vezes):
        u.keybd_event(VK_MIDIA[nome], 0, 0, 0)
        u.keybd_event(VK_MIDIA[nome], 0, 2, 0)
        time.sleep(0.05)


def app_rodando():
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Spotify.exe"], capture_output=True, text=True, timeout=10, creationflags=0x08000000).stdout
        return "Spotify.exe" in out
    except Exception:
        return False


def abrir_app(uri="spotify:"):
    os.startfile(uri)      # o app da Microsoft Store registra o protocolo spotify:


# ---------- camada B: API ----------

def _dispositivo(esperar_s=25):
    """Id do dispositivo do Spotify neste PC (abre o app se preciso e espera aparecer)."""
    fim = time.time() + esperar_s
    aberto = False
    while True:
        r = _api("GET", "/me/player/devices")
        if r.status_code == 200:
            devs = r.json().get("devices", [])
            pc = [d for d in devs if d.get("type") == "Computer"] or devs
            ativo = [d for d in pc if d.get("is_active")]
            if ativo or pc:
                return (ativo or pc)[0]["id"]
        if not aberto:
            abrir_app()
            aberto = True
        if time.time() > fim:
            raise SpotifyErro("o Spotify nao apareceu como dispositivo; abra o app e tente de novo")
        time.sleep(1.5)


def _tocar_uri(device_id, corpo):
    r = _api("PUT", "/me/player/play", params={"device_id": device_id}, json=corpo)
    if r.status_code in (200, 202, 204):
        return
    if r.status_code == 404:    # sem dispositivo ativo: transfere para este e tenta de novo
        _api("PUT", "/me/player", json={"device_ids": [device_id], "play": False})
        time.sleep(1.2)
        r = _api("PUT", "/me/player/play", params={"device_id": device_id}, json=corpo)
        if r.status_code in (200, 202, 204):
            return
    if r.status_code == 403:
        raise SpotifyErro("o Spotify so deixa o controle de reproducao para contas Premium")
    raise SpotifyErro(f"o Spotify recusou o pedido ({r.status_code})")


def escolher(consulta, resultados):
    """Dado o resultado da busca, decide o que tocar: (descricao, corpo_do_play). Playlist so se o pedido disser 'playlist';
    artista inteiro se o nome do artista aparece no pedido e nenhuma faixa bate melhor."""
    q = _norm(consulta)
    pedido_playlist = bool(re.search(r"\bplaylist\b", q))
    tracks = (resultados.get("tracks") or {}).get("items") or []
    artists = (resultados.get("artists") or {}).get("items") or []
    plays = [p for p in ((resultados.get("playlists") or {}).get("items") or []) if p]
    if pedido_playlist and plays:
        p = plays[0]
        return f"a playlist {p['name']}", {"context_uri": p["uri"]}
    melhor, melhor_s = None, 0.0
    qt = set(q.split())
    for t in tracks:
        nome = _norm(t["name"]) + " " + " ".join(_norm(a["name"]) for a in t.get("artists", []))
        s = len(qt & set(nome.split())) / max(1, len(qt))
        if s > melhor_s:
            melhor, melhor_s = t, s
    for a in artists:
        if _norm(a["name"]) and _norm(a["name"]) in q and (melhor is None or _norm(a["name"]) == q or melhor_s < 0.75):
            return f"músicas de {a['name']}", {"context_uri": a["uri"]}
    if melhor:
        return f"{melhor['name']}, de {melhor['artists'][0]['name']}", {"uris": [melhor["uri"]]}
    if tracks:
        t = tracks[0]
        return f"{t['name']}, de {t['artists'][0]['name']}", {"uris": [t["uri"]]}
    return None, None


# ---------- camada A2: aperta o play do "Resultado principal" na tela do app (sem login, sem API) ----------

def _janela_spotify():
    """(hwnd, (esq, topo, larg, alt)) da janela principal do app Spotify, ou None."""
    import ctypes
    from ctypes import wintypes as wt
    u, k = ctypes.windll.user32, ctypes.windll.kernel32
    achadas = []

    def cb(h, _):
        if not u.IsWindowVisible(h):
            return True
        pid = wt.DWORD()
        u.GetWindowThreadProcessId(h, ctypes.byref(pid))
        ph = k.OpenProcess(0x1000, False, pid.value)       # PROCESS_QUERY_LIMITED_INFORMATION
        if not ph:
            return True
        buf = ctypes.create_unicode_buffer(520)
        n = wt.DWORD(520)
        ok = k.QueryFullProcessImageNameW(ph, 0, buf, ctypes.byref(n))
        k.CloseHandle(ph)
        if ok and buf.value.lower().endswith("spotify.exe"):
            r = wt.RECT()
            u.GetWindowRect(h, ctypes.byref(r))
            if (r.right - r.left) > 600 and (r.bottom - r.top) > 400:
                achadas.append((h, (r.left, r.top, r.right - r.left, r.bottom - r.top)))
        return True
    u.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)(cb), 0)
    return achadas[0] if achadas else None


def achar_botao_play(imagem):
    """Centro (x, y) do botao verde de play do 'Resultado principal' na imagem da janela (PIL/numpy), ou None.
    O botao e o unico grande bloco verde Spotify (#1ED760) na parte de cima da area de resultados."""
    import numpy as np
    a = np.asarray(imagem.convert("RGB")).astype(int)
    h, w = a.shape[:2]
    y0, y1, x0, x1 = int(h * 0.10), int(h * 0.45), int(w * 0.28), int(w * 0.92)
    reg = a[y0:y1, x0:x1]
    r, g, b = reg[..., 0], reg[..., 1], reg[..., 2]
    mask = (g > 185) & (r < 110) & (b > 50) & (b < 150) & (g - r > 90)
    if mask.sum() < 500:
        return None
    ys, xs = np.nonzero(mask)
    return int(xs.mean()) + x0, int(ys.mean()) + y0


def _clicar_na_tela(x, y):
    import ctypes
    u = ctypes.windll.user32
    import ctypes.wintypes
    pt = ctypes.wintypes.POINT()
    u.GetCursorPos(ctypes.byref(pt))
    u.SetCursorPos(int(x), int(y))
    time.sleep(0.12)
    u.mouse_event(0x0002, 0, 0, 0, 0)   # botao esquerdo para baixo
    u.mouse_event(0x0004, 0, 0, 0, 0)   # e para cima
    time.sleep(0.15)
    u.SetCursorPos(pt.x, pt.y)          # devolve o mouse onde estava


def tocar_pela_tela(consulta, esperar_s=14):
    """Abre a busca no app e clica no play do 'Resultado principal'. Nao precisa de login nem de API (funciona com o app aberto e visivel)."""
    import ctypes
    from PIL import ImageGrab
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)      # coordenadas em pixels reais, iguais as da captura
    except Exception:
        pass
    abrir_app("spotify:search:" + urllib.parse.quote(consulta))
    fim = time.time() + esperar_s
    time.sleep(2.0)
    while time.time() < fim:
        j = _janela_spotify()
        if j:
            hwnd, (l, t, w, h) = j
            u = ctypes.windll.user32
            u.ShowWindow(hwnd, 9)
            u.keybd_event(0x12, 0, 0, 0); u.keybd_event(0x12, 0, 2, 0)    # truque do Alt: libera o foco
            u.SetForegroundWindow(hwnd)
            time.sleep(0.8)
            img = ImageGrab.grab(bbox=(l, t, l + w, t + h), all_screens=True)
            ponto = achar_botao_play(img)
            if ponto:
                _clicar_na_tela(l + ponto[0], t + ponto[1])
                return True
        time.sleep(1.0)
    return False


def tocar(consulta):
    """Procura e toca. Com login (API): escolhe a melhor faixa/artista/playlist. Sem login: clica no play do resultado principal da busca na tela do app."""
    consulta = (consulta or "").strip()
    if not consulta:
        raise SpotifyErro("diga o que quer ouvir")
    if not logado():
        if tocar_pela_tela(consulta):
            return f"Tocando {consulta} no Spotify."
        return (f"Abri a busca de {consulta} no Spotify, mas não consegui apertar o play sozinho (a janela precisa estar visível). "
                "Com o login da API do Spotify no Braniac isso fica garantido.")
    r = _api("GET", "/search", params={"q": consulta, "type": "track,artist,playlist", "limit": 8, "market": "BR"})
    if r.status_code != 200:
        raise SpotifyErro(f"a busca no Spotify falhou ({r.status_code})")
    desc, corpo = escolher(consulta, r.json())
    if not corpo:
        return f"Não achei nada no Spotify para {consulta}."
    _tocar_uri(_dispositivo(), corpo)
    return f"Tocando {desc}."


def _sessoes_spotify():
    from pycaw.pycaw import AudioUtilities
    return [s for s in AudioUtilities.GetAllSessions() if s.Process and s.Process.name().lower() == "spotify.exe"]


def volume_atual():
    """Volume (0-100) do Spotify no mixer do Windows, ou None se o app ainda nao esta tocando (nao tem sessao de audio)."""
    ses = _sessoes_spotify()
    return round(ses[0].SimpleAudioVolume.GetMasterVolume() * 100) if ses else None


def definir_volume(pct, esperar_s=0):
    """Volume EXATO do Spotify (0-100%) pelo mixer do Windows: so o app muda, a voz do Jarvis e o resto ficam como estao.
    O Spotify so tem sessao de audio depois de tocar: com esperar_s, espera ela aparecer. Devolve o volume aplicado ou None."""
    pct = max(0, min(100, int(pct)))
    fim = time.time() + esperar_s
    while True:
        ses = _sessoes_spotify()
        if ses:
            for s in ses:
                s.SimpleAudioVolume.SetMasterVolume(pct / 100.0, None)
                if pct > 0:
                    s.SimpleAudioVolume.SetMute(0, None)
            return pct
        if time.time() >= fim:
            return None
        time.sleep(0.5)


def ajustar_volume(delta):
    """Sobe/desce o volume do Spotify em `delta` pontos. Sem sessao de audio, usa as teclas de volume do Windows."""
    atual = volume_atual()
    if atual is None:
        tecla("volume_mais" if delta > 0 else "volume_menos", max(1, abs(delta) // 2))
        return None
    return definir_volume(atual + delta)


def controle(acao, valor=None):
    """pausar | continuar | proxima | anterior | volume (0-100) | tocando. Com login usa a API; sem login, as teclas de midia."""
    acao = (acao or "").lower()
    if acao == "volume":
        if valor is None:
            raise SpotifyErro("diga o volume (0 a 100)")
        r = definir_volume(valor, esperar_s=3)
        return f"Volume do Spotify em {r}%." if r is not None else "O Spotify ainda não está tocando; o volume vale quando a música começar."
    if acao in ("volume_mais", "volume_menos"):
        r = ajustar_volume(15 if acao == "volume_mais" else -15)
        return f"Volume em {r}%." if r is not None else "Ajustei o volume."
    if logado():
        try:
            if acao == "pausar":
                _api("PUT", "/me/player/pause"); return "Pausei."
            if acao == "continuar":
                _api("PUT", "/me/player/play"); return "Continuando."
            if acao == "proxima":
                _api("POST", "/me/player/next"); return "Próxima."
            if acao == "anterior":
                _api("POST", "/me/player/previous"); return "Voltando."
            if acao == "tocando":
                r = _api("GET", "/me/player/currently-playing")
                if r.status_code == 200 and r.json().get("item"):
                    i = r.json()["item"]
                    return f"Está tocando {i['name']}, de {i['artists'][0]['name']}."
                return "Não há nada tocando agora."
        except SpotifyErro:
            raise
    teclas = {"pausar": "playpause", "continuar": "playpause", "proxima": "proxima", "anterior": "anterior"}
    if acao in teclas:
        if not app_rodando():
            abrir_app()
        tecla(teclas[acao])
        return {"pausar": "Pausei.", "continuar": "Continuando.", "proxima": "Próxima.", "anterior": "Voltando."}[acao]
    raise SpotifyErro("comando de Spotify desconhecido")
