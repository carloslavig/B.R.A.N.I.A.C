# -*- coding: utf-8 -*-
"""Detecta o PC e escolhe o perfil de IA local (Leve / Equilibrado / Potente). Os modelos NAO vem no instalador: baixam sob demanda."""
import os, shutil, subprocess, sys

PERFIS = {
    "leve": {"titulo": "Leve", "ollama": "qwen2.5:1.5b", "whisper": "base", "download_gb": 1.5,
             "descricao": "Para PCs mais simples: respostas básicas e rápidas, voz no processador."},
    "equilibrado": {"titulo": "Equilibrado", "ollama": "qwen2.5:3b", "whisper": "small", "download_gb": 3.0,
                    "descricao": "Bom para a maioria dos PCs: conversa e voz com boa qualidade."},
    "potente": {"titulo": "Potente", "ollama": "qwen2.5:7b", "whisper": "small", "download_gb": 6.0,
                "descricao": "Para PCs com placa de vídeo boa: melhor qualidade offline e voz acelerada na GPU."},
}


def _ram_gb():
    if sys.platform != "win32":
        return 0.0
    import ctypes

    class MEM(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    m = MEM()
    m.dwLength = ctypes.sizeof(MEM)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return round(m.ullTotalPhys / 2 ** 30, 1)


def _gpu():
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=8)
        nome, mb = [x.strip() for x in r.stdout.strip().splitlines()[0].split(",")]
        return {"nome": nome, "vram_gb": round(float(mb) / 1024, 1)}
    except Exception:
        return None


def detectar(pasta=None):
    pasta = pasta or os.path.expanduser("~")
    return {"ram_gb": _ram_gb(), "cpus": os.cpu_count() or 1, "gpu": _gpu(), "disco_livre_gb": round(shutil.disk_usage(pasta).free / 2 ** 30, 1)}


def recomendar(info):
    """Devolve (id_do_perfil, motivo). Regras simples e conservadoras: nunca recomenda o que nao cabe."""
    ram, gpu, livre = info["ram_gb"], info.get("gpu"), info["disco_livre_gb"]
    if livre < 8:
        return "leve", "pouco espaço livre em disco: vou usar o modelo menor"
    if gpu and gpu["vram_gb"] >= 8 and ram >= 16:
        return "potente", f"placa de vídeo com {gpu['vram_gb']} GB e {ram:g} GB de memória"
    if ram < 8:
        return "leve", f"{ram:g} GB de memória: o modelo menor roda melhor"
    return "equilibrado", f"{ram:g} GB de memória" + (f" e placa de vídeo {gpu['nome']}" if gpu else "")
