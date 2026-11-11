# -*- coding: utf-8 -*-
"""Iniciar com o Windows (opcional, escolha da pessoa): o app abre ESCONDIDO na bandeja, para o assistente e o Telegram ja estarem de pe."""
import sys
from pathlib import Path

CHAVE = r"Software\Microsoft\Windows\CurrentVersion\Run"
NOME = "BRANIAC"


PLIST_MAC = Path.home() / "Library" / "LaunchAgents" / "com.carloslavig.braniac.plist"


def exe_do_app():
    """braniac(.exe) fica ao lado do backend empacotado (braniac-core). Fora do pacote (desenvolvimento) nao ha o que registrar."""
    if getattr(sys, "frozen", False):
        p = Path(sys.executable).parent / ("braniac.exe" if sys.platform == "win32" else "braniac")
        return p if p.exists() else None
    return None


def _definir_mac(ligado, exe):
    """macOS: LaunchAgent do usuario (~/Library/LaunchAgents), sem administrador. RunAtLoad abre o app escondido no login."""
    import plistlib, subprocess
    dominio = f"gui/{__import__('os').getuid()}"
    if ligado:
        exe = exe or exe_do_app()
        if not exe:
            raise RuntimeError("o programa instalado não foi encontrado (isto só funciona no app instalado)")
        PLIST_MAC.parent.mkdir(parents=True, exist_ok=True)
        PLIST_MAC.write_bytes(plistlib.dumps({"Label": "com.carloslavig.braniac", "ProgramArguments": [str(exe), "--background"], "RunAtLoad": True}))
        subprocess.run(["launchctl", "bootout", dominio, str(PLIST_MAC)], capture_output=True)      # recarrega se ja existia
        subprocess.run(["launchctl", "bootstrap", dominio, str(PLIST_MAC)], capture_output=True)
    elif PLIST_MAC.exists():
        subprocess.run(["launchctl", "bootout", dominio, str(PLIST_MAC)], capture_output=True)
        PLIST_MAC.unlink()


def ativo():
    if sys.platform == "darwin":
        return PLIST_MAC.exists()
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
    """Liga/desliga. Windows: so a chave do USUARIO (HKCU); macOS: LaunchAgent do usuario. Nenhum precisa de administrador."""
    if sys.platform == "darwin":
        return _definir_mac(ligado, exe)
    if sys.platform != "win32":
        raise RuntimeError("só no Windows e no macOS")
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
