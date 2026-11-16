# -*- coding: utf-8 -*-
"""TikTok: SEM robo de navegador (contra os termos, risco de perder a conta).

Padrao: o corte aprovado vai para data/cortes/tiktok/ (video + legenda .txt pronta para colar) e o Dono posta pelo celular.
Opcional (cfg tiktok_rascunho_api=True + TIKTOK_ACCESS_TOKEN no .env, depois do app aprovado no TikTok for Developers com o
escopo video.upload): manda o video como RASCUNHO para a caixa de entrada do app; o Dono so revisa e publica."""
import shutil
import requests
from . import config

INIT = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"


def preparar(corte, perfil=""):
    pasta = config.sub("tiktok" + (f"/{perfil}" if perfil else ""))
    destino = pasta / f"corte_{corte['id']:04d}.mp4"
    shutil.copy2(corte["arquivo"], destino)
    legenda = f"{corte.get('titulo') or ''} {corte.get('hashtags') or ''}".strip()
    (pasta / f"corte_{corte['id']:04d}.txt").write_text(legenda.replace("#shorts", "#fyp"), encoding="utf-8")
    return destino


def enviar_rascunho(arquivo):
    """Content Posting API (upload para a caixa de entrada). Devolve o publish_id."""
    token = config.env("TIKTOK_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("sem TIKTOK_ACCESS_TOKEN no .env")
    dados = open(arquivo, "rb").read()
    if len(dados) > 64 * 1024 * 1024:
        raise RuntimeError("video acima de 64 MB: envio em pedaco unico nao suportado aqui")
    r = requests.post(INIT, timeout=30, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"},
                      json={"source_info": {"source": "FILE_UPLOAD", "video_size": len(dados), "chunk_size": len(dados), "total_chunk_count": 1}})
    d = r.json()
    if r.status_code != 200 or d.get("error", {}).get("code", "ok") != "ok":
        raise RuntimeError(f"TikTok recusou: {d.get('error')}")
    up = requests.put(d["data"]["upload_url"], data=dados, timeout=600, headers={
        "Content-Type": "video/mp4", "Content-Length": str(len(dados)), "Content-Range": f"bytes 0-{len(dados) - 1}/{len(dados)}"})
    if up.status_code not in (200, 201):
        raise RuntimeError(f"upload TikTok HTTP {up.status_code}")
    return d["data"]["publish_id"]
