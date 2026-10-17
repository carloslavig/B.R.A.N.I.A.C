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

## Status — v0.6.0

Já funciona:

- **Instalação guiada:** chaves de IA (≥ 1 obrigatória, com passo a passo), permissões em cascata (inclui “nenhum acesso”), IA local (Ollama) por hardware, nome e voz do assistente, WhatsApp e Telegram opcionais.
- **Assistente (tela inicial):** conversa por texto ou microfone, voz natural pela chave Google da própria pessoa, ações no PC só dentro das permissões liberadas (ações perigosas pedem “Confirmar”), controle remoto pelo Telegram, bandeja do Windows e início com o Windows.
- **Novo na 0.4:** pesquisa na web e leitura de abas pelo navegador do assistente (só leitura, resultado só para a pessoa); envio de arquivos por WhatsApp (o assistente acha o contato, até fora das conversas recentes); resumo diário do e-mail de cada pessoa; guarda de segurança opcional (IP, firewall, antivírus, portas, tentativas de login: só avisa); a desinstalação pergunta se apaga TODOS os dados para reinstalar do zero; a tela final do instalador não prende mais ninguém.
- **Novo na 0.5:** memória do usuário (como quer ser chamado, preferências, “lembre que…”, “esqueça…”) no banco local e usada em toda conversa; criação e edição de imagens, vetores e PDFs pelo **ArtCraft** (VectorCraft, PhotoCraft e PdfCraft, Apache-2.0, embutidos no instalador): cartaz, converter/redimensionar/girar fotos, juntar/dividir/extrair PDFs. O resultado vai para `Documentos\BRANIAC-Criacoes` e o original nunca é alterado; permissões `criativo.*`.
- **Novo na 0.6:** a versão aparece no canto inferior direito; **atualização automática** pelas releases do GitHub (confere o SHA-256 publicado na release; desligue falando “desligue a atualização automática”); **rede de Braniacs** pela Radmin VPN: os assistentes de pessoas diferentes conversam entre si só se os dois donos permitirem (convite de uso único, mensagens assinadas, resposta sem dados pessoais e sem executar ordens). Permissão `rede.conversar`.
- **Modo jogo:** botão (ou falar “modo jogo”) suspende o assistente e o Telegram até dois cliques no orbe.

Ainda não existe: chamar só falando o nome, ícone flutuante, detectar jogo sozinho, atendimento automático do WhatsApp, e-mail.
Dados pessoais ficam só no PC da pessoa (`%LOCALAPPDATA%`/Credential Manager); o repositório só traz código e atualizações.
