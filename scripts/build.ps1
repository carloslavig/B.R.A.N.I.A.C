# Gera o instalador do BRANIAC (Windows): backend Python empacotado + app Tauri + instalador NSIS.
# Requisitos (so para QUEM CONSTROI; quem instala nao precisa de nada): Python 3.12, Node 20+, Rust (stable, msvc) e VS Build Tools.
#   .\scripts\build.ps1
$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location "$raiz\seed"
python -m pip install --quiet pyinstaller websocket-client
$ui = (Resolve-Path "braniac_seed\ui").Path
python -m PyInstaller --onefile --noconsole --name braniac-core --add-data "$ui;braniac_seed/ui" `
    --distpath "$raiz\app\src-tauri\binaries" --workpath "$raiz\build\pyi" --specpath "$raiz\build" core_main.py
Copy-Item "$raiz\app\src-tauri\binaries\braniac-core.exe" "$raiz\app\src-tauri\binaries\braniac-core-x86_64-pc-windows-msvc.exe" -Force
Set-Location "$raiz\app"
npm install
npx tauri build
Write-Host "`nInstalador: $raiz\app\src-tauri\target\release\bundle\nsis\"
