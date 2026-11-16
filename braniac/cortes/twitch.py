# -*- coding: utf-8 -*-
"""Twitch: status da live, VODs e clipes. Usa a API oficial (Helix) se houver TWITCH_CLIENT_ID/TWITCH_CLIENT_SECRET no .env;
sem chaves, cai no streamlink (live) e no yt-dlp (VODs/clipes), que nao precisam de cadastro."""
import json, subprocess, time
from datetime import datetime, timedelta, timezone
import requests
from . import config

HELIX = "https://api.twitch.tv/helix"
_token = {"valor": "", "expira": 0}


def tem_api():
    return bool(config.env("TWITCH_CLIENT_ID") and config.env("TWITCH_CLIENT_SECRET"))


def _cabecalhos():
    if time.time() > _token["expira"] - 60:  # token de aplicativo (client credentials): nao envolve login de ninguem
        r = requests.post("https://id.twitch.tv/oauth2/token", timeout=20, params={
            "client_id": config.env("TWITCH_CLIENT_ID"), "client_secret": config.env("TWITCH_CLIENT_SECRET"),
            "grant_type": "client_credentials"})
        r.raise_for_status()
        d = r.json()
        _token.update(valor=d["access_token"], expira=time.time() + d.get("expires_in", 3600))
    return {"Client-ID": config.env("TWITCH_CLIENT_ID"), "Authorization": f"Bearer {_token['valor']}"}


def _get(caminho, **params):
    r = requests.get(HELIX + caminho, headers=_cabecalhos(), params=params, timeout=20)
    r.raise_for_status()
    return r.json().get("data", [])


def _id_usuario(login):
    d = _get("/users", login=login)
    return d[0]["id"] if d else None


def ao_vivo(login):
    """dict com titulo/jogo/inicio se o canal esta ao vivo; None se offline."""
    if tem_api():
        d = _get("/streams", user_login=login)
        if d:
            s = d[0]
            return {"titulo": s.get("title", ""), "jogo": s.get("game_name", ""), "inicio": s.get("started_at", ""), "id": s.get("id")}
        return None
    import streamlink
    try:
        streams = streamlink.Streamlink().streams(f"https://www.twitch.tv/{login}")
    except Exception:
        return None
    return {"titulo": "", "jogo": "", "inicio": "", "id": ""} if streams else None


def _ytdlp_lista(url, n):
    p = subprocess.run(["yt-dlp", "--flat-playlist", "-J", "--playlist-end", str(n), url],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180, creationflags=0x08000000)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip()[-300:])
    return json.loads(p.stdout).get("entries") or []


def clipes_populares(login, janela_h=48, maximo=5, min_views=0):
    """Lista [{id, url, titulo, views, duracao}] dos clipes mais vistos da janela, do mais visto ao menos."""
    if tem_api():
        uid = _id_usuario(login)
        if not uid:
            return []
        desde = (datetime.now(timezone.utc) - timedelta(hours=janela_h)).strftime("%Y-%m-%dT%H:%M:%SZ")
        cs = _get("/clips", broadcaster_id=uid, started_at=desde, first=max(maximo * 3, 20))
        cs = [{"id": c["id"], "url": c["url"], "titulo": c.get("title", ""), "views": c.get("view_count", 0),
               "duracao": c.get("duration", 0)} for c in cs]
    else:
        es = _ytdlp_lista(f"https://www.twitch.tv/{login}/clips?filter=clips&range={'7d' if janela_h <= 168 else '30d'}", maximo * 6)
        desde = time.time() - janela_h * 3600
        cs = [{"id": e.get("id") or e.get("url"), "url": e.get("url") or e.get("webpage_url"), "titulo": e.get("title", ""),
               "views": e.get("view_count") or 0, "duracao": e.get("duration") or 0}
              for e in es if (e.get("timestamp") or time.time()) >= desde]
    ignorar = [t.lower() for t in config.carregar().get("clipes_ignorar_titulos", [])]  # reprise (REPLAY/RERUN) nao e momento novo
    cs = [c for c in cs if c["url"] and c["views"] >= min_views and (c["duracao"] or 30) >= 8  # clipe de 5 s nao vira Short
          and not any(t in (c["titulo"] or "").lower() for t in ignorar)]
    return sorted(cs, key=lambda c: c["views"], reverse=True)[:maximo]


def ultimo_vod(login):
    """O VOD (transmissao arquivada) mais recente: {id, url, titulo} ou None."""
    if tem_api():
        uid = _id_usuario(login)
        vs = _get("/videos", user_id=uid, type="archive", first=1) if uid else []
        return {"id": vs[0]["id"], "url": vs[0]["url"], "titulo": vs[0].get("title", "")} if vs else None
    es = _ytdlp_lista(f"https://www.twitch.tv/{login}/videos?filter=archives&sort=time", 1)
    if not es:
        return None
    e = es[0]
    return {"id": e.get("id"), "url": e.get("url") or e.get("webpage_url"), "titulo": e.get("title", "")}


def descobrir(idioma="en", n=20):
    """Maiores lives AGORA no idioma (API oficial; precisa de TWITCH_CLIENT_ID/SECRET): ajuda a escolher canais grandes.
    Nao diz nada sobre a permissao de cortes de cada um: isso o Dono confere na regra do streamer antes de autorizar."""
    if not tem_api():
        raise RuntimeError("precisa das chaves da API da Twitch (TWITCH_CLIENT_ID e TWITCH_CLIENT_SECRET no braniac/.env)")
    vistos, out = set(), []
    for s in _get("/streams", language=idioma, first=100):
        if s["user_login"] not in vistos:
            vistos.add(s["user_login"])
            out.append({"login": s["user_login"], "nome": s.get("user_name", ""), "espectadores": s.get("viewer_count", 0),
                        "jogo": s.get("game_name", "")})
    return out[:n]
