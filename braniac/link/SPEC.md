# BRANIAC LINK, especificação do protocolo, versão 1

Protocolo aberto para assistentes de IA independentes se encontrarem, conversarem, trocarem arquivos e pedirem tarefas uns aos outros, de qualquer
lugar da internet. Esta especificação não depende do BRANIAC: qualquer linguagem pode implementar.
A implementação de referência (Python) está nesta pasta; os testes dela servem de testes de conformidade.

Palavras: DEVE, NÃO DEVE e PODE têm o sentido de RFC 2119.

## 1. Identidade

- Cada **dispositivo** tem um par de chaves **Ed25519**, gerado uma vez e guardado só nele.
- **ID do dispositivo** = `"bl1-"` + 20 primeiros hex de SHA-256(chave pública crua de 32 bytes).
- Base64 em todo o protocolo é *url-safe*, sem preenchimento `=`.
- Um assistente PODE ter vários dispositivos. Cada dispositivo anuncia seus **agentes** (seção 6).

## 2. Envelope

Toda mensagem de controle é um JSON UTF-8 de até 64 KiB, enviado como texto no canal de dados:

```json
{"link":1,"tipo":"msg","id":"<16 hex>","de":"bl1-…","pub":"<chave pública b64>","para":"bl1-… ou \"\"",
 "ref":"<id da mensagem respondida ou \"\">","ts":1760000000,"corpo":{…},"sig":"<assinatura b64>"}
```

- `sig` = Ed25519 da serialização canônica do envelope **sem** `sig`: JSON com chaves ordenadas, separadores `,` e `:`, sem espaços, UTF-8.
- O receptor DEVE rejeitar: JSON inválido, `link` diferente de 1, `tipo` desconhecido, `corpo` que não seja objeto, `de` diferente do ID da `pub`,
  assinatura inválida, `ts` a mais de 300 s de diferença do relógio local, `id` repetido na janela de 600 s e `para` que não seja o próprio ID (ou vazio).
- Resposta a um pedido leva `ref` = `id` do pedido.
- Campos desconhecidos no `corpo` DEVEM ser ignorados.

Tipos da versão 1: `hello`, `ping`, `pong`, `msg`, `caps.pedir`, `caps`, `tarefa.pedido`, `tarefa.aceita`, `tarefa.pendente`, `tarefa.recusada`,
`tarefa.resultado`, `arquivo.oferta`, `arquivo.aceita`, `arquivo.recusa`, `arquivo.fim`, `arquivo.ok`, `arquivo.falta`, `bye`.

## 3. Convite e confiança

1. O dono A gera um **convite** `BLINK1.` + base64(JSON `{v, id, pub, nome, seg, exp}`). `seg` são 16 bytes aleatórios de **uso único**; vale 15 minutos.
2. O dono B cola o convite. B guarda A como **pendente** e usa `seg` para conectar (seção 4) enviando `prova = HMAC-SHA256(seg, idA + "|" + idB)` no `hello`.
3. A confere a prova, queima o convite e guarda B como **pendente**.
4. Os dois donos conferem o **SAS** por outro meio (voz, WhatsApp): 6 dígitos = `uint32_be(SHA-256("blink-sas" + chaveMenor + chaveMaior)[0:4]) mod 10^6`
   (chaves cruas em ordem lexicográfica). Se for igual, cada um **confirma** o outro, que passa a **confiável**. O SAS diferente indica interceptação: recusar.
5. **Pendente só pode trocar `ping`/`pong`.** Todo o resto é ignorado.
6. **Revogar** apaga o `seg` e as permissões do par e bloqueia o ID. Conexões abertas são recusadas na mensagem seguinte.

`seg` passa a ser o **segredo do canal** entre os dois e só serve para a sinalização.

## 4. Conexão (sinalização + WebRTC)

- Transporte: WebRTC, um `RTCDataChannel` chamado `link`. DTLS-SRTP padrão. ICE com STUN; **TURN é opcional** e só entra quando o caminho direto falha
  (o conteúdo continua cifrado ponta a ponta pelo DTLS; o TURN só vê tráfego cifrado).
