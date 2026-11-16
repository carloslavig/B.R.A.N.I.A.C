---
name: estudio-3d
description: Faz um video curto explicativo em 3D (vertical, para Reels/TikTok/Shorts) no Estudio 3D do Dono. Use quando o Dono pedir um video explicativo, reel ou short em 3D sobre um tema.
allowed-tools: estudio_3d delegar_ao_claude
---

# Estudio 3D (video curto explicativo em 3D)

O estudio fica em `C:\Users\usuario\Projetos\Estudio3D` (Remotion + three.js, feito do zero).

## Tema geral (conceito conhecido, sem estatistica)
Use a ferramenta `estudio_3d` com o tema. O Jarvis escreve o roteiro com IA gratis, narra, sincroniza a legenda e renderiza no PC, em segundo plano (alguns minutos, ~2 min de render). Quando fica pronto, avisa o Dono com o caminho do arquivo. Teto: 3 por dia, um por vez.

## Politica, saude, financas ou qualquer dado/estatistica
A ferramenta recusa. Delegue ao Claude com `delegar_ao_claude` (skill `estudio-3d` dele): ele pesquisa, cita as fontes primarias e produz.

Regras:
- E sempre RASCUNHO: o Dono confere antes de publicar. O Jarvis nunca publica nem posta.
- O Dono nao le bem: o aviso de pronto tambem vai em AUDIO.
- Nunca usar o Chrome do Braniac para isso (o render e local e sem navegador).
