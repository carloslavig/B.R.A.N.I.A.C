# -*- coding: utf-8 -*-
"""Ponto de entrada do backend empacotado (sidecar do app Tauri): `braniac-core.exe <porta>`."""
import sys, time
from braniac_seed import email_diario, remoto, servidor

if __name__ == "__main__":
    porta = int(sys.argv[1]) if len(sys.argv) > 1 else None
    srv, porta = servidor.servir(porta, bloquear=False)
    email_diario.iniciar()     # resumo diario do e-mail (so se a pessoa conectou o proprio Gmail)
    remoto.iniciar()           # se ja houver bot pareado, volta a atender o Telegram assim que o app abre
    try:
        print(f"BRANIAC em http://127.0.0.1:{porta}", flush=True)
    except Exception:
        pass            # sem console (empacotado): nada a imprimir
    while True:
        time.sleep(3600)
