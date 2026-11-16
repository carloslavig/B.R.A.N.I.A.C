# -*- coding: utf-8 -*-
"""Porteiro do Claude (decisao do Dono, 08/11/2026): NENHUMA resposta do Jarvis ao Dono no WhatsApp sai sem o Claude aprovar.

O Jarvis passa o contexto (conversa recente + a pergunta) e a resposta que pretende dar; o Claude diz se a resposta e plausivel
para a pergunta. Aprovou -> sai. Reprovou -> nao sai: sai a versao corrigida do Claude (se ele deu uma) ou um aviso curto.
Claude indisponivel -> `ok=None` (quem chama segura e tenta de novo; nunca manda sem revisao).
"""
import json, re, tempfile
from datetime import datetime
from pathlib import Path
from . import agente_dev, memoria
from .store import DATA

LOG = DATA / "revisor_claude.log"
TIMEOUT_S = 120
PROMPT = """Voce e o REVISOR das respostas do Jarvis (assistente do Dono, no WhatsApp). Nada sai sem a sua aprovacao: se uma resposta ruim sair, a culpa e sua.

Hoje: {hoje}. A mensagem do Dono chegou por {como}.

CONVERSA RECENTE (mais antiga primeiro):
{historico}

PERGUNTA/PEDIDO DO DONO AGORA:
{pergunta}

RESPOSTA QUE O JARVIS QUER ENVIAR:
{resposta}

Decida se essa resposta presta. REPROVE se: nao responde o que foi perguntado; fala de outro assunto ou outro agente (ex.: familia quando a pergunta era do Exercito);
e muito mais longa do que a pergunta pede (pergunta pontual = resposta curta e direta, sem despejar fichas, listas ou avisos); parece inventar dado;
repete a conversa anterior sem necessidade; tem tom robotico, rotulos ("Falei com...", "Fato:") ou revela bastidores (agentes, IAs, banco).
Se o pedido veio truncado/ininteligivel (transcricao de audio ruim), a resposta certa e pedir para repetir, em UMA frase.
APROVE se responde direto e com bom senso.

Responda SOMENTE com uma linha JSON, sem mais nada:
{{"aprovado": true|false, "motivo": "uma frase curta", "corrigida": "resposta melhor, curta, em portugues do Brasil, so com fatos que apareceram acima (ou vazio se aprovado ou se nao da para corrigir)"}}"""


def _log(txt):
    DATA.mkdir(exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {txt}\n")


def _historico(contato, n=8):
    try:
        linhas = [f"{'Dono' if m['direcao'] == 'E' else 'Jarvis'}: {str(m['texto'])[:300]}" for m in memoria.historico(contato, n)]
    except Exception:
        linhas = []
    return "\n".join(linhas) or "(sem histórico)"


def _json(txt):
    m = re.search(r"\{.*\}", txt or "", re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except ValueError:
        return None
    return d if isinstance(d, dict) and isinstance(d.get("aprovado"), bool) else None


def revisar(pergunta, resposta, contato="Dono(dono)", por_audio=False, perguntar=None):
    """{'ok': True|False|None, 'motivo': str, 'corrigida': str}. ok=None: sem revisor (Claude fora do ar / resposta ilegivel)."""
    prompt = PROMPT.format(hoje=datetime.now().strftime("%d/%m/%Y %H:%M"), como="ÁUDIO (transcrito, pode ter erros)" if por_audio else "texto",
                           historico=_historico(contato), pergunta=(pergunta or "")[:1200], resposta=(resposta or "")[:3000])
    try:
        bruto = (perguntar or (lambda p: agente_dev.perguntar(p, workdir=tempfile.gettempdir(), timeout=TIMEOUT_S)))(prompt)
    except Exception as e:
        _log(f"ERRO {e!r}")
        bruto = None
    d = _json(bruto)
    if d is None:
        _log(f"SEM REVISAO | pergunta={pergunta[:60]!r} | bruto={str(bruto)[:120]!r}")
        return {"ok": None, "motivo": "revisor indisponível", "corrigida": ""}
    r = {"ok": d["aprovado"], "motivo": str(d.get("motivo", ""))[:200], "corrigida": str(d.get("corrigida") or "").strip()}
    _log(f"{'APROVOU' if r['ok'] else 'REPROVOU'} | pergunta={pergunta[:60]!r} | resposta={resposta[:80]!r} | motivo={r['motivo']!r} | corrigida={r['corrigida'][:80]!r}")
    return r
