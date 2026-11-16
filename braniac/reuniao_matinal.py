# -*- coding: utf-8 -*-
"""REUNIAO DA MANHA (28/10/2026, pedido do Dono): antes do bom dia das 6h os agentes passam ao Jarvis o que tem a reportar; quem nao tem nada, fica calado.
Cada relato e local (nenhuma IA online), curto e falavel. O Jarvis junta tudo no relatorio falado. Os agentes so RELATAM: nenhum age (Correio nao responde e-mail,
Valerio nao compra nem vende)."""
import json
import re
import time
from datetime import date, datetime

from .store import DATA


def _json(nome):
    try:
        return json.loads((DATA / nome).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _brl(v):
    return "{:,.2f}".format(v).replace(",", "X").replace(".", ",").replace("X", ".")


def relato_cofre(agora=None):
    av = _json("financeiro.json").get("avaliacao") or {}
    if not av:
        return ""
    prazo = date.fromisoformat(av["prazo"]).strftime("%d/%m")
    lido = (_json("financeiro.json").get("saldo_ts") or "")[11:16]
    if av["nivel"] == "batida":
        return f"A meta está batida: o saldo é {_brl(av['saldo'])}, e a meta de {_brl(av['meta'])} vale até {prazo}."
    return (f"O saldo{' (lido às ' + lido + ')' if lido else ''} é {_brl(av['saldo'])} e faltam {_brl(av['falta'])} para bater a meta de {_brl(av['meta'])} até {prazo}, o quinto dia útil, "
            f"com {av['dias_uteis']} dia(s) útil(eis). Para manter o ritmo, hoje precisam entrar uns {_brl(av['precisa_por_dia_util'])}.")


def relato_correio(agora=None):
    """E-mails de pessoa e de oferta guardados desde a ultima reuniao (correio.verificar acumula em 'relato'). Limpa ao entregar."""
    from . import correio
    est = correio._estado()
    itens = est.get("relato") or []
    if not itens:
        return ""
    est["relato"] = []
    correio.ESTADO.write_text(json.dumps(est, ensure_ascii=False), encoding="utf-8")
    pessoas = [i for i in itens if i["tipo"] == "pessoa"]
    vagas = [i for i in itens if i["tipo"] == "trabalho"]
    f = []
    if vagas:
        f.append("Chegou possível oferta de trabalho: " + "; ".join(f"{v['quem']}, {v['assunto']}" for v in vagas[:3]) + ".")
    if pessoas:
        f.append("E-mail de pessoa: " + "; ".join(f"{p['quem']}, {p['assunto']}" for p in pessoas[:3]) + ".")
    return " ".join(f) + " Quer que eu te ajude a redigir uma resposta? Eu não envio nada sozinho."


def relato_ilheu(agora=None):
    est = _json("airbnb_estado.json")
    pend = [c for c in (est.get("consultas") or {}).values() if c.get("estado") == "consulta"]
    if not pend:
        return ""
    return f"No Airbnb, {len(pend)} reserva(s) ou hóspede(s) esperando o OK de vocês: " + ", ".join(c.get("hospede", "?") for c in pend[:4]) + "."


def relato_compasso(agora=None):
    from . import agenda
    return agenda.resumo_falado(agora) or ""


def relato_tino(agora=None):
    from . import qualidade
    trocas, n, _ = qualidade.medir(1)
    return f"Nas últimas vinte e quatro horas você corrigiu o Jarvis {n} vez(es) em {trocas} conversas." if n else ""


def relato_claudinho(agora=None):
    from . import claudinho
    return claudinho.relato(agora)


def relato_nando(agora=None):
    from . import candidaturas
    return candidaturas.relato()


ORDEM = (("Cofre", relato_cofre), ("Correio", relato_correio), ("Nando", relato_nando), ("Ilhéu", relato_ilheu), ("Compasso", relato_compasso), ("Tino", relato_tino), ("Claudinho", relato_claudinho))


def reunir(agora=None):
    """[(agente, texto)] so de quem tem algo a dizer. Registra no barramento (pedido do Jarvis e resposta de cada um)."""
    try:
        from . import barramento
    except Exception:
        barramento = None
    saida = []
    for nome, fn in ORDEM:
        try:
            texto = (fn(agora) or "").strip()
        except Exception:
            texto = ""
        if barramento:
            try:
                barramento.enviar("Jarvis", nome, "pedido", "reunião da manhã: o que você tem a reportar?")
                barramento.enviar(nome, "Jarvis", "resposta", "tenho algo a reportar" if texto else "nada a reportar")
            except Exception:
                pass
        if texto:
            saida.append((nome, texto))
    return saida


def para_fala(agora=None):
    """Bloco falado da reuniao, ou '' se ninguem tem nada."""
    r = reunir(agora)
    if not r:
        return ""
    return "Passei pelos agentes antes de falar com você. " + " ".join(f"{n} reporta: {t}" for n, t in r)
