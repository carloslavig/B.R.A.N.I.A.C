@echo off
rem Liga o navegador do Braniac (WhatsApp, ChatGPT, Gemini, Grok), o servidor do Jarvis e abre a interface.
cd /d "%~dp0\.."
title Ligando o Braniac...
python -m braniac.ligar_tudo
