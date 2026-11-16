@echo off
cd /d "%~dp0\.."
python -m braniac.cortes desligar
timeout /t 5 >nul
