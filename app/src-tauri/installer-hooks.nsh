; Ganchos do instalador NSIS do BRANIAC.
; Os dados da pessoa ficam FORA da pasta do programa (%LOCALAPPDATA%\BRANIAC-dados) para uma ATUALIZACAO nunca apagar nada.
; Ao DESINSTALAR de verdade (nao em atualizacao) perguntamos se apaga tambem os dados: "Sim" deixa o PC totalmente limpo
; (a proxima instalacao comeca do zero: sem perfil, sem permissoes, sem chaves, sem login do navegador do assistente).

!macro NSIS_HOOK_PREUNINSTALL
  nsExec::Exec 'taskkill /F /IM braniac.exe /T'
  nsExec::Exec 'taskkill /F /IM braniac-core.exe /T'
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  ${If} $UpdateMode <> 1
    MessageBox MB_YESNO|MB_ICONQUESTION "Apagar TAMBÉM os seus dados do BRANIAC?$\n$\n(perfil, permissões, chaves de IA, histórico, login do navegador do assistente e Telegram)$\n$\nEscolha SIM para deixar o computador totalmente limpo: uma nova instalação começa do zero.$\nEscolha NÃO para guardar seus dados para uma reinstalação." /SD IDYES IDNO braniac_manter_dados
      RMDir /r "$LOCALAPPDATA\BRANIAC-dados"
      RMDir /r "$LOCALAPPDATA\com.carloslavig.braniac"
      RMDir /r "$APPDATA\com.carloslavig.braniac"
      DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "BRANIAC"
      ; chaves guardadas no Cofre de Credenciais do Windows (alvos 'BRANIAC/...')
      FileOpen $0 "$TEMP\braniac_limpa_cofre.ps1" w
      FileWrite $0 "cmdkey /list | Select-String 'BRANIAC/' | ForEach-Object { $$t = ($$_.Line -replace '.*target=','').Trim(); cmdkey /delete:$$t | Out-Null }$\r$\n"
      FileClose $0
      nsExec::Exec 'powershell -NoProfile -ExecutionPolicy Bypass -File "$TEMP\braniac_limpa_cofre.ps1"'
      Delete "$TEMP\braniac_limpa_cofre.ps1"
    braniac_manter_dados:
  ${EndIf}
!macroend
