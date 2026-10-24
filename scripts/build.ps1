# Gera o instalador do BRANIAC (Windows): backend Python empacotado + app Tauri + instalador NSIS.
# Requisitos (so para QUEM CONSTROI; quem instala nao precisa de nada): Python 3.12, Node 20+, Rust (stable, msvc) e VS Build Tools.
#   .\scripts\build.ps1
$ErrorActionPreference = "Continue"   # PowerShell 5.1 trata aviso no stderr de programa externo como erro; checamos o codigo de saida
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location "$raiz\seed"
python -m pip install --quiet --disable-pip-version-check pyinstaller websocket-client
$ui = (Resolve-Path "braniac_seed\ui").Path
$hab = (Resolve-Path "braniac_seed\habilidades").Path   # v0.7: habilidades que vem junto
python -m PyInstaller --onefile --noconsole --name braniac-core --add-data "$ui;braniac_seed/ui" --add-data "$hab;braniac_seed/habilidades" `
    --distpath "$raiz\app\src-tauri\binaries" --workpath "$raiz\build\pyi" --specpath "$raiz\build" core_main.py
if ($LASTEXITCODE) { throw "PyInstaller falhou" }
Copy-Item "$raiz\app\src-tauri\binaries\braniac-core.exe" "$raiz\app\src-tauri\binaries\braniac-core-x86_64-pc-windows-msvc.exe" -Force
# ArtCraft (Apache-2.0): so os CLIs sem janela + licencas, de ~\Apps\ArtCraft (instalacao portatil de quem constroi)
foreach ($app in "vectorcraft","photocraft","pdfcraft") {
    $orig = Get-ChildItem "$env:USERPROFILE\Apps\ArtCraft\$app" -Directory | Select-Object -First 1
    $dest = "$raiz\app\src-tauri\artcraft\$app"
    New-Item -ItemType Directory -Force $dest | Out-Null
    Copy-Item "$($orig.FullName)\$app-cli.exe" $dest -Force
    Copy-Item "$($orig.FullName)\LICENSE-APACHE", "$($orig.FullName)\NOTICE" $dest -Force -ErrorAction SilentlyContinue
}
Set-Location "$raiz\app"
npm install
npx tauri build
if ($LASTEXITCODE) { throw "tauri build falhou" }
Write-Host "`nInstalador: $raiz\app\src-tauri\target\release\bundle\nsis\"
