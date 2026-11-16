# -*- coding: utf-8 -*-
"""Agente CORREIO (26/10/2026): de ~15 em 15 min olha so os METADADOS da caixa de entrada (Gmail, somente leitura, tudo local, nada vai a IA online) e avisa o
Dono no WhatsApp quando chega e-mail de PESSOA FISICA normal ou possivel OFERTA DE TRABALHO. Remetente + assunto apenas; nunca o corpo."""
import email.utils
import json
import re
import time

from .store import DATA

ESTADO = DATA / "correio.json"
ROBO = re.compile(r"no-?reply|do-?not-?reply|nao-?responda|notific|newsletter|mailer|marketing|news@|info@|contato@|suporte@|support@|alerts?@|updates?@|"
                  r"@(?:.+\.)?(?:facebookmail|linkedin|google|youtube|amazon|mercadolivre|nubank|ifood|airbnb|samsung|spotify|steampowered|epicgames|discord)\.", re.I)
CATEGORIAS_RUINS = {"CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL", "CATEGORY_UPDATES", "CATEGORY_FORUMS", "SPAM"}
MAX_AVISOS = 2
# 05/11: o Dono so quer aviso de algo EXTREMAMENTE importante; o resto vai so para o relatorio da manha (relato)
IMPORTANTE = re.compile(r"urgente|convoca|entrevista|aprovad|contrata|proposta de emprego|ex[eé]rcito|11.?rm|\bSTT\b|intima|cita[cç][aã]o|div[oó]rcio|cart[oó]rio|"
                        r"prazo (?:final|hoje|amanh)|[uú]ltimo dia|vence hoje|bloquead|invadid|acesso n[aã]o autorizado", re.I)


def _estado():
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def classificar(nome, end, assunto, cabecalhos, labels):
    """'pessoa' | 'trabalho' | '' . Pura (testavel). cabecalhos = dict com chaves em minusculas."""
    from .rotina import RUIDO, TRABALHO
    labels = set(labels or [])
    oferta = bool(TRABALHO.search(assunto)) and not RUIDO.search(assunto)
    if labels & {"SPAM", "CATEGORY_PROMOTIONS"}:
        return ""
    if oferta:
        return "trabalho"
    if labels & CATEGORIAS_RUINS:
        return ""
    automatico = cabecalhos.get("list-unsubscribe") or re.search(r"bulk|list|junk", cabecalhos.get("precedence", ""), re.I) or \
        cabecalhos.get("auto-submitted", "no").lower() not in ("", "no")
    return "pessoa" if nome and not automatico and not ROBO.search(end or "") else ""


def verificar(enviar_dono, n=40):
    """Devolve quantos avisos mandou. A primeira rodada so marca o que ja estava na caixa (nao inunda o WhatsApp)."""
    from . import gmail_web, ia_web
    try:                      # 28/10: pela aba logada do Chrome do Braniac (a API do Google expirava a cada 7 dias); so le remetente e assunto
        caixa = gmail_web.caixa(n)
    except ia_web.IAWebErro:
        return 0
    est = _estado()
    primeira = est.get("fonte") != "web"          # ids da API antigos nao servem: marca a caixa atual como vista, sem inundar o WhatsApp
    vistos = {} if primeira else dict.fromkeys(est.get("vistos", []))   # dict = conjunto com ordem (o corte [-500:] num set jogava fora ids recentes e reavisava o mesmo e-mail)
    avisos = 0
    for m in caixa:
        i = m["id"]
        if i in vistos:
            continue
        vistos[i] = None
        if primeira or not m["nao_lida"]:
            continue
        nome, end, assunto = (m["nome"] or "").strip(), m["email"], (m["assunto"] or "(sem assunto)")[:90]
        cab, m = {}, {"labelIds": []}
        tipo = classificar(nome, end, assunto, cab, m.get("labelIds"))
        if tipo and avisos < MAX_AVISOS:
            urgente = bool(IMPORTANTE.search(assunto))
            quem = (nome or end or "?")[:40]
            if tipo == "trabalho":    # 28/10: vaga vai para o Nando (triagem); o Correio continua so lendo
                try:
                    from . import candidaturas
                    candidaturas.receber("Correio", assunto, quem)
                except Exception:
                    pass
            est.setdefault("relato", []).append({"tipo": tipo, "quem": quem, "assunto": assunto, "ts": time.time()})   # entra na reuniao da manha
            if not urgente:
                continue
            enviar_dono(f"📬 E-mail de pessoa: {quem} — {assunto}" if tipo == "pessoa" else f"💼 Possível oferta de trabalho no e-mail: {quem} — {assunto}")
            avisos += 1
    est["vistos"] = list(vistos)[-500:]
    est["ts"], est["fonte"] = time.time(), "web"
    try:
        from . import barramento
        if avisos or primeira:
            barramento.enviar("Correio", "Compasso", "status", f"conferi a caixa: {avisos} aviso(s) ao Dono" if not primeira else "primeira conferencia: caixa marcada como vista")
    except Exception:
        pass
    ESTADO.write_text(json.dumps(est, ensure_ascii=False), encoding="utf-8")
    return avisos
