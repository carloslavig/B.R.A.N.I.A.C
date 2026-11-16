@echo off
rem Liga o vigia dos cortes de live da Twitch (roda sozinho, sem janela). Log: braniac\data\cortes\cortes.log
cd /d "%~dp0\.."
python -m braniac.cortes ligar
python -m braniac.cortes status
timeout /t 8 >nul
