# B.R.A.N.I.A.C

Assistente de IA pessoal para Windows: voz, memória local e acesso ao PC **só com a sua permissão**.
Tudo roda no seu computador — nada seu é enviado para este repositório.

- Arquitetura e decisões: [docs/ARQUITETURA.md](docs/ARQUITETURA.md)
- Backend da instalação (permissões, cofre de chaves, hardware, nome/voz, reunião das IAs, atualizador): [`seed/`](seed/)
- App desktop (Tauri, uma janela só): [`app/`](app/)
- **Braniac completo** (o mesmo núcleo do Braniac original: Jarvis, prédio/escritório 3D, B2, aba Vozes, agentes, NexoDev, Fornalha...): [`braniac/`](braniac/).
  Essa cópia não tem nenhum dado pessoal. Ela é gerada por `scripts/exportar.py` e conferida por `scripts/varrer_pessoal.py`.
  "Dono", "Parceira", "Mãe" e "Pai" são papéis: troque pelos nomes da sua casa. Por enquanto o instalador ainda usa o `seed/`, e a troca está no plano [docs/SEED-REAL.md](docs/SEED-REAL.md).

### Rodar o Braniac completo (avançado)

```
pip install requests websocket-client numpy cryptography pillow psutil
python -m braniac.ligar_tudo --sem-interface
```

Rode na pasta deste repositório e depois abra http://127.0.0.1:8765/b2. As chaves de IA vão em variáveis de ambiente ou em `braniac/.env`, que nunca vai para o git.
Os recursos opcionais só pedem as bibliotecas deles quando são usados: transcrição (`faster-whisper`), vozes locais (`kokoro-onnx`, `piper`, `sherpa-onnx`), Gmail (`google-api-python-client`) e conexão direta (`aiortc`).
A leitura do WhatsApp pelo navegador ainda não está aqui.

### Habilidades de terceiros

As habilidades feitas por outros autores (Instagram, day trade, investimentos, Blender) **não vêm neste repositório**.
Na primeira vez que o painel abre, ele pergunta se você quer instalar e mostra a lista para marcar e desmarcar. Só as marcadas são baixadas, direto do GitHub de cada autor
(lista em [`braniac/habilidades_terceiros.json`](braniac/habilidades_terceiros.json)). Depois, para instalar mais, use **Habilidades → Habilidades de terceiros**.
Cada uma segue a licença do próprio autor.

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
