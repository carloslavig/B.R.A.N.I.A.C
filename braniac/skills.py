# -*- coding: utf-8 -*-
"""AGENT SKILLS no Braniac (formato aberto agentskills.io, pedido do Dono em 14/10/2026).
Cada skill e uma pasta em braniac/skills/<nome>/ com um SKILL.md (frontmatter com name e description + instrucoes) e, opcional,
references/ com textos de apoio. Divulgacao progressiva, como no padrao:
  1. descoberta: so 'nome: descricao' de cada skill vai na descricao da ferramenta usar_skill (barato);
  2. ativacao: a IA chama usar_skill(nome) e recebe as instrucoes completas;
  3. execucao: segue as instrucoes com as ferramentas normais; usar_skill(nome, arquivo) le um references/.
Diferente do dossie (FATOS por palavra-chave), skill e PROCEDIMENTO (como fazer uma tarefa). Scripts de skill NAO sao executados aqui."""
import re
from pathlib import Path

DIR = Path(__file__).resolve().parent / "skills"
_NOME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _frontmatter(texto):
    """(campos, corpo). YAML simples: chave: valor numa linha (aspas opcionais)."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", texto, re.S)
    if not m:
        return {}, texto
    campos = {}
    for linha in m.group(1).splitlines():
        k, sep, v = linha.partition(":")
        if sep and not linha.startswith((" ", "\t")):
            campos[k.strip()] = v.strip().strip('"').strip("'")
    return campos, m.group(2)


def listar(base=None):
    """[(nome, descricao, pasta)] das skills validas (nome no padrao e igual ao da pasta, descricao presente)."""
    base = Path(base or DIR)
    out = []
    for arq in sorted(base.glob("*/SKILL.md")):
        try:
            campos, _ = _frontmatter(arq.read_text(encoding="utf-8"))
        except OSError:
            continue
        nome, desc = campos.get("name", ""), campos.get("description", "")
        if _NOME.match(nome) and nome == arq.parent.name and desc:
            out.append((nome, desc[:1024], arq.parent))
    return out


def catalogo(base=None, maximo=160):
    """Linhas 'nome: descricao' para a descricao da ferramenta (fase de descoberta)."""
    return "; ".join(f"{n}: {d[:maximo]}" for n, d, _ in listar(base))


def ferramentas_da_skill(nome, base=None):
    """Campo 'allowed-tools' do padrao (nomes separados por espaco): ferramentas que a skill precisa e que entram no agente quando ela e ativada."""
    for n, _, pasta in listar(base):
        if n == nome:
            campos, _ = _frontmatter((pasta / "SKILL.md").read_text(encoding="utf-8"))
            return set(campos.get("allowed-tools", "").split())
    return set()


def usar(nome, arquivo="", base=None):
    """Fase de ativacao: instrucoes completas da skill (ou um arquivo de references/)."""
    skills = {n: p for n, _, p in listar(base)}
    if nome not in skills:
        return f"Skill '{nome}' não existe. Disponíveis: {', '.join(skills) or 'nenhuma'}."
    pasta = skills[nome]
    if arquivo:
        alvo = (pasta / arquivo).resolve()
        if pasta.resolve() not in alvo.parents or not alvo.is_file():   # so arquivos de dentro da propria skill
            return f"Arquivo '{arquivo}' não existe na skill {nome}."
        return alvo.read_text(encoding="utf-8")[:8000]
    _, corpo = _frontmatter((pasta / "SKILL.md").read_text(encoding="utf-8"))
    extras = sorted(str(p.relative_to(pasta)).replace("\\", "/") for p in pasta.rglob("*") if p.is_file() and p.name != "SKILL.md")
    return corpo.strip()[:8000] + (f"\n\n(Arquivos de apoio: {', '.join(extras)} — leia com usar_skill(nome, arquivo).)" if extras else "")
