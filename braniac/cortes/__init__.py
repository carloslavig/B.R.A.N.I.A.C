# -*- coding: utf-8 -*-
"""Cortes automaticos de lives da Twitch -> YouTube Shorts / TikTok, 100% local (sem LLM paga).

Fluxo: vigia (live/VOD/clipes) -> deteccao (pico de audio + chat) -> legenda (Whisper local)
-> render 9:16 (ffmpeg/NVENC) -> fila (SQLite) -> aprovacao do Dono -> YouTube / pasta do TikTok.
Uso: python -m braniac.cortes --help
"""
