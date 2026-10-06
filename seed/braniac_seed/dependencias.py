# -*- coding: utf-8 -*-
"""Dependencias da IA LOCAL: Ollama + modelo do perfil escolhido. Baixa sob demanda, com progresso. So acontece quando a pessoa manda
instalar (a tela diz o tamanho antes). Nao ha download escondido."""
import json, os, shutil, subprocess, sys, urllib.request

OLLAMA_API = "http://127.0.0.1:11434"
OLLAMA_SETUP_URL = "https://ollama.com/download/OllamaSetup.exe"


def ollama_exe():
    p = shutil.which("ollama")
    if p:
        return p
    for c in (os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"), r"C:\Program Files\Ollama\ollama.exe"):
        if os.path.exists(c):
            return c
    return None


def ollama_no_ar(get=None):
    try:
        (get or (lambda u: urllib.request.urlopen(u, timeout=3).read()))(OLLAMA_API + "/api/tags")
        return True
    except Exception:
        return False


def modelos_instalados(get=None):
    try:
        raw = (get or (lambda u: urllib.request.urlopen(u, timeout=5).read()))(OLLAMA_API + "/api/tags")
        return [m["name"] for m in json.loads(raw).get("models", [])]
    except Exception:
        return []


def estado(modelo, get=None):
    inst = ollama_exe() is not None
    no_ar = ollama_no_ar(get)
    mods = modelos_instalados(get) if no_ar else []
    return {"ollama_instalado": inst, "ollama_no_ar": no_ar, "modelo": modelo, "modelo_pronto": any(m.startswith(modelo) for m in mods)}


def subir_ollama():
    """Inicia o servico do Ollama (sem janela)."""
    exe = ollama_exe()
    if not exe:
        raise RuntimeError("Ollama não está instalado")
    subprocess.Popen([exe, "serve"], creationflags=0x08000000 if sys.platform == "win32" else 0)


def baixar_modelo(modelo, progresso=None, post_stream=None):
    """Puxa o modelo pelo Ollama relatando % (progresso(pct, texto)). post_stream injetavel para teste."""
    def real(url, corpo):
        req = urllib.request.Request(url, json.dumps(corpo).encode("utf-8"), {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=3600) as r:
            for linha in r:
                if linha.strip():
                    yield json.loads(linha)
    ultimo = None
    for ev in (post_stream or real)(OLLAMA_API + "/api/pull", {"model": modelo, "stream": True}):
        if ev.get("error"):
            raise RuntimeError(ev["error"])
        if ev.get("total") and progresso:
            progresso(int(100 * ev.get("completed", 0) / ev["total"]), ev.get("status", ""))
        ultimo = ev.get("status")
    return ultimo == "success"


def baixar_instalador_ollama(destino, progresso=None):
    """Baixa o instalador oficial do Ollama (so do dominio oficial). Quem executa e a propria pessoa/instalador, com a confirmacao dela."""
    if not OLLAMA_SETUP_URL.startswith("https://ollama.com/"):
        raise RuntimeError("endereço inesperado")
    with urllib.request.urlopen(OLLAMA_SETUP_URL, timeout=60) as r, open(destino, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        feito = 0
        while True:
            bloco = r.read(1 << 20)
            if not bloco:
                break
            f.write(bloco)
            feito += len(bloco)
            if total and progresso:
                progresso(int(100 * feito / total), "baixando o Ollama")
    return destino
