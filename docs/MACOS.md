# BRANIAC no macOS

Port do backend e da casca para macOS. O Windows continua sendo o alvo principal: nada do caminho do Windows foi removido.

## Rodar sem compilar
```
./scripts/dev-mac.sh [porta]     # só Python 3.9+; abre a tela no navegador
```
Dados em `~/Library/Application Support/BRANIAC-dados`; chaves de API no Keychain (item `BRANIAC/<provedor>`). `BRANIAC_HOME=/pasta` usa um perfil de teste.

## Gerar o app (.app e .dmg)
```
./scripts/build-mac.sh           # Python, Node 20+, Rust e Xcode Command Line Tools
```
**Não verificado:** o `main.rs` (cfg por plataforma, `RunEvent::Reopen`, encerramento com SIGTERM) e o `build-mac.sh` nunca foram compilados/rodados. Sem assinatura/notarização da Apple o Gatekeeper avisa na primeira abertura.

## O que mudou
- `plataforma.py`: diferenças Windows/macOS num lugar só (abrir arquivo/app, shell, lixeira, `SEM_JANELA`).
- `cofre.py`: Keychain via Security.framework (ctypes; a chave nunca vai em argumento de linha de comando).
- `autostart.py`: LaunchAgent do usuário. `hardware.py`: RAM por `sysctl`, GPU Apple Silicon (memória unificada).
- `guarda.py`: portas por `lsof` e firewall do macOS (sem antivírus/RDP/login). `pc_tools.py`: shell zsh, lixeira pelo Finder, filtro de comandos perigosos também para unix.
- Interface: textos dependem do sistema (Keychain, barra de menus). Testes: `tests/conftest.py` isola o cofre real.

## Navegador do assistente
- **Chromium (Chrome/Edge/Brave...)**: CDP, como no Windows (perfil separado, janela escondida).
- **Safari (`navegador_safari.py`, experimental)**: AppleScript `do JavaScript`. O assistente só mexe nas abas que ele criou. Exige em *Safari › Ajustes › Desenvolvedor* a opção "Permitir JavaScript de Eventos da Apple". Limites: abas de janelas **privadas** não são visíveis ao AppleScript (é preciso uma janela normal aberta); não há janela própria para esconder; cliques/digitação são eventos de JavaScript; envio de arquivo no WhatsApp limitado a 15 MB.
- **Verificado com o Safari real:** abrir/listar/fechar a aba do assistente. **Não verificado:** execução de JavaScript, ChatGPT/Gemini, WhatsApp e pesquisa no Safari.

## Não existe no macOS
Atualização automática (releases só trazem o instalador NSIS), ArtCraft (CLIs só para Windows), rede de Braniacs (Radmin VPN), e o ícone na barra de menus só existe no app Tauri compilado.