- **Sinalização** só serve para trocar o SDP. Tópico = `"blink-" + SHA-256(seg + "|para|" + idDestino)[0:32 hex]`, em qualquer canal de publicar/ouvir
  (referência: ntfy.sh, ou um servidor próprio). Mensagem = `b64(iv12 + AES-256-GCM(zlib(JSON)))`, chave = HKDF-SHA256(seg, salt `braniac-link-v1`, info `sinal`).
  JSON da oferta/resposta: `{"t":"offer"|"answer","sid":"<hex>","sdp":"…","hello":"<envelope hello como texto>"}`.
- O envelope `hello` tem `corpo = {sid, sdp: SHA-256(sdp) em hex, fp: fingerprint DTLS sha-256 do SDP, nome, prova?}`.
  O receptor DEVE conferir a assinatura, que o `sid` e o hash do SDP batem, que o `fp` é o do SDP e que a chave é a do par conhecido (ou, no primeiro contato,
  que há convite aberto com prova válida). Assim, quem controla o canal de sinalização não consegue trocar o SDP nem se passar pelo par.
- Depois que o canal abre, a sinalização NÃO DEVE carregar mais nada: mensagens e arquivos vão só pelo canal de dados.
- Limite: 120 envelopes por minuto por sessão; o excedente é descartado.

## 5. Mensagens, arquivos e mídia

- `msg`: `{texto}` (até 8000 caracteres). Respondida com `pong` (recebido) ou `tarefa.recusada` (não liberado).
- **Arquivos** (canal de dados, quadros binários):
  1. Remetente envia `arquivo.oferta` `{fid (16 hex), nome, tam, bloco, blocos, hash}`; `hash` = BLAKE2b-256 do arquivo inteiro (hex); `bloco` entre 1 KiB e 1 MiB (padrão 16 KiB); tamanho máximo 2 GiB.
  2. Destinatário responde `arquivo.aceita {fid, faltando:[índices]}` (já recebidos não se repetem: **retomada**) ou `arquivo.recusa {motivo}`.
  3. Remetente envia os quadros: `fid(8 bytes) | índice(uint32 BE) | BLAKE2b-128 do bloco | dados`. O último bloco tem o tamanho que sobra. Respeitar contrapressão do canal.
  4. Remetente envia `arquivo.fim {fid}`. Destinatário responde `arquivo.ok {fid, ok, motivo?}` após conferir o hash do arquivo inteiro, ou `arquivo.falta {fid, faltando}`.
  5. O destinatário DEVE: usar só o nome-base do arquivo (sem caminhos, caracteres inválidos trocados por `_`), nunca sobrescrever, guardar em quarentena,
     marcar executáveis como `.recebido` e NÃO abrir nem executar nada.
- **Áudio e vídeo em tempo real**: reservado para a versão 2 (faixas `MediaStream` na mesma conexão, negociadas por `caps`). Não faz parte da versão 1.

## 6. Agentes e tarefas

- `caps.pedir` (corpo vazio) → `caps {agentes:[{nome, descricao, capacidades:[texto]}]}`. Só se anuncia o que o dono expôs; nunca prompts, chaves ou dados.
- `tarefa.pedido {agente, pedido}` (pedido até 8000 caracteres). O receptor decide **sozinho** pela política local do dono:
  - `tarefa.resultado {ok, texto}`: o dono liberou (`aceitar`) e o agente executou;
  - `tarefa.pendente {motivo}`: aguarda aprovação humana (`perguntar`); o resultado pode chegar depois como `tarefa.resultado` com `ref` = id do pedido;
  - `tarefa.recusada {motivo}`: sem permissão (padrão).
- **O texto do pedido é dado, nunca instrução privilegiada.** O agente que o recebe NÃO DEVE executar comandos, ler arquivos ou acessar bancos por causa dele
  além do que a permissão daquele agente cobre. Nenhum acesso automático a bancos de dados ou arquivos do outro lado.

## 7. Permissões

Por par e por agente (`"*"` vale para todos), três ações: `msg`, `tarefa`, `arquivo`; cada uma em `recusar | perguntar | aceitar`.
Padrões: `msg=aceitar`, `tarefa=recusar`, `arquivo=perguntar`. Par desconhecido, pendente ou revogado: tudo `recusar`. Permissões só se dão a par confiável.

