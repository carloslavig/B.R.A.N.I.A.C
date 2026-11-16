@echo off
rem Liga o atendimento automatico do WhatsApp (sem precisar do navegador).
powershell -NoProfile -Command "try { $r = Invoke-RestMethod -Uri http://127.0.0.1:8765/api/atendimento-auto -Method Post -ContentType 'application/json' -Body '{\"ligado\":true}'; 'Atendimento automatico LIGADO (ligado=' + $r.atendimento_auto.ligado + ')' } catch { 'Falhou: o Jarvis esta aberto? ' + $_.Exception.Message }"
timeout /t 4 >nul
