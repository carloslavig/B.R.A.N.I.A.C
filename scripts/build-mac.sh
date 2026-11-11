#!/usr/bin/env bash
# Gera o app do BRANIAC para macOS (.app e .dmg): backend Python empacotado (PyInstaller) + casca Tauri.
# Requisitos (so de QUEM CONSTROI): Python 3.9+, Node 20+, Rust (stable) e as Xcode Command Line Tools (xcode-select --install).
#   ./scripts/build-mac.sh
# Saida: app/src-tauri/target/release/bundle/{macos,dmg}/
# Sem assinatura/notarizacao da Apple o Gatekeeper avisa na 1a abertura (botao direito > Abrir). Para distribuir, assine com Developer ID.
set -euo pipefail
raiz="$(cd "$(dirname "$0")/.." && pwd)"
triple="$(rustc -vV | sed -n 's/^host: //p')"
cd "$raiz/seed"
[ -d .venv-build ] || python3 -m venv .venv-build
.venv-build/bin/pip install --quiet --disable-pip-version-check pyinstaller websocket-client pillow
.venv-build/bin/python -m PyInstaller --onefile --name braniac-core \
  --add-data "braniac_seed/ui:braniac_seed/ui" --add-data "braniac_seed/habilidades:braniac_seed/habilidades" \
  --distpath "$raiz/app/src-tauri/binaries" --workpath "$raiz/build/pyi" --specpath "$raiz/build" core_main.py
cp "$raiz/app/src-tauri/binaries/braniac-core" "$raiz/app/src-tauri/binaries/braniac-core-${triple}"
# ArtCraft (vector/photo/pdf) ainda so existe para Windows: a pasta fica vazia no Mac e esses recursos avisam que nao estao instalados
mkdir -p "$raiz/app/src-tauri/artcraft"
cd "$raiz/app"
npm install
npx tauri build --bundles app,dmg
echo; echo "App: $raiz/app/src-tauri/target/release/bundle/"