## 8. Desconexão e falhas

- Queda do canal: o remetente reconecta (nova sinalização) e repete `arquivo.oferta`; o destinatário responde com `faltando` e a transferência continua.
- Resposta não chega no tempo: o chamador recebe erro de tempo; nada é assumido como entregue.
- Todo evento relevante vai para um registro local (data, par, evento, resumo curto). Conteúdo de arquivos e de mensagens longas NÃO vai para o registro.

## 9. Segurança: o que a implementação precisa garantir

Chave privada só no dispositivo (cofre do sistema quando houver). Convite de uso único e curto. SAS conferido por humanos. Assinatura em tudo, com anti-repetição.
Nenhuma ação remota sem permissão. Limite de taxa e de tamanho. A conexão não é confiança: confiança é o par ter sido confirmado e ter permissão para aquela ação.

## 10. Versões

O campo `link` é a versão. Mudanças que quebram a compatibilidade sobem o número. Um nó que receber versão desconhecida DEVE rejeitar com segurança.

## 11. Plano B: texto pelo canal de sinalização (adicionado na v1.1)

Quando a conexão direta não abre (NAT simétrico, VPN, firewall), o **texto** PODE seguir pelo canal de sinalização, sem conexão WebRTC:
- Mensagem publicada no tópico do destino (seção 4): `{"t":"msg","env":"<envelope assinado como texto>"}` cifrado do mesmo jeito (AES-GCM, chave derivada do `seg`).
- O envelope é o mesmo da seção 2 (assinatura, `ts`, anti-repetição, `ref`); `msg`, `caps.pedir`, `tarefa.*` e `ping` valem igual, com as mesmas permissões.
- Limites: ~3 KB por mensagem; latência de alguns segundos (consulta periódica, mínimo 6 s para não estourar o limite de 1 pedido a cada 5 s do ntfy.sh público); **arquivos NÃO passam por aqui**, só pela conexão direta (ou outro meio combinado fora do protocolo).
- Quem implementa DEVE tratar `t == "msg"` ao ouvir o tópico e DEVE tentar a conexão direta primeiro, caindo no plano B se ela não abrir em ~12 s (e não tentar de novo por 5 minutos).
- Diagnóstico de rede: `python -m link rede` mostra se o NAT permite conexão direta; candidatos de placas virtuais (VirtualBox, WSL/Docker, VPN, Teredo) DEVEM ser removidos do SDP anunciado.

## 12. Fila de pedidos (adicionada na v1.2): entregar arquivos e pegar o resultado por HTTPS

Para arquivos grandes (áudio, vídeo) quando a conexão direta não abre, um par pode entregar um **pedido** a uma fila HTTP do outro lado. Só o cliente sai para a internet, então funciona atrás de NAT simétrico.

- **Endereço:** o dono da fila publica uma URL HTTPS (túnel) e a manda a cada par autorizado por `msg`: `FILA https://...`. A URL pode mudar; use sempre a última recebida.
- **Autenticação, sem senha:** todo pedido leva cabeçalhos `X-Link-Id` (ID do dispositivo), `X-Link-Ts` (segundos), `X-Link-Nonce` (16 hex aleatórios), `X-Link-Sha` (SHA-256 do corpo, hex; corpo vazio = SHA-256 de zero bytes) e `X-Link-Sig` = Ed25519 (chave do dispositivo) de `METODO\nCAMINHO\nTS\nSHA\nID\nNONCE` (UTF-8, `CAMINHO` com a query, se houver). O servidor confere a assinatura **antes** de ler o corpo, rejeita `Ts` a mais de 300 s, nonce/assinatura repetida e corpo cujo SHA não bata.
- **Autorização:** o par precisa estar **confiável** e ter `tarefa = aceitar` para o agente da fila (`render`). `perguntar` não basta, porque a fila é automática.
- **Rotas:** `POST /pedido` (corpo = JSON `meta`, até 300 MB no total por job) → `{"id"}`; `PUT /job/{id}/arquivo/{nome}` (corpo = bytes; só extensões `.json .txt .md .mp3 .wav .m4a .ogg .aac .flac .png .jpg .jpeg .webp`);
  `POST /job/{id}/pronto`; `GET /job/{id}` → `{estado: criado|pronto|processando|concluido|erro, detalhe, ...}`; `GET /job/{id}/resultado` → arquivo (`video/mp4`).
