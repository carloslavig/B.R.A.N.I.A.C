# -*- coding: utf-8 -*-
"""Atalho para o ChatGPT (ver ia_web.py)."""
from .ia_web import IAWebErro as GptWebErro  # noqa: F401
from . import ia_web


def perguntar(texto, timeout_s=120, nova_conversa=True):
    return ia_web.perguntar("chatgpt", texto, timeout_s, nova_conversa)
