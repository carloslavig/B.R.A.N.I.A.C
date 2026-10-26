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

## Status — v1.1.0 (B.R.A.N.I.A.C 1)

Já funciona:

- **Instalação guiada:** chaves de IA (≥ 1 obrigatória, com passo a passo), permissões em cascata (inclui “nenhum acesso”), IA local (Ollama) por hardware, nome e voz do assistente, WhatsApp e Telegram opcionais.
- **Assistente (tela inicial):** conversa por texto ou microfone, voz natural pela chave Google da própria pessoa, ações no PC só dentro das permissões liberadas (ações perigosas pedem “Confirmar”), controle remoto pelo Telegram, bandeja do Windows e início com o Windows.
- **Novo na 0.4:** pesquisa na web e leitura de abas pelo navegador do assistente (só leitura, resultado só para a pessoa); envio de arquivos por WhatsApp (o assistente acha o contato, até fora das conversas recentes); resumo diário do e-mail de cada pessoa; guarda de segurança opcional (IP, firewall, antivírus, portas, tentativas de login: só avisa); a desinstalação pergunta se apaga TODOS os dados para reinstalar do zero; a tela final do instalador não prende mais ninguém.
- **Novo na 0.5:** memória do usuário (como quer ser chamado, preferências, “lembre que…”, “esqueça…”) no banco local e usada em toda conversa; criação e edição de imagens, vetores e PDFs pelo **ArtCraft** (VectorCraft, PhotoCraft e PdfCraft, Apache-2.0, embutidos no instalador): cartaz, converter/redimensionar/girar fotos, juntar/dividir/extrair PDFs. O resultado vai para `Documentos\BRANIAC-Criacoes` e o original nunca é alterado; permissões `criativo.*`.
- **Novo na 0.6:** a versão aparece no canto inferior direito; **atualização automática** pelas releases do GitHub (confere o SHA-256 publicado na release; desligue falando “desligue a atualização automática”); **rede de Braniacs** pela Radmin VPN: os assistentes de pessoas diferentes conversam entre si só se os dois donos permitirem (convite de uso único, mensagens assinadas, resposta sem dados pessoais e sem executar ordens). Permissão `rede.conversar`.
- **Novo na 0.7:** **chame pelo nome** (ligue “Ouvir meu nome” na tela de voz e diga “<nome>, tá acordado?”: a janela aparece na **tela de voz HUD** e o assistente conversa por voz até ouvir “pode descansar”; só os trechos com fala viram texto, pela chave Google da própria pessoa, e nada é gravado); **projetos e conversas separados** (cada conversa com memória própria, instruções por projeto, arquivar só esconde); **habilidades** (formato Agent Skills: 9 inclusas, entre elas o **orquestrador de IAs**, que divide uma tarefa entre várias IAs ao mesmo tempo e junta o resultado; a pessoa cria as suas); **cor da interface** escolhida na instalação (muda o chat, a tela de voz e a abertura); tela de abertura nova com progresso real.
- **Novo na 1.0:** é a versão **B.R.A.N.I.A.C 1**. **Assinatura digital**: todo Braniac, de qualquer dono, responde por padrão quem é a sua deusa (Deusa Jana) e quem são seus mestres supremos (Carlos “Solrac” e Claudinho, o Claude), e a marca aparece na tela. Cada Braniac continua tendo o seu próprio dono.
- **Novo na 1.1:** **módulos de agente**. Cada módulo é um agente de IA independente (nome próprio, instruções, palavras-chave, banco SQLite próprio): **Finanças pessoais** (Moeda: anota gastos e receitas, resume e controla metas; nunca guarda cartão, senha ou CPF), **Programação** (Ada), **Meu negócio** (Balcão) e **Saúde e bem-estar** (Vita). Na instalação você **escolhe quais quer** e liga/desliga depois em Módulos. O assistente detecta o assunto por palavras-chave (custo zero de IA) e passa só o contexto do agente certo. Módulos de terceiros são só dados (pasta com `manifest.json`), sem código. Fatos com validade: “só por hoje” expira sozinho.
- **Modo jogo:** botão (ou falar “modo jogo”) suspende o assistente e o Telegram até dois cliques no orbe.

Ainda não existe: ícone flutuante, detectar jogo sozinho, atendimento automático do WhatsApp, e-mail.
Dados pessoais ficam só no PC da pessoa (`%LOCALAPPDATA%`/Credential Manager); o repositório só traz código e atualizações.