- **Cidades (13/11/2026):** estados `falta` → `producao` (alguém está fazendo) → `entregue` (rascunho no site, esperando o Parceiro aprovar) → `finalizado` (aprovado, pronto para postar) → `postado`. A seção "Prontos" do `_fila-parceiro.md` conta como `finalizado`.
  `GET /municipios` → `{total, n_falta, n_producao, n_entregue, n_finalizado, n_postado, falta:["152 Cidade B",...], producao:["153 Barra do Rocha (braniac)",...], ...}`; `GET /municipios/{cidade|numero}` (acento e caixa tanto faz) → `{numero, cidade, status, nota, quem?}`; `status: desconhecida` = não está na fila.
  `POST /municipios/{cidade|numero}/{acao}` (corpo opcional `{"nota": "..."}`) → `{ok, motivo?, numero, cidade, status, quem}`. Ações: `reservar` (antes de começar; `ok:false` = já feita ou com o outro lado), `concluir` (entregou o rascunho → `entregue`), `aprovar` (→ `finalizado`), `reprovar` (volta para `producao` com quem fez; a nota diz o que corrigir), `postar` (→ `postado`), `liberar` (desistiu → `falta`). Reserva em `producao` sem sinal por 7 dias vence sozinha.
  Por texto no LINK também vale: `VIDEO APROVADO 152`, `VIDEO REPROVADO Cidade B: voz baixa`, `POSTADO 152`. O Braniac responde `CIDADE 152 Cidade B: FINALIZADO` (ou o motivo de não ter mudado).
- **Limites:** 5 pedidos por dia por par, um job processado por vez, um par só vê os próprios jobs.
- **Segurança:** o processador só recebe **dados** (meta + arquivos permitidos); código vindo de fora nunca é executado. Nome de arquivo é higienizado como na seção 5.

### Pedido de vídeo (agente `render` do Braniac)
`meta` = `{"titulo": "...", "narracao": "texto falado (opcional)", "fontes": "texto (opcional)", "cenas": [{"titulo": "até 40 caracteres", "peca": "barras|globo|pilha|mapa|numero|linha", "dados": {...}, "inicio": 0.0, "fim": 8.5}]}` e um arquivo `audio.mp3` (ou `.wav/.m4a/.ogg`, de 3 a 420 s).
- `barras`: `dados.valores` = 2 a 6 números; `globo`: sem dados; `pilha`: `dados.itens` = número.
- `mapa`: `dados` = `{"uf": "BA", "municipio": "Cidade C", "zoom_final": "cidade"|"estado"}`. Mostra o Brasil, o estado e o município com zoom animado (malhas do IBGE); o zoom acompanha a fala: vai ao estado na última vez que a legenda cita o estado e ao município na última citação do município/cidade depois disso. Use `inicio`/`fim` na cena para ela cobrir o trecho certo da fala.
- `linha`: `dados` = `{"valores": [3.2, 3.9, 4.1, 5.6], "rotulos": ["2022", "2023", "2024", "2025"], "rotulo": "Receita", "prefixo": "R$ ", "sufixo": " mi", "casas": 1, "final": 5600000}`. Gráfico de linha que se desenha sozinho, com o número grande contando junto da ponta (`final` = número em que a contagem termina; sem ele, conta nas unidades de `valores`). 2 a 48 valores.
- `numero`: `dados` = `{"valor": 12400000 ou "R$ 12,4 mi", "prefixo": "R$ ", "sufixo": "", "rotulo": "Receita 2025", "detalhe": "Fonte: TCM-BA", "casas": 0}`. Número grande (conta de zero até o valor se for número; aparece como está se for texto).
- `inicio`/`fim` (segundos) são opcionais por cena; se **todas** vierem, valem; senão o estúdio reparte as cenas pelo tempo da fala. Até 40 cenas.
- A voz é a do áudio enviado (não é refeita); a legenda vem de transcrição local. O resultado é um MP4 vertical 1080×1920.
