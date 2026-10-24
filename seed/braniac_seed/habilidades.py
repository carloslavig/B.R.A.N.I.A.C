# -*- coding: utf-8 -*-
"""Habilidades (v0.7, formato aberto Agent Skills: uma pasta com SKILL.md). Vem um pacote junto com o programa e a pessoa pode criar as suas
(pasta 'habilidades' nos dados dela). O assistente ve a lista (nome + quando usar) e, quando o pedido combina, carrega o passo a passo."""
import re
import time
from pathlib import Path
from . import paths

EMBUTIDAS = Path(__file__).parent / "habilidades"


def _usuario():
    p = paths.arquivo("habilidades")
    p.mkdir(exist_ok=True)
    return p


def _frontmatter(txt):
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", txt, re.S)
    if not m:
        return {}, txt
    campos = {}
    for linha in m.group(1).splitlines():
        if ":" in linha and not linha.startswith(" "):
            k, v = linha.split(":", 1)
            campos[k.strip()] = v.strip().strip('"')
    return campos, m.group(2)


def listar():
    """[(nome, descricao, origem)] - as da pessoa podem substituir as embutidas de mesmo nome."""
    achadas = {}
    for origem, base in (("embutida", EMBUTIDAS), ("sua", _usuario())):
        for arq in sorted(base.glob("*/SKILL.md")):
            campos, _ = _frontmatter(arq.read_text(encoding="utf-8", errors="ignore"))
            if campos.get("name") == arq.parent.name and campos.get("description"):
                achadas[arq.parent.name] = (arq.parent.name, campos["description"], origem)
    return list(achadas.values())


def catalogo(maximo=180):
    return "; ".join(f"{n}: {d[:maximo]}" for n, d, _ in listar())


def carregar(nome):
    nome = re.sub(r"[^a-z0-9-]", "", str(nome or "").lower())
    for base in (_usuario(), EMBUTIDAS):
        arq = base / nome / "SKILL.md"
        if arq.exists():
            return _frontmatter(arq.read_text(encoding="utf-8", errors="ignore"))[1].strip()
    return None


def criar(nome, descricao, passos):
    slug = re.sub(r"[^a-z0-9]+", "-", str(nome or "").lower()).strip("-")[:40]
    if not slug or not str(descricao or "").strip() or not str(passos or "").strip():
        raise ValueError("a habilidade precisa de nome, de quando usar e do passo a passo")
    pasta = _usuario() / slug
    if pasta.exists() or (EMBUTIDAS / slug).exists():
        raise ValueError(f"já existe uma habilidade chamada {slug}")
    pasta.mkdir(parents=True)
    (pasta / "SKILL.md").write_text(f"---\nname: {slug}\ndescription: {' '.join(str(descricao).split())[:300]}\n"
                                    f"metadata:\n  origem: criada em {time.strftime('%d/%m/%Y')}\n---\n\n# {str(nome).strip()}\n\n{str(passos).strip()}\n",
                                    encoding="utf-8")
    return slug
