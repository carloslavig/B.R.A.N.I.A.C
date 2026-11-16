# -*- coding: utf-8 -*-
"""Painel de pendências e erros: o que espera o OK do Dono e o que está quebrado, num lugar só. Só LÊ dados que já existem (sem IA)."""
import json
import time

from . import sauraki

DATA = sauraki.DATA


def _prop():
    out = []
    for f in sorted((DATA / "propostas").glob("*.md"), reverse=True):
        try:
            txt = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "AGUARDANDO APROVA" in txt[:600].upper():
            tema = next((l[5:].strip() for l in txt.splitlines() if l.startswith("Tema:")), f.stem)
            out.append({"agente": "Alma/Forja", "tipo": "ok", "titulo": "Proposta de melhoria: " + tema[:90], "detalhe": f.name, "ts": f.stat().st_mtime})
    return out


def _reservas():
    cons = (sauraki._json("airbnb_estado.json").get("consultas") or {}).values()
    return [{"agente": "Ilhéu", "tipo": "ok", "titulo": "Aguardando OK: " + str(c.get("hospede") or c.get("nome") or "reserva/hóspede")[:60],
             "detalhe": str(c.get("pergunta") or c.get("resumo") or "")[:160], "ts": c.get("ts") or 0} for c in cons if c.get("estado") == "consulta"]


def _erros():
    out, m = [], sauraki._json("manutencao.json")
    if m.get("testes_ok") is False:
        for f in (m.get("falhas") or ["teste falhando"])[:5]:
            out.append({"agente": "Forja", "tipo": "erro", "titulo": "Teste falhando na madrugada", "detalhe": f, "ts": 0})
    if sauraki._json("vaquinha.json").get("ultimo_erro"):
        out.append({"agente": "Vaquinha", "tipo": "erro", "titulo": "Último deploy do site falhou", "detalhe": str(sauraki._json("vaquinha.json")["ultimo_erro"])[:160], "ts": 0})
    for mod, arq, bad in (("NexoDev", "empresa_dev/tickets.json", ("bloqueado",)), ("Fornalha", "empresa_mkt/pedidos.json", ("falhou",))):
        try:
            for t in json.loads((DATA / arq).read_text(encoding="utf-8")):
                if t.get("estado") in bad:
                    h = (t.get("historico") or [{}])[-1].get("txt", "")
                    out.append({"agente": mod, "tipo": "erro", "titulo": f"{t.get('id')} {t.get('estado')}: {(t.get('titulo') or t.get('tipo') or '')[:70]}", "detalhe": h[:160], "ts": t.get("criado") or 0})
        except (OSError, ValueError):
            pass
    return out


def _so_dono():
    """Linhas `- [Área] texto` de data/pendencias_dono.md: o que só o Dono pode fazer (login, conta, OK)."""
    try:
        linhas = (DATA / "pendencias_dono.md").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out, tipo = [], "dono"
    for l in linhas:
        l = l.strip()
        if l.startswith("## "):   # seção "## Comigo (Claude)": o que está andando sem depender do Dono
            tipo = "claude" if "claude" in l.lower() else "dono"
        elif l.startswith("- ["):
            area, _, txt = l[3:].partition("]")
            out.append({"agente": area.strip(), "tipo": tipo, "titulo": txt.strip(), "detalhe": "", "ts": 0})
    return out


def painel():
    ok, erros, lista = _prop() + _reservas(), _erros(), _so_dono()
    dono = [x for x in lista if x["tipo"] == "dono"]
    claude = [x for x in lista if x["tipo"] == "claude"]
    return {"ts": time.time(), "aguardando": ok, "erros": erros, "so_dono": dono, "comigo": claude,
            "total": len(ok) + len(erros) + len(dono)}


def fala(maximo=4):
    """Resposta curta (vai em áudio) quando o Dono PERGUNTA das pendências. Regra de 15/11/2026: nenhuma rotina manda isso sozinha."""
    p = painel()
    c, ok = p["so_dono"], p["aguardando"]
    if not c and not ok:
        return "Nenhuma pendência esperando você agora."
    partes = []
    if c:
        itens = [f"{x['agente']}: {x['titulo'].split('(')[0].strip().rstrip('.')}" for x in c[:maximo]]
        partes.append(f"Tem {len(c)} coisas paradas que só você pode resolver. As primeiras são: " + "; ".join(itens) + ".")
    if ok:
        partes.append(f"E {len(ok)} esperando o seu OK.")
    partes.append("O mapa completo está no computador, na tela do mapa do Braniac.")
    return " ".join(partes)
