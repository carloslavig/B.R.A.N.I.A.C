---
name: modelo-3d
description: Cria uma peca/objeto 3D parametrico (CAD) a partir de uma descricao ou foto e mostra no visualizador 3D do PC (http://localhost:3123), com exportacao .glb, .step e .stl para impressao 3D. Use quando o Dono pedir "faz um modelo 3D", "desenha uma peca", "cria um suporte/engrenagem/caixa", "recria este objeto da foto".
allowed-tools: delegar_ao_claude
---

# Modelo 3D (skill /render do Claude)

Quem faz e o Claude, com a skill `render` dele (`.claude/skills/render`, build123d + visualizador Three.js local).
O Jarvis so delega com `delegar_ao_claude`, passando a descricao (e o caminho da foto, se houver), por exemplo:
"Use a skill render: suporte de celular para mesa, 70 mm de largura, angulo de 60 graus."

Regras:
- Peca de impressao 3D: pedir as medidas que o Dono souber (mm). Sem medida, o Claude pesquisa a medida padrao e diz o que assumiu.
- O resultado fica em `.claude/skills/render/viewer/models/<nome>.glb/.step/.stl`; o Dono ve em http://localhost:3123 (so no PC dele).
- Nao confundir com o Estudio 3D (video explicativo) nem com o Blender (render de produto): esta skill e para PECA/CAD.
- O Dono nao le bem: o aviso de pronto vai em AUDIO curto, com o nome do modelo.
- Nunca expor a porta 3123 para fora do PC.
