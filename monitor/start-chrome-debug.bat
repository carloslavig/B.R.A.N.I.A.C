@echo off
rem ================================================================
rem  SO E NECESSARIO no DETECT_MODE=cdp.
rem
rem  Abre o Chrome com a porta de debug remoto (9222) usando um
rem  PERFIL DEDICADO em %USERPROFILE%\ChromeAgente.
rem
rem  Por que perfil dedicado: a partir do Chrome 136 a porta de debug
rem  e IGNORADA se voce usar o perfil padrao. Entao a automacao usa um
rem  perfil separado. Voce faz login no WhatsApp Web e no Airbnb UMA VEZ
rem  nesse perfil; depois fica salvo.
rem
rem  Este .bat NAO fecha o seu Chrome normal. Ele abre uma janela
rem  separada, so para a automacao. Deixe essa janela aberta.
rem ================================================================
setlocal
set "PROFILE=%USERPROFILE%\ChromeAgente"
rem caminho ABSOLUTO e limpo (sem "..\"): com "..\" o Chrome nao le o arquivo e o microfone virtual sai mudo
for %%I in ("%~dp0..\braniac\data\mic.wav") do set "MIC=%%~fI"
set "CHROME=C:\Program Files\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"

if not exist "%CHROME%" (
  echo Chrome nao encontrado. Ajuste o caminho neste .bat.
  goto :end
)

if not exist "%PROFILE%" mkdir "%PROFILE%"

echo Abrindo Chrome de automacao (porta 9222, perfil %PROFILE%)...
start "" "%CHROME%" ^
  --remote-debugging-port=9222 ^
  --user-data-dir="%PROFILE%" ^
  --no-first-run --no-default-browser-check ^
  --use-fake-device-for-media-stream --use-fake-ui-for-media-stream ^
  --use-file-for-fake-audio-capture="%MIC%%%noloop" --mute-audio ^
  --disable-features=CalculateNativeWinOcclusion --disable-backgrounding-occluded-windows --disable-renderer-backgrounding ^
  --new-window "https://web.whatsapp.com" "https://www.airbnb.com.br/hosting/messages"

echo.
echo Na PRIMEIRA vez: faca login no WhatsApp Web (QR code) e no Airbnb
echo nessa janela. Depois e so deixar aberta.
echo.
echo Para conferir a porta: abra http://127.0.0.1:9222/json/version

:end
echo.
pause
endlocal
