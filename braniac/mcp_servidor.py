# -*- coding: utf-8 -*-
"""PILOTO OpenClaw (27/10/2026): servidor MCP LOCAL (stdio) pelo qual o OpenClaw consulta os agentes do Braniac.
O Braniac continua dono dos dados e das regras: so os agentes NAO locais (sem dado pessoal/financeiro/saude/familia: Sultao, Forja, Ada) respondem por aqui.
Qualquer outro agente e recusado com orientacao de falar com o Jarvis. Nada de acao: so leitura. Cada chamada vai para o barramento (o escritorio mostra o Jarvis
indo ate o agente) e para data/mcp_piloto.log (so hora, ferramenta e agente; nunca o conteudo).
Uso: python -m braniac.mcp_servidor   (o OpenClaw sobe este comando como servidor MCP)."""
import time

from . import delegacao
from .store import DATA

LOG = DATA / "mcp_piloto.log"
LIMITE = 1800


def _log(msg):
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S") + " " + msg + "\n")
    except OSError:
        pass


def agentes_publicos():
    return sorted(n for n, (_, local, _) in delegacao.AGENTES.items() if not local)


def listar_agentes_publicos():
    """Agentes que podem ser consultados por este canal (sem dado pessoal), com a especialidade de cada um."""
    from . import assuntos
    esp = {a["agente"]: a["descricao"] for a in assuntos.listar()}
    _log("listar_agentes_publicos")
    return "\n".join(f"- {n}: {esp.get(n, '')}" for n in agentes_publicos())


def consultar_agente(agente, pergunta):
    """Pergunta a um agente do Braniac e devolve o que ele tem. So agentes sem dado pessoal; os outros sao recusados."""
    agente = (agente or "").strip()
    pergunta = (pergunta or "").strip()[:300]
    if agente not in delegacao.AGENTES:
        _log(f"consultar_agente desconhecido:{agente[:20]}")
        return f"Agente desconhecido: {agente[:30]}. Use listar_agentes_publicos."
    if agente not in agentes_publicos():
        _log(f"consultar_agente RECUSADO:{agente}")
        return f"O agente {agente} lida com dados pessoais e não responde por este canal. Peça direto ao Jarvis."
    if not pergunta:
        return "Faltou a pergunta."
    r = delegacao.consultar(agente, pergunta)            # registra pedido/resposta no barramento (aparece no escritorio)
    _log(f"consultar_agente {agente}")
    return r["texto"][:LIMITE]


def criar():
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP("braniac")
    mcp.tool()(listar_agentes_publicos)
    mcp.tool()(consultar_agente)
    return mcp


if __name__ == "__main__":
    criar().run()
