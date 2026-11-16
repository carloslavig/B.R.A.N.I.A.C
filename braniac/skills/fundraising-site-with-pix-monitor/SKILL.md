---
name: fundraising-site-with-pix-monitor
description: Quando precisar criar um site de vaquinha que mostra o total arrecadado em tempo real ao detectar pagamentos via PIX.
allowed-tools: nodejs express django flask sqlite postgresql mongodb stripe pix api webhook service socket io django channels
metadata:
  origem: criada pelo B.R.A.N.I.A.C 1 em 27/10/2026
---

# fundraising-site-with-pix-monitor

1. Definir requisitos básicos (página de doação, exibição do total, página de agradecimento).
2. Escolher uma stack web (ex.: Node.js/Express, Django, Flask, etc.) e configurar o projeto.
3. Criar banco de dados para armazenar doações (ex.: SQLite, PostgreSQL, MongoDB).
4. Implementar formulário de doação que gera um QR‑Code ou link PIX usando a API do banco ou serviço de pagamento.
5. Configurar webhook ou polling no serviço PIX para receber notificações de pagamentos recebidos na conta especificada.
6. Desenvolver endpoint que valida a notificação, registra a doação no banco e atualiza o valor total.
7. Integrar WebSocket (ex.: Socket.io, Django Channels) ou Server‑Sent Events para enviar ao cliente o novo total assim que a doação for registrada.
8. Na página de exibição, conectar ao WebSocket e atualizar dinamicamente o valor exibido.
9. Testar todo o fluxo usando contas de teste ou sandbox do PIX.
10. Deploy em um serviço de hospedagem (ex.: Vercel, Heroku, Render) e garantir HTTPS para segurança.
