# -*- coding: utf-8 -*-
"""Iniciar com o Windows (opcional, escolha da pessoa): o app abre ESCONDIDO na bandeja, para o assistente e o Telegram ja estarem de pe."""
import sys
from pathlib import Path

CHAVE = r"Software\Microsoft\Windows\CurrentVersion\Run"
NOME = "BRANIAC"


def exe_do_app():
    """braniac.exe fica ao lado do backend empacotado (braniac-core.exe). Fora do pacote (desenvolvimento) nao ha o que registrar."""
    if getattr(sys, "frozen", False):
        p = Path(sys.executable).parent / "braniac.exe"
        return p if p.exists() else None
    return None


def ativo():
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CHAVE) as k:
            winreg.QueryValueEx(k, NOME)
            return True
    except OSError:
        return False


def definir(ligado, exe=None):
    """Liga/desliga. Usa so a chave do USUARIO (HKCU): nao precisa de administrador."""
    if sys.platform != "win32":
        raise RuntimeError("só no Windows")
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CHAVE, 0, winreg.KEY_SET_VALUE) as k:
        if ligado:
            exe = exe or exe_do_app()
            if not exe:
                raise RuntimeError("o programa instalado não foi encontrado (isto só funciona no app instalado)")
            winreg.SetValueEx(k, NOME, 0, winreg.REG_SZ, f'"{exe}" --background')
        else:
            try:
                winreg.DeleteValue(k, NOME)
            except OSError:
                pass
