@echo off
rem Desliga tudo: pausa IAs/monitor, descarrega o Ollama e encerra o servidor do Braniac.
cd /d "%~dp0\.."
python -c "from braniac import power; power.desligar('manual')"
for /f "tokens=5" %%p in ('netstat -ano ^| findstr "127.0.0.1:8765" ^| findstr LISTENING') do taskkill /PID %%p /F >nul 2>&1
echo Braniac desligado. Para religar, abra LIGAR-JARVIS.bat
timeout /t 3 >nul
