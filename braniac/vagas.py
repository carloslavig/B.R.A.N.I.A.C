# -*- coding: utf-8 -*-
"""Agente GARIMPEIRO (26/10/2026): uma vez por dia procura vagas REMOTAS (Remotive, API publica, sem login) com o perfil do Dono (TI, suporte, IA/automacao;
mundo todo/Brasil/LatAm) e manda as novas no WhatsApp. Nao se candidata e nao manda dado pessoal: so le a lista publica. O texto das vagas e dado de terceiros."""
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime

from .store import DATA

ESTADO = DATA / "vagas.json"
BUSCAS = ("IT support", "technical support", "AI automation")
LOCAL_OK = re.compile(r"worldwide|anywhere|global|brazil|brasil|latin|latam|americas|south america", re.I)
HORA = 8
MAX_DIA = 5


def _estado():
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _buscar(termo):
    url = "https://remotive.com/api/remote-jobs?limit=25&search=" + urllib.parse.quote(termo)
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Braniac"}), timeout=25) as r:
        return json.load(r).get("jobs", [])


def filtrar(jobs, vistos):
    """Vagas novas com local compativel; as que informam salario vem primeiro. Pura (testavel)."""
    out, ids = [], set()
    for j in jobs:
        if str(j.get("id")) in vistos or j.get("id") in ids or not LOCAL_OK.search(j.get("candidate_required_location") or ""):
            continue
        ids.add(j.get("id"))
        out.append(j)
    return sorted(out, key=lambda j: not j.get("salary"))


def verificar(enviar_dono, agora=None):
    """No maximo uma vez por dia, a partir das 8h. Devolve quantas vagas mandou."""
    agora = agora or datetime.now()
    est = _estado()
    hoje = agora.strftime("%Y-%m-%d")
    if agora.hour < HORA or est.get("dia") == hoje:
        return 0
    est["dia"] = hoje
    vistos = set(est.get("vistos", []))
    jobs = []
    for b in BUSCAS:
        try:
            jobs += _buscar(b)
        except Exception:
            continue
    novas = filtrar(jobs, vistos)[:MAX_DIA]
    vistos |= {str(j["id"]) for j in novas}
    est["vistos"] = list(vistos)[-800:]
    ESTADO.write_text(json.dumps(est, ensure_ascii=False), encoding="utf-8")
    try:
        from . import barramento
        barramento.enviar("Garimpeiro", "Compasso", "status", f"busca do dia: {len(novas)} vaga(s) nova(s) enviada(s)")
    except Exception:
        pass
    try:        # 28/10: as vagas do dia tambem entram na fila do Nando (triagem e relato na reuniao)
        from . import candidaturas
        for j in novas:
            candidaturas.receber("Garimpeiro", j["title"], j["company_name"], j["url"])
    except Exception:
        pass
    if novas:
        linhas = [f"• {j['title'][:70]} — {j['company_name'][:30]} ({j.get('salary') or 'salário não informado'}) {j['url']}" for j in novas]
        enviar_dono("🔎 Vagas remotas novas de hoje (Garimpeiro):\n" + "\n".join(linhas))
    return len(novas)
