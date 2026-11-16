# -*- coding: utf-8 -*-
"""ANIMACOES para reels (12/11/2026): quatro animacoes prontas do repositorio claude-animation-skills (Artem Novitckii, MIT; licenca em skills/_licencas) que o Braniac gera
SOZINHO a partir de um JSON, sem IA e sem gastar token: graph (linha + numero que conta), minimalistic-graphics, map-route (rota 3D), breakdown (vista explodida).
As outras duas (zach-d-films, stick-figure) exigem escrever cenas em codigo: peca ao Claude (skill de mesmo nome em .claude/skills).
Ficam em braniac/skills/<nome>/build.py + braniac/kit (three.js, GSAP, Playwright; instalados com npm --ignore-scripts). Saida em E:\\braniac-link\\animacoes quando houver E:."""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
SKILLS = RAIZ / "skills"
SAIDA = Path(r"E:\braniac-link\animacoes") if os.path.exists("E:\\") else RAIZ / "data" / "animacoes"
ATIVAS = {"graph": "graph", "minimalistic-graphics": "minimalistic-graphics", "map-route": "map-route", "breakdown": "breakdown"}
SEGREDO = re.compile(r"senha|token|cpf|cart[aã]o|pix|chave de acesso|c[oó]digo de verifica", re.I)
MAX_DIA = 8
ARQ_USO = RAIZ / "data" / "animacoes_uso.json"


def _usos_hoje():
    try:
        d = json.loads(ARQ_USO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    return d if d.get("dia") == time.strftime("%Y-%m-%d") else {"dia": time.strftime("%Y-%m-%d"), "n": 0}


def disponiveis():
    return sorted(ATIVAS)


def gerar(skill, spec, timeout=900):
    """Gera o mp4 da animacao `skill` com o JSON `spec` (dict). Devolve o Path do mp4 ou levanta ValueError/RuntimeError."""
    if skill not in ATIVAS:
        raise ValueError(f"animacao desconhecida: {skill}. Disponiveis aqui: {', '.join(disponiveis())} (zach-d-films e stick-figure: peca ao Claude)")
    if not isinstance(spec, dict):
        raise ValueError("spec precisa ser um objeto JSON")
    if SEGREDO.search(json.dumps(spec, ensure_ascii=False)):
        raise ValueError("spec com palavra de segredo/dado pessoal: recusado")
    pasta_skill = SKILLS / ATIVAS[skill]
    if not (pasta_skill / "build.py").exists() or not (RAIZ / "kit" / "node_modules").exists():
        raise RuntimeError("animacoes nao instaladas (falta skills/<nome>/build.py ou kit/node_modules)")
    uso = _usos_hoje()
    if uso["n"] >= MAX_DIA:
        raise ValueError(f"teto de {MAX_DIA} animacoes por dia")
    uso["n"] += 1
    ARQ_USO.parent.mkdir(parents=True, exist_ok=True)
    ARQ_USO.write_text(json.dumps(uso), encoding="utf-8")
    pasta = SAIDA / f"{time.strftime('%Y%m%d-%H%M%S')}-{skill}"
    pasta.mkdir(parents=True, exist_ok=True)
    arq = pasta / f"pedido.{skill.split('-')[0] if skill != 'minimalistic-graphics' else 'minimal'}.json"
    arq.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    r = subprocess.run([sys.executable.replace("pythonw.exe", "python.exe"), str(pasta_skill / "build.py"), str(arq)], cwd=str(pasta), capture_output=True, text=True,
                       timeout=timeout, creationflags=0x08000000 if os.name == "nt" else 0, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    mp4s = sorted(pasta.glob("*.mp4"), key=lambda p: p.stat().st_mtime)
    if r.returncode or not mp4s:
        raise RuntimeError("a animacao nao saiu: " + (r.stderr or r.stdout)[-300:])
    return mp4s[-1]
