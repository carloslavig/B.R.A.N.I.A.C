#!/usr/bin/env bash
# Roda o BRANIAC no macOS SEM compilar nada (so Python 3.9+): sobe o backend e abre a tela no navegador.
#   ./scripts/dev-mac.sh [porta]        (padrao 8765)
# Dados da pessoa ficam em ~/Library/Application Support/BRANIAC-dados (chaves no Keychain). Use BRANIAC_HOME=/pasta para um perfil de teste.
set -euo pipefail
raiz="$(cd "$(dirname "$0")/.." && pwd)"
porta="${1:-8765}"
cd "$raiz/seed"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install --quiet --disable-pip-version-check websocket-client pillow
fi
echo "BRANIAC em http://127.0.0.1:${porta}  (Ctrl+C para parar)"
( sleep 2 && open "http://127.0.0.1:${porta}/" ) &
exec .venv/bin/python -c "
import sys, time
from braniac_seed import auto_update, rede_local, email_diario, guarda, remoto, servidor
srv, p = servidor.servir(int(sys.argv[1]), bloquear=False)
guarda.iniciar(); email_diario.iniciar(); auto_update.iniciar(); rede_local.iniciar(); remoto.iniciar()
while True: time.sleep(3600)
" "$porta"
