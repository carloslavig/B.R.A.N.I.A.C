# -*- coding: utf-8 -*-
"""fcc: ponte local Anthropic Messages -> provedores gratis do Braniac (codigo Rust em fcc-rs/).
Abre as chaves do .env (DPAPI) so na memoria do processo e as entrega ao fcc.exe por variavel de ambiente.
Claude Code usando os provedores gratis:  set ANTHROPIC_BASE_URL=http://127.0.0.1:8791  e  ANTHROPIC_AUTH_TOKEN=local
Compilar: cd fcc-rs && cargo build --release.   Subir: python -m braniac.fcc"""
import os
import socket
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
EXE = RAIZ / "fcc-rs" / "target" / "release" / "fcc.exe"
PORTA = 8791


def no_ar(porta=PORTA):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", porta)) == 0


def subir(porta=PORTA):
    """Sobe a ponte sem janela se ainda nao estiver no ar. Devolve True se esta respondendo."""
    if no_ar(porta):
        return True
    if not EXE.exists():
        return False
    from . import segredos
    env = {**os.environ, **segredos.ler_env(RAIZ / ".env")}
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen([str(EXE), str(RAIZ), str(porta)], env=env, creationflags=flags,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True


def variaveis(porta=PORTA):
    """Variaveis para rodar o Claude Code pela ponte."""
    return {"ANTHROPIC_BASE_URL": f"http://127.0.0.1:{porta}", "ANTHROPIC_AUTH_TOKEN": "local"}


if __name__ == "__main__":
    print("fcc no ar" if subir() else "fcc.exe nao compilado (cd fcc-rs && cargo build --release)")
    sys.exit(0)
