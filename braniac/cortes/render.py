# -*- coding: utf-8 -*-
"""Render vertical 9:16 (1080x1920) com ffmpeg: corte + enquadramento + legenda queimada + volume normalizado.
Usa a NVENC da GTX 1650 (h264_nvenc); se falhar, cai no libx264 (CPU)."""
import subprocess, sys
from pathlib import Path

SEM_JANELA = 0x08000000 if sys.platform == "win32" else 0


def filtro_video(modo="desfocado", ass_nome=None):
    if modo == "centro":  # recorte central: bom quando a acao fica no meio (camera, conversa)
        f = "[0:v]scale=-2:1920,crop=1080:1920,setsar=1[v0]"
    else:  # video inteiro no meio, fundo = o mesmo video ampliado e borrado (nao perde HUD/placar do jogo)
        f = ("[0:v]split=2[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:2,eq=brightness=-0.08[bg];"
             "[b]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[v0]")
    if ass_nome:
        f += f";[v0]ass={ass_nome}[v]"
    else:
        f += ";[v0]null[v]"
    return f


def _cmd(video, inicio, dur, saida, filtro, codec):
    v = (["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "23", "-b:v", "8M", "-maxrate", "12M", "-bufsize", "16M"]
         if codec == "nvenc" else ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21"])
    return ["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", f"{inicio:.2f}", "-i", str(video), "-t", f"{dur:.2f}",
            "-filter_complex", filtro, "-map", "[v]", "-map", "0:a:0?", *v, "-pix_fmt", "yuv420p", "-r", "30",
            "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
            "-movflags", "+faststart", str(saida)]


def renderizar(video, inicio, fim, saida, ass=None, modo="desfocado"):
    """Gera o mp4 vertical. `ass` (opcional) e o arquivo de legenda; o ffmpeg roda na pasta dele (evita escapar 'C:' no filtro)."""
    saida = Path(saida).resolve()
    saida.parent.mkdir(parents=True, exist_ok=True)
    pasta = Path(ass).resolve().parent if ass else saida.parent
    filtro = filtro_video(modo, Path(ass).name if ass else None)
    erro = ""
    for codec in ("nvenc", "x264"):
        p = subprocess.run(_cmd(Path(video).resolve(), inicio, fim - inicio, saida, filtro, codec), cwd=pasta,
                           capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=SEM_JANELA)
        if p.returncode == 0 and saida.exists() and saida.stat().st_size > 10_000:
            return saida
        erro = p.stderr.strip()[-400:]
    raise RuntimeError("ffmpeg falhou: " + erro)


def miniatura(video, destino, t=1.0):
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
                    "-vf", "scale=540:-2", str(destino)], check=False, creationflags=SEM_JANELA)
    return destino


def duracao(video):
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(video)],
                       capture_output=True, text=True, creationflags=SEM_JANELA)
    try:
        return float(p.stdout.strip())
    except ValueError:
        return 0.0
