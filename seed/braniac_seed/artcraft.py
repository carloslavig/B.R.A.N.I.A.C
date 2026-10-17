# -*- coding: utf-8 -*-
"""Criacao de imagens, vetores e PDFs pelo ArtCraft (VectorCraft, PhotoCraft, PdfCraft: Apache-2.0, storytold/artcraft), via CLI sem janela.
Regra de seguranca: o resultado SEMPRE vai para a pasta de criacoes (Documentos/BRANIAC-Criacoes) com nome simples; o original nunca e sobrescrito."""
import json, os, re, subprocess, sys
from pathlib import Path

PASTA = "BRANIAC-Criacoes"
EXT_SAIDA = {".png", ".jpg", ".jpeg", ".webp", ".pdf", ".svg", ".tif", ".tiff"}


class ArtCraftErro(RuntimeError):
    pass


def pasta_saida():
    p = Path.home() / "Documents" / PASTA
    p.mkdir(parents=True, exist_ok=True)
    return p


def _exe(app):
    """Acha <app>-cli.exe: variavel BRANIAC_ARTCRAFT, pasta 'artcraft' ao lado do programa instalado, ou a instalacao portatil do desenvolvedor."""
    nome = f"{app}-cli.exe"
    bases = [os.environ.get("BRANIAC_ARTCRAFT"), Path(sys.executable).parent / "artcraft", Path(sys.executable).parent / "resources" / "artcraft",
             Path.home() / "Apps" / "ArtCraft"]
    for b in filter(None, bases):
        for c in (Path(b) / app / nome, *Path(b).glob(f"{app}/*/{nome}")):
            if c.is_file():
                return str(c)
    raise ArtCraftErro(f"O módulo {app} do ArtCraft não está instalado neste computador.")


def _rodar(app, args, timeout=180):
    r = subprocess.run([_exe(app), *map(str, args)], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=timeout, creationflags=0x08000000, cwd=str(pasta_saida()))
    if r.returncode:
        raise ArtCraftErro((r.stderr or r.stdout or "falhou").strip()[-300:])
    return r.stdout


def _entrada(caminho):
    from . import pc_tools
    c = pc_tools._caminho(caminho)
    if not c.is_file():
        raise ArtCraftErro("Isso não é um arquivo.")
    return str(c)


def _saida(nome, padrao_ext):
    n = re.sub(r"[^\w\-. ]", "_", Path(str(nome).strip().strip('"')).name) or "resultado"
    if Path(n).suffix.lower() not in EXT_SAIDA:
        n = Path(n).stem + padrao_ext
    return pasta_saida() / n


def _resultado(texto, caminho):
    """Texto para a pessoa (+ a imagem, se for PNG pequeno, para aparecer na tela)."""
    msg = f"{texto}\nArquivo: {caminho}"
    p = Path(caminho)
    if p.suffix.lower() == ".png" and p.stat().st_size < 2_000_000:
        return msg, p.read_bytes()
    return msg, None


# ---------- vetor ----------
def vetor_cartaz(texto, arquivo="cartaz.png", fundo="#1f1f3d", cor_texto="#ffffff", destaque="#f5a623"):
    out = _saida(arquivo, ".png")
    passos = [("shape.rectangle", {"x": 0, "y": 0, "width": 612, "height": 792}), ("paint.setFill", {"color": fundo}),
              ("shape.ellipse", {"x": 156, "y": 130, "width": 300, "height": 300}), ("paint.setFill", {"color": destaque}),
              ("text.create", {"x": 46, "y": 480, "text": texto, "size": 48, "color": cor_texto, "justify": "center",
                               "area": {"width": 520, "height": 220, "fit": "shrinkText"}})]
    args = ["run"]
    for cmd, par in passos:
        args += ["--cmd", cmd, "--params", json.dumps(par)]
    _rodar("vectorcraft", args + ["--export", out, "--scale", 2])
    return _resultado("Cartaz criado.", out)


