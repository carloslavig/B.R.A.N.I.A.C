# -*- coding: utf-8 -*-
"""Legenda local: faster-whisper (small; GTX 1650 em float16, senao CPU int8) com tempo de cada palavra -> arquivo .ass
no estilo Shorts/TikTok (palavras grandes, 2-3 por vez, a palavra falada em amarelo)."""
import gc, subprocess, sys, threading
from pathlib import Path
from . import config

SEM_JANELA = 0x08000000 if sys.platform == "win32" else 0
_lock = threading.Lock()
_modelo = None
MOTOR = ""


def _carregar():
    global _modelo, MOTOR
    if _modelo is not None:
        return _modelo
    from faster_whisper import WhisperModel
    from .. import voz
    voz._dll_cuda()
    caminho = config.carregar().get("whisper_modelo") or str(voz.WHISPER)
    try:
        import numpy as np
        m = WhisperModel(caminho, device="cuda", compute_type="float16")
        list(m.transcribe(np.zeros(16000, dtype=np.float32), beam_size=1)[0])  # as DLLs CUDA so carregam aqui
        MOTOR = "gpu"
    except Exception:
        import os
        m = WhisperModel(caminho, device="cpu", compute_type="int8", cpu_threads=max(4, (os.cpu_count() or 8) // 2))
        MOTOR = "cpu"
    _modelo = m
    return m


def liberar():
    """Solta a VRAM depois do lote (a GTX 1650 tem so 4 GB e o Ollama/voz tambem usam)."""
    global _modelo
    with _lock:
        _modelo = None
        gc.collect()


def extrair_wav(video, inicio, fim, destino):
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", f"{inicio:.2f}", "-i", str(video), "-t", f"{fim - inicio:.2f}",
                    "-vn", "-ac", "1", "-ar", "16000", str(destino)], check=True, creationflags=SEM_JANELA)
    return destino


def transcrever(wav, idioma="pt"):
    """(palavras [(ini, fim, texto)], texto_corrido) com tempos relativos ao inicio do wav."""
    with _lock:
        m = _carregar()
        segs, _ = m.transcribe(str(wav), language=idioma or None, word_timestamps=True, vad_filter=True, beam_size=5,
                               condition_on_previous_text=False)
        palavras, frases = [], []
        for s in segs:
            frases.append(s.text.strip())
            for w in s.words or []:
                t = w.word.strip()
                if t:
                    palavras.append((float(w.start), float(w.end), t))
    return palavras, " ".join(frases).strip()


def _tempo(s):
    s = max(0.0, s)
    return f"{int(s // 3600)}:{int(s % 3600 // 60):02d}:{s % 60:05.2f}"


def _escapar(t):
    return t.replace("\\", "").replace("{", "(").replace("}", ")")


def agrupar(palavras, max_palavras=3, max_chars=16):
    grupos, atual = [], []
    for w in palavras:
        texto = " ".join(x[2] for x in atual + [w])
        if atual and (len(atual) >= max_palavras or len(texto) > max_chars or w[0] - atual[-1][1] > 0.6):
            grupos.append(atual)
            atual = []
        atual.append(w)
    if atual:
        grupos.append(atual)
    return grupos


def gerar_ass(palavras, destino, margem_v=470, tamanho=80):
    """Escreve o .ass: cada grupo fica na tela inteiro, com a palavra da vez em amarelo."""
    cab = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Corte,Arial Black,{tamanho},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,1,0,1,7,3,2,60,60,{margem_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    linhas = []
    for g in agrupar(palavras):
        for i, (ini, fim, _) in enumerate(g):
            prox = g[i + 1][0] if i + 1 < len(g) else fim
            partes = [("{\\c&H00F0FF&}" + _escapar(w[2]).upper() + "{\\c&HFFFFFF&}") if j == i else _escapar(w[2]).upper()
                      for j, w in enumerate(g)]
            linhas.append(f"Dialogue: 0,{_tempo(ini)},{_tempo(max(prox, ini + 0.05))},Corte,,0,0,0,,{' '.join(partes)}")
    Path(destino).write_text(cab + "\n".join(linhas) + "\n", encoding="utf-8")
    return destino
