# BRANIAC — arquitetura e decisões

Assistente de IA pessoal para Windows. Primeiro para amigos do Carlos, depois para venda. **Tudo roda no PC da pessoa.**

## Princípios (decisões do Carlos, 06/10/2026)

1. **Dados da pessoa nunca sobem.** Perfil, banco, conversas, chaves e permissões ficam em `%LOCALAPPDATA%\BRANIAC`. Este repositório só recebe **novas funções e parâmetros**, e a atualização é de mão única (o PC só baixa).
2. **Parecer um programa único**, feito pelo Carlos: um instalador, um ícone, uma janela. Nada de janelas e programas soltos.
3. **Consentimento claro e em cascata.** O acesso ao PC é explicado na instalação e pode ser *total*, *granular* ou *nenhum*. Recusar é válido: o assistente só conversa. Cada permissão é revogável (pai revoga filhos) e há botão de emergência (`revogar_tudo`).
4. **Nome obrigatório.** A pessoa escolhe nome e voz (feminina/masculina). Quem não souber recebe perguntas sobre seus gostos e sugestões.
5. **Pelo menos uma chave de API** (Google primeiro, depois OpenRouter, Groq, Cerebras, Mistral). As outras são opcionais e a tela diz o que cada uma melhora. A chave é testada na hora e guardada no **Gerenciador de Credenciais do Windows** — nunca em texto puro.
6. **Começa 100% local** (Ollama + Whisper). O perfil de IA local (Leve / Equilibrado / Potente) é escolhido pelo hardware; os modelos baixam sob demanda, não vêm no instalador.

## Arquitetura (decidida com o conselho de IAs do Braniac)

```
┌────────────────────────── 1 instalador · 1 ícone · 1 janela ──────────────────────────┐
│  Tauri (única janela visível: orbe, microfone, conversa, ícone de bandeja/flutuante)  │
│        │ API local (127.0.0.1)                                                        │
│  Sidecar Python: Braniac core (roteador de IAs, banco unificado, voz, permissões)     │
│        │ CDP                                                                          │
│  Navegador do assistente (Edge/Chrome do PC, perfil próprio, escondido):              │
│  contas ChatGPT/Gemini — só aparece no login, depois some. Um adapter por IA.         │
└───────────────────────────────────────────────────────────────────────────────────────┘
```

- **Por que não logar dentro do WebView2:** o Google costuma bloquear login em navegador embutido (`disallowed_useragent`) e o ChatGPT usa desafios que falham em webview. Navegador de verdade com perfil próprio é o que funciona; o Tauri esconde isso para a pessoa ver um programa só.
- **Adapters isolados** (ChatGPT, Gemini…): a interface dessas páginas muda e quebra a automação; cada IA fica numa camada trocável.
- **Código pesado separado de prompts/regras/parâmetros:** só estes se atualizam (por pacote assinado/com hash), sem reinstalar o pacote grande.
- **Reuniões das IAs (conselho)** ficam no projeto "Reuniões das IAs" do ChatGPT.

## Riscos conhecidos
- Pacote final grande (Python + Whisper). Modelos baixam depois.
- Sem certificado de assinatura de código, o antivírus pode acusar falso positivo → prever certificado antes de vender.
- Automação de ChatGPT/Gemini pelo navegador pode ferir os termos de uso e quebrar com mudanças de layout → tratada como camada opcional/substituível. Gemini também funciona por chave de API, sem aba.
- LGPD ao vender: consentimento, ver/exportar/apagar memória, telemetria só se a pessoa aceitar.