def vetor_converter(entrada, saida):
    out = _saida(saida, ".png")
    _rodar("vectorcraft", ["convert", _entrada(entrada), out])
    return _resultado("Convertido.", out)


# ---------- foto ----------
def _foto(entrada, saida, passos, qualidade=None, msg="Pronto."):
    out = _saida(saida, ".png")
    args = ["run", _entrada(entrada)]
    for cmd, par in passos:
        args += ["--cmd", cmd] + (["--params", json.dumps(par)] if par else [])
    args += ["--out", out] + (["--quality", int(qualidade)] if qualidade else [])
    _rodar("photocraft", args)
    return _resultado(msg, out)


def foto_converter(entrada, saida, qualidade=None):
    out = _saida(saida, ".png")
    _rodar("photocraft", ["convert", _entrada(entrada), out] + (["--quality", int(qualidade)] if qualidade else []))
    return _resultado("Convertida.", out)


def foto_redimensionar(entrada, saida, largura):
    return _foto(entrada, saida, [("image.imageSize", {"width": int(float(largura))})], msg=f"Redimensionada para {int(float(largura))} px de largura.")


def foto_girar(entrada, saida, graus="90"):
    cmd = {"90": "edit.transform.rotate90Cw", "180": "edit.transform.rotate180", "270": "edit.transform.rotate90Ccw", "-90": "edit.transform.rotate90Ccw"}.get(str(graus).strip())
    if not cmd:
        raise ArtCraftErro("Só giro em 90, 180 ou 270 graus.")
    return _foto(entrada, saida, [(cmd, None)], msg=f"Girada {graus}°.")


def foto_preto_e_branco(entrada, saida):
    return _foto(entrada, saida, [("image.mode.grayscale", None)], msg="Convertida para preto e branco.")


# ---------- pdf ----------
def pdf_texto(arquivo, pagina=None):
    t = _rodar("pdfcraft", ["text", _entrada(arquivo)] + (["--page", int(pagina)] if pagina else [])).strip()
    return (t[:3500] + ("…" if len(t) > 3500 else "")) or "Esse PDF não tem texto selecionável (pode ser escaneado)."


def _lista(v):
    return [x.strip() for x in (v if isinstance(v, list) else re.split(r"[;,\n]", str(v))) if str(x).strip()]


def pdf_juntar(arquivos, saida="juntado.pdf"):
    out = _saida(saida, ".pdf")
    ent = [_entrada(a) for a in _lista(arquivos)]
    if len(ent) < 2:
        raise ArtCraftErro("Preciso de pelo menos 2 PDFs (separe os caminhos por ponto e vírgula).")
    _rodar("pdfcraft", ["combine", *ent, "--out", out])
    return _resultado(f"{len(ent)} PDFs juntados.", out)


def pdf_extrair_paginas(arquivo, paginas, saida="extraido.pdf"):
    out = _saida(saida, ".pdf")
    if not re.fullmatch(r"[\d, ]+", str(paginas)):
        raise ArtCraftErro("Informe as páginas assim: 1,3,5.")
    _rodar("pdfcraft", ["extract", _entrada(arquivo), "--pages", str(paginas).replace(" ", ""), "--out", out])
    return _resultado("Páginas extraídas.", out)


def pdf_dividir(arquivo, a_cada):
    pasta = pasta_saida() / (Path(arquivo).stem[:40] + "-partes")
    pasta.mkdir(exist_ok=True)
    _rodar("pdfcraft", ["split", _entrada(arquivo), "--every", int(a_cada), "--out-dir", pasta])
    return f"PDF dividido de {int(a_cada)} em {int(a_cada)} páginas.\nPasta: {pasta}", None


def pdf_para_imagem(arquivo, pagina="1", saida="pagina.png"):
    out = _saida(saida, ".png")
    _rodar("pdfcraft", ["render", _entrada(arquivo), "--page", int(pagina), "--dpi", 110, "--out", out])
    return _resultado(f"Página {int(pagina)} convertida em imagem.", out)
