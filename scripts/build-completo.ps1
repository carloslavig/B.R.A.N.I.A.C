# Gera o instalador do BRANIAC COMPLETO (Windows): a mesma janela do Braniac original + o Braniac inteiro + Python embutido.
# Quem instala nao precisa de nada (nem Python). Quem constroi: Python 3.12, Node 20+, Rust (stable, msvc) e VS Build Tools.
#   .\scripts\build-completo.ps1
$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
$pac = "$raiz\app-completo\pacote"

# 1) trava: nada pessoal entra no instalador
python "$raiz\scripts\varrer_pessoal.py" "$raiz\braniac" "$raiz\local-ia" "$raiz\monitor"
if ($LASTEXITCODE) { throw "Dado pessoal encontrado: corrija antes de gerar o instalador" }

# 2) Python embutido oficial (python.org), da mesma versao do Python de quem constroi (as bibliotecas precisam bater)
$ver = (python -c "import platform;print(platform.python_version())").Trim()
$mm = ($ver.Split(".")[0..1]) -join ""
if (Test-Path $pac) { Remove-Item -Recurse -Force $pac }
New-Item -ItemType Directory -Force "$pac\python" | Out-Null
$zip = "$env:TEMP\python-$ver-embed-amd64.zip"
if (-not (Test-Path $zip)) { Invoke-WebRequest "https://www.python.org/ftp/python/$ver/python-$ver-embed-amd64.zip" -OutFile $zip }
Expand-Archive $zip -DestinationPath "$pac\python" -Force
# caminhos do Python embutido: a pasta do pacote (..) para achar o braniac e site-packages para as bibliotecas
Set-Content -Encoding ascii "$pac\python\python$mm._pth" "python$mm.zip`r`n.`r`nLib\site-packages`r`n..`r`nimport site"
python -m pip install --disable-pip-version-check --quiet --target "$pac\python\Lib\site-packages" -r "$raiz\braniac\requirements.txt"
if ($LASTEXITCODE) { throw "pip falhou" }

# 3) o Braniac (sem data/, caches e testes) e as pecas de fora da pasta dele
robocopy "$raiz\braniac" "$pac\braniac" /E /XD data __pycache__ tests .pytest_cache graphify-out /XF *.pyc .env /NFL /NDL /NJH /NJS | Out-Null
robocopy "$raiz\local-ia" "$pac\local-ia" /E /XD __pycache__ /NFL /NDL /NJH /NJS | Out-Null
robocopy "$raiz\monitor" "$pac\monitor" /E /NFL /NDL /NJH /NJS | Out-Null
& "$pac\python\python.exe" -c "import braniac.server, braniac.jarvis, braniac.ligar_tudo; print('Braniac importa no Python embutido')"
if ($LASTEXITCODE) { throw "o Braniac nao importou no Python embutido" }
Remove-Item -Recurse -Force "$pac\braniac\data" -ErrorAction SilentlyContinue   # o teste acima cria data/ a partir de padrao/

# 4) janela + instalador NSIS (PowerShell 5.1 trata aviso no stderr do npm/tauri como erro: daqui em diante so o codigo de saida conta)
$ErrorActionPreference = "Continue"
Set-Location "$raiz\app-completo"
npm install
npx tauri build
if ($LASTEXITCODE) { throw "tauri build falhou" }
Write-Host "`nInstalador: $raiz\app-completo\target\release\bundle\nsis\"
