# -*- coding: utf-8 -*-
"""Jarvis mexe no PC do Dono (24/10/2026, pedido dele para o B.R.A.N.I.A.C 2): abrir paginas, pastas e documentos, procurar e listar arquivos.
Limites de proposito: NUNCA executa programa/script (.exe, .bat, .ps1...), nunca apaga, move ou altera arquivo. Abrir usa o programa padrao do Windows."""
import os
import time
import webbrowser
from pathlib import Path

PERIGOSOS = {".exe", ".msi", ".bat", ".cmd", ".ps1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".scr", ".com", ".pif", ".lnk", ".jar",
             ".reg", ".hta", ".cpl", ".dll", ".sys", ".py", ".pyw", ".sh", ".appx", ".msix", ".url"}
CASA = Path.home()
RAIZES = [CASA / n for n in ("Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos", "OneDrive", "Projetos", "ArtCraft-Trabalho")]
PULAR = {"AppData", "node_modules", ".git", "__pycache__", "target", ".venv", "venv", "$Recycle.Bin", "Windows", "Program Files", "Program Files (x86)"}


def abrir(alvo):
    alvo = str(alvo or "").strip().strip('"')
    if alvo.lower().startswith(("http://", "https://")):
        webbrowser.open(alvo)
        return f"Abri a pagina {alvo} no navegador."
    p = Path(os.path.expandvars(os.path.expanduser(alvo)))
    if not p.exists():
        return f"Nao achei '{alvo}'. Use a acao procurar para achar o caminho certo."
    if p.is_file() and p.suffix.lower() in PERIGOSOS:
        return f"Nao abro {p.suffix} (programa/script pode ser perigoso). O Dono pode abrir ele mesmo: {p}"
    os.startfile(str(p))   # pasta abre no Explorer; documento no programa padrao
    return f"Abri {'a pasta' if p.is_dir() else 'o arquivo'} {p}."


def listar(pasta, n=60):
    p = Path(os.path.expandvars(os.path.expanduser(str(pasta or CASA))))
    if not p.is_dir():
        return f"'{pasta}' nao e uma pasta."
    itens = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))[:n]
    linhas = [f"[pasta] {x.name}" if x.is_dir() else f"{x.name} ({x.stat().st_size // 1024} KB)" for x in itens if not x.name.startswith("desktop.ini")]
    return f"{p}:\n" + "\n".join(linhas) if linhas else f"{p} esta vazia."


def procurar(termo, n=20, limite_s=15):
    """Arquivos/pastas cujo NOME contem o termo, nas pastas do usuario (Desktop, Documentos, Downloads, Imagens, Projetos...)."""
    termo = str(termo or "").lower().strip()
    if len(termo) < 2:
        return "Diga pelo menos 2 letras do nome."
    achados, fim = [], time.time() + limite_s
    for raiz in [r for r in RAIZES if r.exists()]:
        for pasta, dirs, arqs in os.walk(raiz):
            dirs[:] = [d for d in dirs if d not in PULAR and not d.startswith(".")]
            achados += [os.path.join(pasta, x) for x in dirs + arqs if termo in x.lower()]
            if len(achados) >= n or time.time() > fim:
                break
        if len(achados) >= n or time.time() > fim:
            break
    if not achados:
        return f"Nada com '{termo}' no nome nas pastas do usuario."
    return "\n".join(achados[:n]) + ("" if time.time() < fim else "\n(busca parou no tempo limite; seja mais especifico)")


def executar(acao, alvo):
    if acao == "abrir":
        return abrir(alvo)
    if acao == "listar":
        return listar(alvo)
    if acao == "procurar":
        return procurar(alvo)
    return "acao desconhecida: use abrir, listar ou procurar"
