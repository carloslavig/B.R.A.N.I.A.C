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

## Estado atual (`seed/`)
Feito e testado: permissões, cofre de chaves, validação de chaves, hardware/perfis, nome e voz (com sugestões), roteiro da instalação, atualizador com hash + rollback.
Falta: casca Tauri, empacotamento do sidecar Python, tela de instalação (UI), adapters ChatGPT/Gemini, núcleo do Braniac (extração do código atual sem dados pessoais), modo jogo, ícone flutuante/bandeja.
