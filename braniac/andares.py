"""Andares do predio 3D (/sauraki) que estao construidos (16/11/2026).

Sem data/predio.json = predio inteiro (o PC do dono). A copia publica traz padrao/predio.json so com terreo, escritorio e cobertura:
a pessoa comeca com um andar e constroi os outros pelo botao do predio. Construir so mostra o andar; nao liga nem desliga rotina.
"""
import json

from .store import DATA

ARQ = DATA / "predio.json"
# mesma ordem (base -> topo) do ORDEM de ui/sauraki-real.html (teste confere)
TODOS = ["terreo", "servidores", "dormitorio2", "dormitorio1", "braincenter", "compras", "cortes", "esteira", "investimentos",
         "marketing", "nexodev", "escritorio", "cobertura"]
FIXOS = ("terreo", "escritorio", "cobertura")


def _indisponiveis():
    """Andar cujo modulo nao veio nesta instalacao (a esteira de videos de prefeitura nao vai na copia publica)."""
    try:
        from .link import lote_parceiro  # noqa: F401
        return []
    except Exception:
        return ["esteira"]


def estado():
    try:
        andares = json.loads(ARQ.read_text(encoding="utf-8")).get("andares")
    except (OSError, ValueError):
        andares = None
    return {"andares": andares, "todos": TODOS, "indisponiveis": _indisponiveis()}


def construir(andar):
    e = estado()
    if andar not in TODOS or andar in e["indisponiveis"]:
        raise ValueError("andar desconhecido")
    atual = e["andares"] if e["andares"] is not None else list(TODOS)
    novo = [k for k in TODOS if k in atual or k == andar or k in FIXOS]
    ARQ.parent.mkdir(parents=True, exist_ok=True)
    ARQ.write_text(json.dumps({"andares": novo}, ensure_ascii=False, indent=1), encoding="utf-8")
    return estado()