## Estado atual (v0.1)
Pronto e testado:
- `seed/braniac_seed`: permissões, cofre de chaves (+ validação), hardware/perfis, dependências da IA local (Ollama), nome e voz com sugestões, roteiro da instalação, **tela da instalação** (voz, orbe, microfone), navegador do assistente (Edge/Chrome, perfil próprio), adapters ChatGPT/Gemini, **primeira reunião das IAs** (grava a ficha no banco local), banco local em duas camadas, atualizador com hash + rollback, servidor local com proteção Host/Origin.
- `app/`: casca **Tauri** (uma janela) que sobe o backend empacotado (`braniac-core.exe`, PyInstaller) escondido, espera ele responder e mostra a tela; ao fechar encerra o backend.
- `scripts/build.ps1` gera `BRANIAC_x.y.z_x64-setup.exe` (NSIS, instalação por usuário, sem pedir administrador).

Os dados da pessoa ficam em `%LOCALAPPDATA%\BRANIAC-dados` (pasta diferente da do programa: desinstalar não apaga nada dela).

Falta: núcleo do Braniac (extração do código atual sem dados pessoais) ligado ao final da instalação, modo jogo/edição, ícone de bandeja/flutuante, assinatura do manifesto de atualização, certificado de assinatura de código, instalador do Ollama embutido no fluxo.

## WhatsApp e controle remoto pelo Telegram (v0.1+)

- **WhatsApp** (`seed/braniac_seed/whatsapp.py`): WhatsApp Web no navegador do assistente; a pessoa lê o QR uma vez. Funções: ver não lidas, ler conversa, enviar. Exige as permissões `whatsapp.ler` / `whatsapp.enviar`; o conteúdo só volta para a própria pessoa (nunca para IA online). *Ainda não inclui atendimento automático (responder sozinho).*
- **Telegram** (`remoto.py` + `pc_tools.py`): bot da própria pessoa. Travas: (1) desligado de fábrica; (2) pareamento por código de uso único exibido só na tela do PC — só o ID do dono é atendido, em conversa privada; (3) **armado** só pela tela local (por tempo limitado ou "sempre"); pelo Telegram só dá para desarmar (`/parar`); (4) toda ação passa pelas permissões; (5) ações perigosas (apagar, escrever, executar comando, enviar WhatsApp) exigem `SIM <código>` (2 min, uso único); (6) a IA só escolhe a ação a partir da mensagem do dono e **o resultado nunca volta para ela** (nada escondido em arquivo/mensagem manda no PC); (7) 30 comandos/min e auditoria em `remoto.log`.
- **App na bandeja** (`app/`): fechar a janela só a esconde; "Sair" no ícone encerra tudo; instância única; "Iniciar com o Windows" (opcional, escolha da pessoa) abre escondido com `--background`.
- Limite assumido: textos e prints enviados ao Telegram passam pelos servidores dele (a tela avisa).

## Voz natural e chaves de API (v0.2)

- A instalação **avisa logo no começo** que a voz está robótica (voz do sistema) porque ainda não há API conectada, e leva direto ao **passo a passo** para conseguir a primeira chave (Google primeiro). Só depois de validada a chave a voz passa a vir do serviço.
- **Voz natural** (`voz_nuvem.py`): Gemini TTS pela chave do Google da própria pessoa; voz feminina/masculina com 4 opções cada e 3 estilos (calmo, profissional, animado); texto limpo para fala, rejeição de áudio suspeito, acabamento (corte de silêncio, normalização), **cache em disco** (mesma fala = zero cota), rodízio de modelos e de chaves do Google (2ª e 3ª chave = mais cota), adianta a próxima fala. Sem chave/cota/internet cai na voz do sistema; **voz privada** nunca envia texto para fora.
- **Quanto mais chaves, melhor** (explicado como redundância + capacidade): cota gratuita diária por serviço, troca automática quando uma acaba, resposta mais rápida, voz natural o dia todo. A tela mostra o nível (Nenhuma / Básico / Bom / Excelente) e só revela as outras chaves depois da primeira (assistente guiado, uma de cada vez).
- Sugestões do conselho de IAs aplicadas: assistente gradual, indicador de nível, cache, fallback sempre, aviso de privacidade e modo privado. Ficaram para depois: TTS local offline (Piper) como base e outros serviços de voz.
- A tela nunca falha em silêncio: erros viram aviso visível e entram em `instalacao.log` (só no PC).
