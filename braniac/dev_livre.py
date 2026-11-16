# -*- coding: utf-8 -*-
"""Jarvis PROGRAMA sozinho com as IAs gratis (sem o Claude): implementador da automelhoria quando o Claude nao esta disponivel (21/10/2026).
Mesma assinatura do implementador do Claude: rodar(prompt, timeout) -> (codigo, texto). Quem confere tudo depois e a automelhoria
(testes, travas, arquivos protegidos, desfazer), entao aqui so se limita ONDE a IA pode mexer: dentro de braniac/, nunca em data/, .env, travas."""
import re
import subprocess
import sys
import time
from pathlib import Path

from . import automelhoria

BRANIAC = automelhoria.BRANIAC
PASSOS = 40
_PROIBIDO_ESCRITA = automelhoria.PROTEGIDOS   # as travas de seguranca do jarvis.py quem confere e a automelhoria (AST), nao esta lista


def _caminho(rel, escrita=False):
    """Path dentro de braniac/ ou ValueError. Leitura: sem data/ e .env. Escrita: sem arquivos protegidos."""
    p = (BRANIAC / str(rel).replace("braniac/", "", 1).lstrip("/\\")).resolve()
    r = p.relative_to(BRANIAC.resolve()).as_posix()      # sai de braniac/ -> ValueError
    if r.split("/")[0] in ("data", ".git") or p.name.startswith(".env"):
        raise ValueError("pasta/arquivo proibido")
    if escrita and (r in _PROIBIDO_ESCRITA or r.endswith(".env")):
        raise ValueError(f"{r} e protegido")
    return p


def executor(nome, a):
    if nome == "ler_arquivo":
        linhas = _caminho(a["caminho"]).read_text(encoding="utf-8").splitlines()
        i, f = int(a.get("inicio") or 1), int(a.get("fim") or 200)
        return "\n".join(f"{n}: {l}" for n, l in enumerate(linhas[i - 1:f], i)) or "(vazio)"
    if nome == "buscar_codigo":
        achou = [f"{p.relative_to(BRANIAC).as_posix()}:{n}: {l.strip()[:140]}" for p in sorted(BRANIAC.rglob("*.py")) if "data" not in p.relative_to(BRANIAC).parts
                 for n, l in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1) if a["texto"].lower() in l.lower()]
        return "\n".join(achou[:40]) or "nada encontrado"
    if nome == "substituir_trecho":
        p = _caminho(a["caminho"], True)
        t = p.read_text(encoding="utf-8")
        if t.count(a["antigo"]) != 1:
            return f"ERRO: o trecho antigo aparece {t.count(a['antigo'])} vez(es); preciso de exatamente 1 (inclua mais linhas ao redor)"
        p.write_text(t.replace(a["antigo"], a["novo"]), encoding="utf-8")
        return "ok"
    if nome == "criar_arquivo":
        p = _caminho(a["caminho"], True)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(a["conteudo"], encoding="utf-8")
        return "ok"
    if nome == "rodar_testes":
        alvo = str(_caminho(a["arquivo"])) if a.get("arquivo") else "braniac/tests"
        r = subprocess.run([sys.executable.replace("pythonw.exe", "python.exe"), "-m", "pytest", alvo, "-q", "-x", "-p", "no:cacheprovider"], cwd=BRANIAC.parent, capture_output=True, text=True, timeout=900, creationflags=0x08000000)
        return (r.stdout + r.stderr)[-1800:]
    return f"ferramenta desconhecida: {nome}"


def ferramentas():
    from .jarvis import _fn
    s = {"type": "string"}
    return [
        _fn("ler_arquivo", "Le um arquivo de braniac/ com numero de linha (padrao linhas 1-200).", {"caminho": s, "inicio": {"type": "integer"}, "fim": {"type": "integer"}}, ["caminho"]),
        _fn("buscar_codigo", "Procura um texto nos .py de braniac/ (arquivo:linha).", {"texto": s}, ["texto"]),
        _fn("substituir_trecho", "Troca um trecho EXATO (aparece 1 vez) por outro num arquivo. Prefira isto a reescrever o arquivo.", {"caminho": s, "antigo": s, "novo": s}, ["caminho", "antigo", "novo"]),
        _fn("criar_arquivo", "Cria um arquivo novo (ex.: um teste em braniac/tests/).", {"caminho": s, "conteudo": s}, ["caminho", "conteudo"]),
        _fn("rodar_testes", "Roda os testes (um arquivo, ex.: tests/test_x.py, ou todos se omitir).", {"arquivo": s}),
    ]


def rodar(prompt, timeout=1500):
    from .router import Router
    prompt += ("\nVoce trabalha com FERRAMENTAS (ler_arquivo, buscar_codigo, substituir_trecho, criar_arquivo, rodar_testes): leia o codigo antes de mudar, "
               "mude pouco, escreva um teste e rode-o. Quando terminar, responda em ate 6 linhas o que mudou.")
    try:
        texto, _ = Router().responder_agente(f"dev-livre-{int(time.time())}", prompt, ferramentas(), executor, max_passos=PASSOS, compacto=True)
        return (0, texto) if texto and "Não consegui" not in texto[:20] else (1, texto or "sem resposta")
    except Exception as e:
        return 1, f"erro: {str(e)[:200]}"
