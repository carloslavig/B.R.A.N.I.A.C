# B.R.A.N.I.A.C

Assistente de IA pessoal para Windows: voz, memória local e acesso ao PC **só com a sua permissão**.
Tudo roda no seu computador — nada seu é enviado para este repositório.

- Arquitetura e decisões: [docs/ARQUITETURA.md](docs/ARQUITETURA.md)
- Backend da instalação (permissões, cofre de chaves, hardware, nome/voz, reunião das IAs, atualizador): [`seed/`](seed/)
- App desktop (Tauri, uma janela só): [`app/`](app/)

## Gerar o instalador

Requisitos de quem constrói: Python 3.12, Node 20+, Rust (stable, msvc) e Visual Studio Build Tools.

```
.\scripts\build.ps1
```

Saída: `app\src-tauri\target\release\bundle\nsis\BRANIAC_<versão>_x64-setup.exe` (instala por usuário, sem administrador).

## Testes

```
cd seed
python -m pytest tests -q
```

## Status — v0.3.0

Já funciona:

- **Instalação guiada:** chaves de IA (≥ 1 obrigatória, com passo a passo), permissões em cascata (inclui “nenhum acesso”), IA local (Ollama) por hardware, nome e voz do assistente, WhatsApp e Telegram opcionais.
- **Assistente (tela inicial):** conversa por texto ou microfone, voz natural pela chave Google da própria pessoa, ações no PC só dentro das permissões liberadas (ações perigosas pedem “Confirmar”), controle remoto pelo Telegram, bandeja do Windows e início com o Windows.
- **Modo jogo:** botão (ou falar “modo jogo”) suspende o assistente e o Telegram até dois cliques no orbe.

Ainda não existe: chamar só falando o nome, ícone flutuante, detectar jogo sozinho, atendimento automático do WhatsApp, e-mail.
Dados pessoais ficam só no PC da pessoa (`%LOCALAPPDATA%`/Credential Manager); o repositório só traz código e atualizações.
