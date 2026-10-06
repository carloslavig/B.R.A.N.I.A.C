# -*- coding: utf-8 -*-
"""Onde ficam os dados de cada pessoa. TUDO roda e fica no PC dela (nada sobe para este repositorio nem para servidor nenhum):
perfil, banco, permissoes, extensoes baixadas. Pode ser trocado com a variavel BRANIAC_HOME (testes)."""
import os
from pathlib import Path

APP = "BRANIAC-dados"   # pasta DIFERENTE da do programa (%LOCALAPPDATA%\BRANIAC): desinstalar o app nunca apaga os dados da pessoa


def dados_dir():
    base = os.environ.get("BRANIAC_HOME")
    if base:
        p = Path(base)
    else:
        p = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")) / APP
    p.mkdir(parents=True, exist_ok=True)
    return p


def arquivo(nome):
    return dados_dir() / nome
