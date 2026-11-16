---
name: baixar-video-youtube
description: Baixa vídeo ou áudio do YouTube (ou stream m3u8), ou pega a legenda/transcrição de um vídeo, para o Dono usar em cortes e edição. Use quando ele pedir para baixar, salvar ou transcrever um vídeo por link.
allowed-tools: delegar_ao_claude
---

# Baixar vídeo do YouTube

Quem baixa é o **Claude**, pela skill `youtube-downloader` (yt-dlp + ffmpeg, já instalados no PC). Você aciona com `delegar_ao_claude`.

1. Pegue só o que faltar, em 1 pergunta: **o link**, se é **vídeo ou só áudio**, e **para onde salvar** (padrão: `C:\Users\usuario\ArtCraft-Trabalho\downloads`).
2. Se ele só quer o TEXTO falado (legenda, transcrição, "o que ele disse"), diga ao Claude para tentar legenda existente antes de baixar o vídeo inteiro.
3. Chame `delegar_ao_claude` com a tarefa completa: link, formato, pasta, e a instrução "use a skill youtube-downloader; confirme o caminho, tamanho e resolução do arquivo final".
4. Responda ao Dono com o caminho do arquivo. Nunca extraia cookies do navegador sem ele autorizar.

Direitos: baixar só para uso pessoal ou com permissão; em cortes publicados, cite a fonte. Não baixe playlists inteiras sem confirmar.
