# -*- coding: utf-8 -*-
"""LEADS DO GOOGLE MAPS (12/11/2026, pedido do Dono): lista de empresas (nome, telefone, site, categoria, endereco, nota) de um tipo de negocio numa cidade, pelo kit
google-maps-scraper-kit (Mahanaicoach, MIT) instalado em C:\\Users\\usuario\\Projetos\\google-maps-scraper-kit. Roda 100% local (Chrome proprio do kit, nunca o Chrome do Braniac), sem chave.
Travas do Braniac: so a pedido do Dono (prospeccao), sem proxy, volume baixo (ate 40 por busca, 3 buscas por dia), SEM e-mails nem redes sociais por padrao (LGPD: so dado comercial),
CSV so em E:\\braniac-link\\leads (fora do Git). Nao envia mensagem para ninguem: quem decide o contato e o Dono (regras de prospeccao do CLAUDE.md: Jarvis se identifica, dedup em prospeccao-contatados.md).
Aviso: raspar o Google Maps vai contra os termos de uso do Google; o risco e do uso, por isso o teto baixo."""
import csv
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

KIT = Path(os.environ.get("MAPS_KIT", r"C:\Users\usuario\Projetos\google-maps-scraper-kit"))
SAIDA = Path(r"E:\braniac-link\leads") if os.path.exists("E:\\") else Path(__file__).resolve().parent / "data" / "leads"
MAX_POR_BUSCA, MAX_BUSCAS_DIA = 40, 3
ARQ_USO = Path(__file__).resolve().parent / "data" / "leads_maps_uso.json"
SEGREDO = re.compile(r"senha|token|cpf|cart[aã]o|pix|chave de acesso", re.I)


def _py(*args, timeout=600):
    return subprocess.run([sys.executable.replace("pythonw.exe", "python.exe"), *args], cwd=str(KIT), capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, creationflags=0x08000000 if os.name == "nt" else 0, env=dict(os.environ, PYTHONIOENCODING="utf-8"))


def _usos_hoje():
    try:
        d = json.loads(ARQ_USO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    return d if d.get("dia") == time.strftime("%Y-%m-%d") else {"dia": time.strftime("%Y-%m-%d"), "n": 0}


def buscar(tipo, cidade, limite=20):
    """Devolve (caminho do csv, [{title, phone, website, category, address, review_rating, review_count}]). ValueError/RuntimeError com mensagem clara."""
    tipo, cidade = re.sub(r"\s+", " ", str(tipo or "")).strip()[:60], re.sub(r"\s+", " ", str(cidade or "")).strip()[:60]
    if len(tipo) < 3 or len(cidade) < 3:
        raise ValueError("preciso do tipo de negocio e da cidade (ex.: 'padarias', 'Cidade, MT')")
    if SEGREDO.search(tipo + cidade):
        raise ValueError("pedido com palavra de segredo: recusado")
    if not (KIT / "scripts" / "scrape.py").exists():
        raise RuntimeError(f"kit do scraper nao encontrado em {KIT}")
    limite = max(1, min(int(limite or 20), MAX_POR_BUSCA))
    uso = _usos_hoje()
    if uso["n"] >= MAX_BUSCAS_DIA:
        raise ValueError(f"teto de {MAX_BUSCAS_DIA} buscas por dia (para nao sobrecarregar nem irritar o Google)")
    uso["n"] += 1
    ARQ_USO.parent.mkdir(parents=True, exist_ok=True)
    ARQ_USO.write_text(json.dumps(uso), encoding="utf-8")
    SAIDA.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", f"{tipo}-{cidade}".lower().encode("ascii", "ignore").decode()).strip("-")[:50]
    csv_path = SAIDA / f"{time.strftime('%Y%m%d-%H%M')}-{slug}.csv"
    ini = _py("scripts/engine.py", "start", timeout=120)
    if ini.returncode:
        raise RuntimeError("motor do scraper nao subiu: " + (ini.stdout + ini.stderr)[-200:])
    try:
        r = _py("scripts/scrape.py", f"{tipo} em {cidade}", "--city", cidade, "--depth", "2", "--lang", "pt", "--country", "br", "--no-email", "--no-socials",
                "--limit", str(limite), "--out", str(csv_path), timeout=900)
    finally:
        _py("scripts/engine.py", "stop", timeout=60)
    if r.returncode or not csv_path.exists():
        raise RuntimeError("a busca nao terminou: " + (r.stderr or r.stdout)[-250:])
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        linhas = list(csv.DictReader(f))
    return csv_path, linhas
