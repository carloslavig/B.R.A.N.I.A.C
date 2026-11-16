---
name: animacoes-reels
description: Gera animações prontas para reels (gráfico de linha com número que conta, linha minimalista, rota em mapa 3D, vista explodida de aparelho, e os estilos stick-figure e 3D cartoon). Use quando o Dono pedir animação, gráfico animado, rota no mapa ou "o que tem dentro" de um aparelho, para outros projetos que não sejam as contas das prefeituras.
allowed-tools: animacao delegar_ao_claude
---

# Animações para reels (repositório claude-animation-skills, MIT)

Origem: `artemnovitckii/claude-animation-skills` (licença em `skills/_licencas/`). Nada disso gasta IA para renderizar.

## Use a ferramenta `animacao` (você mesmo, sem o Claude)
`animacao(tipo, spec)` gera o mp4 vertical em `E:\braniac-link\animacoes\<data>-<tipo>\`. Teto de 8 por dia. Nunca publica.
| tipo | O que faz | Onde ver o spec |
|---|---|---|
| `graph` | linha que se desenha + número grande que conta | `skills/graph/SKILL.md` |
| `minimalistic-graphics` | degraus de linha fina, um ponto que sobe | `skills/minimalistic-graphics/SKILL.md` |
| `map-route` | rota em mapa 3D com pino e ETA | `skills/map-route/SKILL.md` |
| `breakdown` | vista explodida de um aparelho com legendas | `skills/breakdown/SKILL.md` |
Leia o SKILL.md do tipo (use_skill) só para ver os campos do JSON. Números **sempre reais**: nunca invente dado; se faltar ponto, pergunte.

## Só o Claude faz (use `delegar_ao_claude`)
`stick-figure` (explicador com bonecos) e `zach-d-films` (explicador 3D cartoon): precisam escrever cenas em código. A voz grátis deles (Kokoro) não foi instalada; use a voz do Braniac.

## Para contas de prefeitura/dados oficiais
Não use estas: use o Estudio3D (peças `mapa`, `numero`, `linha`, `barras`) pela fila do Aliado (skill `fila-render-aliado`).

## Regras
- Rascunho: o Dono confere antes de publicar. Aviso de pronto em ÁUDIO curto.
- Dados com senha/CPF/cartão/Pix são recusados.
- Se der erro, leia o fim da mensagem: falta de `kit/node_modules` = animações não instaladas; avise o Dono.
