# -*- coding: utf-8 -*-
"""Faxina de abas (11/11/2026): o Chrome do Braniac acumulava abas paradas (Gemini, Grok, Instagram, TikTok...) e era ele,
nao o Python, que pesava no PC (~2,5 GB). A cada tick fecha a aba que NAO e essencial e esta ha mais de PARADA_S na mesma
URL. O login nao se perde (fica no perfil); quem precisar abre a aba de novo sob demanda.
Desligar: BRANIAC_FAXINA_ABAS=0 no .env."""
import os, time

MANTER = ("web.whatsapp.com", "airbnb.com", "web.telegram.org", "infinitepay.io", "127.0.0.1", "localhost", "chrome://", "devtools://")
PARADA_S = 3600
_vistas = {}   # id da aba -> (url, desde quando esta nessa url)


def escolher(abas, vistas, agora, parada_s=PARADA_S):
    """Pura: recebe [{id, url}], atualiza `vistas` e devolve os ids a fechar (nao essenciais, parados ha parada_s)."""
    fechar = []
    for a in abas:
        url = a.get("url", "")
        ant = vistas.get(a["id"])
        if not ant or ant[0] != url:
            vistas[a["id"]] = (url, agora)      # aba nova ou navegou: zera o relogio
        elif agora - ant[1] >= parada_s and not any(m in url for m in MANTER):
            fechar.append(a["id"])
    vivos = {a["id"] for a in abas}
    for i in [i for i in vistas if i not in vivos or i in fechar]:
        del vistas[i]
    return fechar


def tick(agora=None):
    """Devolve quantas abas fechou. Nunca mexe no Chrome enquanto um audio esta sendo gravado (sairia cortado)."""
    if os.environ.get("BRANIAC_FAXINA_ABAS", "1") == "0":
        return 0
    from . import pesquisa, wpp_voz
    if wpp_voz._LOCK.locked():
        return 0
    fechar = escolher(pesquisa._abas(), _vistas, agora or time.time())
    for i in fechar:
        pesquisa._fechar_aba(i)
    return len(fechar)
