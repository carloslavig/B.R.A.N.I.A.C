# -*- coding: utf-8 -*-
"""Diferencas entre Windows e macOS num lugar so (v1.2): o resto do codigo pergunta aqui em vez de espalhar `sys.platform`.
Linux nao e alvo oficial, mas cai nos mesmos caminhos do macOS onde da (xdg-open, /bin/sh)."""
import subprocess, sys

WIN = sys.platform == "win32"
MAC = sys.platform == "darwin"
SO = "Windows" if WIN else ("macOS" if MAC else "Linux")

# creationflags so existe no Windows (no macOS qualquer valor diferente de 0 levanta ValueError): 0x08000000 = CREATE_NO_WINDOW
SEM_JANELA = 0x08000000 if WIN else 0

# nome falado pela pessoa -> nome do aplicativo no macOS (`open -a`)
APPS_MAC = {"calculadora": "Calculator", "bloco de notas": "TextEdit", "explorador": "Finder", "paint": "Preview", "configuracoes": "System Settings",
            "navegador": "Google Chrome", "edge": "Microsoft Edge", "chrome": "Google Chrome", "spotify": "Spotify", "word": "Microsoft Word",
            "excel": "Microsoft Excel"}


def _lancar(args):
    subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def abrir_arquivo(alvo):
    """Abre arquivo, pasta ou URL com o programa padrao do sistema."""
    if WIN:
        import os
        os.startfile(str(alvo))  # noqa: S606 (alvo ja validado por quem chama)
    elif MAC:
        _lancar(["open", str(alvo)])
    else:
        _lancar(["xdg-open", str(alvo)])


def abrir_app(nome):
    """Abre um aplicativo conhecido pelo nome falado (ver pc_tools.APPS). Devolve False se esse sistema nao conhece o nome."""
    chave = nome.strip().lower()
    if WIN:
        from .pc_tools import APPS
        app = APPS.get(chave)
        if not app:
            return False
        import os
        os.startfile(app)  # noqa: S606 (so apps conhecidos)
        return True
    if MAC and chave in APPS_MAC:
        _lancar(["open", "-a", APPS_MAC[chave]])
        return True
    return False


def comando_shell(comando):
    """Lista de argumentos para rodar um comando de texto no terminal do sistema."""
    if WIN:
        return ["powershell", "-NoProfile", "-Command", comando]
    return ["/bin/zsh" if MAC else "/bin/sh", "-c", comando]


def nome_shell():
    return "PowerShell" if WIN else ("terminal (zsh)" if MAC else "terminal (sh)")


def mover_para_lixeira(cam):
    """Manda o arquivo/pasta para a lixeira do sistema (da para restaurar). Levanta RuntimeError se falhar."""
    cam = str(cam)
    if WIN:
        metodo = "DeleteDirectory" if __import__("os").path.isdir(cam) else "DeleteFile"
        cmd = (f"Add-Type -AssemblyName Microsoft.VisualBasic; [Microsoft.VisualBasic.FileIO.FileSystem]::{metodo}"
               f"('{cam.replace(chr(39), chr(39) * 2)}','OnlyErrorDialogs','SendToRecycleBin')")
        r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=30, creationflags=SEM_JANELA)
    elif MAC:
        # o caminho vai como ARGUMENTO (nunca dentro do script): nome de arquivo nao consegue injetar AppleScript
        r = subprocess.run(["osascript", "-e", "on run argv", "-e", 'tell application "Finder" to delete (POSIX file (item 1 of argv))', "-e", "end run", cam],
                           capture_output=True, text=True, timeout=30)
    else:
        r = subprocess.run(["gio", "trash", cam], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:150] or "falhou")
