# -*- coding: utf-8 -*-
"""Organiza a pasta Downloads do Dono (30/10/2026). So MOVE para subpastas por tipo; nunca apaga, nunca abre/executa, nunca toca em pasta existente.
Copia identica (mesmo conteudo) vai para 'Duplicados' em vez de ser apagada. Cada rodada grava o que moveu em data/organizador.json (desfazer = mover de volta)."""
import hashlib
import json
import time
from pathlib import Path

from .store import DATA

DOWNLOADS = Path.home() / "Downloads"
LOG = DATA / "organizador.json"
PARADOS = 600   # so mexe em arquivo parado ha 10 min (download em andamento fica quieto)
IGNORAR = {"desktop.ini"}
PARCIAIS = {".crdownload", ".part", ".tmp", ".download"}
CATEGORIAS = (
    ("Instaladores", {".exe", ".msi", ".msix", ".appx", ".winmd"}),
    ("Imagens", {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic"}),
    ("Videos", {".mp4", ".mov", ".mkv", ".avi", ".webm"}),
    ("Audios", {".mp3", ".wav", ".ogg", ".m4a", ".opus"}),
    ("Documentos", {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".txt", ".csv", ".odt"}),
    ("Paginas e codigo", {".html", ".htm", ".css", ".js", ".py", ".json", ".xml", ".ini"}),
    ("Compactados", {".zip", ".rar", ".7z", ".tar", ".gz"}),
)


def _hash(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _destino(p):
    if p.name.lower().startswith("client_secret") and p.suffix.lower() == ".json":
        return "Credenciais"   # segredo do Google: fica separado e sinalizado na checagem de seguranca
    return next((nome for nome, exts in CATEGORIAS if p.suffix.lower() in exts), "Outros")


def organizar(pasta=None, agora=None, simular=False):
    """Devolve [(origem, destino)] movidos (ou que seriam, se simular)."""
    pasta, agora = Path(pasta or DOWNLOADS), agora or time.time()
    vistos, movidos = {}, []
    for p in sorted(pasta.iterdir(), key=lambda x: (x.stat().st_mtime, len(x.name))):   # o original (mais antigo, nome mais curto) fica; a copia vai para Duplicados
        if not p.is_file() or p.name.lower() in IGNORAR or p.suffix.lower() in PARCIAIS or agora - p.stat().st_mtime < PARADOS:
            continue
        try:
            h = (p.stat().st_size, _hash(p))
            sub = "Duplicados" if h in vistos else _destino(p)
            vistos.setdefault(h, p)
            alvo = pasta / sub / p.name
            n = 1
            while alvo.exists():    # nunca sobrescreve
                alvo = pasta / sub / f"{p.stem} ({n}){p.suffix}"
                n += 1
            if not simular:
                alvo.parent.mkdir(exist_ok=True)
                p.rename(alvo)
            movidos.append((str(p), str(alvo)))
        except OSError:
            continue
    if movidos and not simular:
        LOG.write_text(json.dumps({"quando": time.strftime("%Y-%m-%d %H:%M"), "movidos": movidos}, ensure_ascii=False, indent=1), encoding="utf-8")
    return movidos


def rodar(registrar=None, **kw):
    """Organiza e anota no relatorio da madrugada (so se mexeu em algo)."""
    movidos = organizar(**kw)
    if movidos and registrar:
        dup = sum("Duplicados" in d for _, d in movidos)
        registrar(f"🗂️ Downloads organizado: {len(movidos)} arquivo(s) para subpastas por tipo ({dup} duplicado(s) separado(s), nada apagado).")
    return movidos


if __name__ == "__main__":
    import sys
    for o, d in rodar(simular="--simular" in sys.argv):
        print(Path(o).name, "->", Path(d).parent.name)
