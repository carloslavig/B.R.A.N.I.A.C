---
name: editar-arquivos-artcraft
description: Edita ou converte foto, lote de fotos, Word, PDF, planilha, slides, vetor, vídeo ou áudio do Dono com os apps ArtCraft instalados no PC. Use quando ele pedir para tratar/editar/converter/juntar/criar um desses arquivos.
allowed-tools: artcraft delegar_ao_claude
---

# Editar arquivos com o ArtCraft

**Primeiro tente a ferramenta `artcraft` (direto no PC, sem gastar o Claude):** converter/redimensionar/girar/preto e branco de foto, cartaz com texto, converter vetor, ler/juntar/dividir/extrair PDF, Word para PDF, planilha entre formatos, slides para PDF ou imagem, converter áudio, CAD para PDF, dados de vídeo. Ela já guarda o resultado em `ArtCraft-Trabalho` sem tocar no original. Só use `delegar_ao_claude` (abaixo) quando o pedido for edição de verdade: tratar lote de fotos, montar/editar vídeo, animação, diagramação, criar documento do zero.

Os apps ArtCraft (PhotoCraft, LightCraft, WordCraft, PdfCraft, GridCraft, DeckCraft, VectorCraft, DesignCraft, FilmCraft, SoundCraft, EffectCraft, CadCraft) estão no PC e quem os opera é o **Claude** (pelos servidores MCP deles). Você aciona com `delegar_ao_claude`.

1. Junte em 1 pergunta só o que faltar: **qual arquivo/pasta** (caminho ou onde está), **o que fazer** e **formato de saída**. Não pergunte o que ele já disse.
2. Chame `delegar_ao_claude` com uma tarefa completa, por exemplo:
   "Use a skill artcraft: copie as fotos de E:\.Fotografia\2026\Evento X para a pasta de trabalho, aplique tratamento natural (exposição, branco, contraste leve) no LightCraft e exporte JPG 2048px qualidade 90 em C:\Users\usuario\ArtCraft-Trabalho\Evento X\final. Não altere os originais."
3. Diga ao Dono que o Claude está fazendo e que o resultado chega quando terminar (ele fica em `C:\Users\usuario\ArtCraft-Trabalho`).
4. Nunca prometa prazo exato nem diga que terminou antes do resultado chegar.
