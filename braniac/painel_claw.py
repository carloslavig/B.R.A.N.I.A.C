# -*- coding: utf-8 -*-
"""PAINEL (27/10/2026): dados agregados para a interface nova `/painel` (layout inspirado no Control UI do OpenClaw, MIT). So LEITURA e so dados locais ja existentes:
agenda de hoje, rotinas (Compasso), agentes/assuntos com contagem de fatos, manutencao, propostas pendentes, resumo da vaquinha e da meta. Nada de IA, nada de segredo.
O que e pessoal (agenda, financeiro) so aparece na interface local do PC (127.0.0.1) ou no tunel P2P pareado do proprio Dono."""
import time


def _seguro(f, padrao=None):
    try:
        return f()
    except Exception:
        return padrao


def assuntos_com_fatos():
    from . import assuntos
    out = []
    for a in assuntos.listar():
        def n(a=a):
            c = assuntos._topico_db(a["id"])
            v = c.execute("SELECT COUNT(*) FROM fatos WHERE ativo=1 AND (validade IS NULL OR validade>?)", (time.time(),)).fetchone()[0]
            c.close()
            return v
        out.append({"id": a["id"], "nome": a["nome"], "agente": a["agente"], "descricao": a["descricao"], "fatos": _seguro(n, 0)})
    return out


def rotinas():
    from . import compasso
    return [{"id": r["id"], "titulo": r["titulo"], "horario": r.get("horario", ""), "dias": r.get("dias") or [], "ativa": bool(r.get("ativa")), "para": r.get("para", ""),
             "ate": r.get("ate", ""), "ultima": r.get("ultima", "")} for r in compasso.listar()]


APPS = {"photocraft": "Editor de imagens (camadas, PSD)", "vectorcraft": "Vetores, logos e cartazes", "wordcraft": "Documentos Word", "soundcraft": "Áudio (estilo Pro Tools)",
        "effectcraft": "Motion graphics", "pdfcraft": "PDF: editar, assinar, OCR", "lightcraft": "Revelar e organizar fotos (RAW)", "gridcraft": "Planilhas",
        "deckcraft": "Slides", "filmcraft": "Edição de vídeo", "designcraft": "Diagramação de páginas", "cadcraft": "Desenho técnico (CAD)"}


def plugins():
    """Apps conectados por MCP (ArtCraft, em .mcp.json) + habilidades do Jarvis. So nomes e descricao: nunca comando com caminho/segredo."""
    import json
    from pathlib import Path
    out = []
    try:
        mcp = json.loads((Path(__file__).resolve().parent.parent / ".mcp.json").read_text(encoding="utf-8")).get("mcpServers", {})
        out = [{"nome": n, "tipo": "App ArtCraft (MCP)", "descricao": APPS.get(n, "Servidor MCP")} for n in mcp]
    except (OSError, ValueError):
        pass
    return out


def dados():
    from . import agenda, financeiro, manutencao, sauraki, vaquinha
    fin = _seguro(financeiro._estado, {}) or {}
    av = fin.get("avaliacao") or {}
    vq = _seguro(vaquinha._estado, {}) or {}
    return {
        "ts": time.time(),
        "plugins": _seguro(plugins, []),
        "agenda_hoje": _seguro(lambda: agenda.listar("", 1), ""),
        "rotinas": _seguro(rotinas, []),
        "assuntos": _seguro(assuntos_com_fatos, []),
        "manutencao": _seguro(manutencao.ultimo, {}),
        "propostas_pendentes": _seguro(sauraki._propostas_pendentes, 0),
        "financeiro": {"saldo": fin.get("saldo"), "nivel": av.get("nivel"), "falta": av.get("falta"), "meta": av.get("meta"), "prazo": av.get("prazo"), "lido_em": fin.get("saldo_ts")} if fin else None,
        "vaquinha": {"ativa": bool(vq.get("ativo")), "recebido": vq.get("arrecadado"), "gasto": vq.get("gasto"), "meta": vq.get("meta"), "informado_em": vq.get("informado_em")} if vq else None,
    }
