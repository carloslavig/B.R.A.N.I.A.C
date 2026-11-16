@echo off
rem Sobe o servidor do Braniac (se ainda nao estiver de pe) e abre a interface do Jarvis.
cd /d "%~dp0\.."
powershell -NoProfile -Command "try{(Invoke-WebRequest http://127.0.0.1:8765/api/status -UseBasicParsing -TimeoutSec 2)|Out-Null;exit 0}catch{exit 1}"
if errorlevel 1 (
  start "Braniac" /min python -m braniac.server
  timeout /t 3 /nobreak >nul
)
python -c "from braniac import power; power.ligar()"
start "" http://127.0.0.1:8765
