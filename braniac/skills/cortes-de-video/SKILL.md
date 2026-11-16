---
name: cortes-de-video
description: Abre e acompanha pedidos de corte vertical (fala + gameplay + legenda) na Claquete, o 5o andar. Use quando o Dono pedir corte de entrevista/podcast para TikTok, Kwai ou YouTube.
allowed-tools: cortes_video
---

# Cortes de vídeo (Claquete)

- `abrir`: fonte (arquivo local ou URL), autor (sempre citado no vídeo) e gameplay (arquivo local). Sem autor ou sem gameplay, não abre.
- `trabalhar` avança um estado por vez: transcrito, cortado, montado, legendado, revisado, aguardando OK. `quadro` mostra a fila.
- `aprovar` só com o OK do Dono e só depois de `direitos_ok` e `gameplay_ok` virarem true em `data/empresa_cortes/equipe.json`. Agenda TikTok (09:00 e 20:00) e copia para a pasta do Kwai; YouTube espera o ritmo do conselho.
- Nunca publique por conta própria. Trechos curtos (20 a 45 s). Sem senha, CPF, cartão ou Pix em pedido.
- A rotina antiga da Twitch (`cortes`) está pausada (`data/cortes/PAUSA_ANDAR`); não confundir.
