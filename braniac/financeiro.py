# -*- coding: utf-8 -*-
"""Agente FINANCEIRO (Cofre, 27/10/2026): so LE a conta InfinitePay do Dono (aba logada no Chrome do Braniac, porta 9222) e acompanha a META de saldo
(valor em data/pessoal.json) na conta ate o 5o DIA UTIL do mes. Guarda saldo e extrato so no PC (data/financeiro.json), nunca manda a IA online, nunca paga, transfere nem
mexe na conta. Gera previsao e alerta o Dono (WhatsApp) quando a meta esta em risco ou critica. Login: sempre o Dono."""
import json
import re
import time
from datetime import date, datetime, timedelta

from .store import DATA

ESTADO = DATA / "financeiro.json"
from . import pessoal as _pessoal
META = float(_pessoal.get("meta_conta", 0.0))   # meta de saldo do dono (data/pessoal.json)
URL = "https://app.infinitepay.io/home"
INTERVALO_S = 3600                   # le a conta no maximo 1x por hora
JANELA_DIAS = 14                     # ritmo = media dos ultimos 14 dias de extrato
FERIADOS = {(1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (11, 20), (12, 25)}      # nacionais fixos
FERIADOS_ANO = {2026: {date(2026, 4, 3)}, 2027: {date(2027, 3, 26)}}                                 # Sexta-feira Santa
MESES = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6, "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12}


def dia_util(d):
    return d.weekday() < 5 and (d.month, d.day) not in FERIADOS and d not in FERIADOS_ANO.get(d.year, ())


def quinto_dia_util(ano, mes):
    d, n = date(ano, mes, 1), 0
    while True:
        n += dia_util(d)
        if n == 5:
            return d
        d += timedelta(days=1)


def prazo_atual(hoje):
    """5o dia util do mes corrente; passou (dia seguinte em diante) -> o do proximo mes."""
    p = quinto_dia_util(hoje.year, hoje.month)
    return p if hoje <= p else quinto_dia_util(hoje.year + (hoje.month == 12), hoje.month % 12 + 1)


def dias_uteis_ate(hoje, prazo):
    """Dias uteis de amanha ate o prazo (inclusive)."""
    n, d = 0, hoje + timedelta(days=1)
    while d <= prazo:
        n += dia_util(d)
        d += timedelta(days=1)
    return n


def _valor(s):
    return float(s.replace("R$", "").replace(".", "").replace(",", ".").strip())


def parsear(texto, hoje):
    """Texto da home do InfinitePay -> (saldo, [movimentos]). Movimento = {data, desc, valor(+/-), hora}. Pura (testavel)."""
    texto = texto.replace(" ", " ")
    m = re.search(r"Seu saldo é de\s*R\$\s*([\d.,]+)", texto)
    saldo = _valor(m.group(1)) if m else None
    linhas = [l.strip() for l in texto.splitlines() if l.strip()]
    movs, data = [], None
    if saldo is None:    # aba escondida: o numero do saldo nao anima; o saldo do dia, logo abaixo da 1a data do extrato, e o mesmo valor
        for i, l in enumerate(linhas[:-1]):
            if re.match(r"^(Hoje|Ontem|[A-Za-zçÇ\-]+)? ?• \d{1,2} \w{3}, \d{4}$", l) and re.match(r"^R\$ ?[\d.,]+$", linhas[i + 1]):
                saldo = _valor(linhas[i + 1])
                break
    for i, l in enumerate(linhas):
        h = re.match(r"^(Hoje|Ontem|[A-Za-zçÇ\-]+)? ?• (\d{1,2}) (\w{3}), (\d{4})$", l)
        if h:
            data = date(int(h.group(4)), MESES.get(h.group(3).lower()[:3], 1), int(h.group(2)))
            continue
        v = re.match(r"^([+-])R\$ ?([\d.,]+)$", l)
        if v and data and i:
            hora = linhas[i + 1].split("•")[0].strip() if i + 1 < len(linhas) else ""
            movs.append({"data": data.isoformat(), "desc": linhas[i - 1][:60], "valor": (1 if v.group(1) == "+" else -1) * _valor(v.group(2)), "hora": hora})
    return saldo, movs


def _estado():
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _salvar(est):
    ESTADO.write_text(json.dumps(est, ensure_ascii=False), encoding="utf-8")


def ritmo(movs, hoje):
    """(entra_por_dia, sai_por_dia, dias_de_historico) nos ultimos JANELA_DIAS dias, so com o extrato que ja foi guardado."""
    ini = hoje - timedelta(days=JANELA_DIAS)
    mv = [m for m in movs if date.fromisoformat(m["data"]) > ini]
    if not mv:
        return 0.0, 0.0, 0
    dias = max(1, (hoje - min(date.fromisoformat(m["data"]) for m in mv)).days + 1)
    return sum(m["valor"] for m in mv if m["valor"] > 0) / dias, -sum(m["valor"] for m in mv if m["valor"] < 0) / dias, dias


def avaliar(saldo, movs, hoje):
    """Situacao da meta. nivel: batida | ok | atencao | critico. Pura (testavel)."""
    prazo = prazo_atual(hoje)
    du = dias_uteis_ate(hoje, prazo)
    corridos = (prazo - hoje).days
    entra, sai, hist = ritmo(movs, hoje)
    previsto = saldo + (entra - sai) * corridos
    falta = max(0.0, META - saldo)
    if saldo >= META:
        nivel = "batida"
    elif previsto >= META and du > 2:
        nivel = "ok"
    elif du <= 3 or previsto < META * 0.5:
        nivel = "critico"
    else:
        nivel = "atencao" if previsto < META else "ok"
    return {"saldo": saldo, "meta": META, "falta": falta, "prazo": prazo.isoformat(), "dias_uteis": du, "dias": corridos,
            "entra_dia": entra, "sai_dia": sai, "historico_dias": hist, "previsto": previsto, "nivel": nivel,
            "precisa_por_dia_util": falta / du if du else falta}


def _brl(v):
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def texto(av):
    prazo = date.fromisoformat(av["prazo"]).strftime("%d/%m")
    if av["nivel"] == "batida":
        return f"✅ Meta batida: você tem {_brl(av['saldo'])} na InfinitePay e a meta de {_brl(av['meta'])} vale até {prazo}."
    base = (f"saldo {_brl(av['saldo'])}, faltam {_brl(av['falta'])} para {_brl(av['meta'])} até o 5º dia útil ({prazo}, {av['dias_uteis']} dia(s) útil(eis)). "
            f"Precisa entrar uns {_brl(av['precisa_por_dia_util'])} por dia útil.")
    if av["historico_dias"] >= 5:
        base += f" Pelo seu ritmo dos últimos {av['historico_dias']} dias (entra {_brl(av['entra_dia'])}/dia, sai {_brl(av['sai_dia'])}/dia) a previsão é fechar em {_brl(av['previsto'])}."
    else:
        base += " Ainda tenho pouco histórico para prever bem."
    return {"critico": "🚨 META EM RISCO: ", "atencao": "⚠️ Atenção na meta: ", "ok": "📈 Meta no caminho: "}[av["nivel"]] + base


def ler_conta(hoje=None):
    """Recarrega a aba do InfinitePay e devolve (saldo, movs). Levanta RuntimeError se a sessao caiu (o Dono precisa logar)."""
    from . import ia_web, whatsapp
    hoje = hoje or date.today()
    with whatsapp.LOCK:
        try:
            with ia_web._Aba({"dominio": "infinitepay.io", "nova": URL}) as a:
                a.cmd("Target.activateTarget", {"targetId": a.url.rstrip("/").split("/")[-1]})
                a.cmd("Page.bringToFront")
                a.cmd("Page.navigate", {"url": URL})
                for _ in range(15):
                    time.sleep(2)
                    t = a.js("document.body.innerText") or ""
                    if parsear(t, hoje)[0] is not None or re.search(r"(?i)entrar|login|senha", t[:600]) and "saldo" not in t:
                        break
                saldo, movs = parsear(t, hoje)
        finally:
            ia_web._devolver_foco_ao_whatsapp()
    if saldo is None:
        raise RuntimeError("sessao do InfinitePay caiu ou a pagina mudou")
    return saldo, movs


def mudanca_texto(ant, novo, movs, falta_ant, av):
    """Mensagem de mudanca no saldo: o que aconteceu, os movimentos novos e o efeito na meta. Pura (testavel)."""
    d = novo - ant
    linhas = [f"💰 Mudança na conta: o saldo {'aumentou' if d > 0 else 'diminuiu'} {_brl(abs(d))} (era {_brl(ant)}, agora {_brl(novo)})."]
    if movs:
        linhas.append("Movimentos novos: " + "; ".join(f"{'+' if m['valor'] > 0 else '-'}{_brl(abs(m['valor']))} {m['desc'][:28]}" for m in movs[:4]) + ".")
    if av["nivel"] == "batida":
        linhas.append(f"Meta batida ✅ ({_brl(av['saldo'])} de {_brl(av['meta'])}).")
    else:
        efeito = ""
        if falta_ant is not None and abs(av["falta"] - falta_ant) >= 0.5:
            efeito = f" ({'aumentou' if av['falta'] > falta_ant else 'diminuiu'} {_brl(abs(av['falta'] - falta_ant))})"
        linhas.append(f"Para a meta de {_brl(av['meta'])} agora faltam {_brl(av['falta'])}{efeito}, {av['dias_uteis']} dia(s) útil(eis) até {date.fromisoformat(av['prazo']).strftime('%d/%m')}.")
    return " ".join(linhas)


def verificar(enviar_dono, agora=None, ler=ler_conta):
    """Chamado no tick (~10 min). Le a conta 1x/hora, guarda, avalia e alerta (8h-21h; 1 aviso por dia, ou na hora se o nivel piorar)."""
    agora = agora or datetime.now()
    est = _estado()
    if time.time() - est.get("ts", 0) < INTERVALO_S:
        return None
    est["ts"] = time.time()
    try:
        saldo, novos = ler(agora.date())
    except Exception as e:
        _salvar(est)
        if est.get("sessao_avisada") != agora.strftime("%Y-%m-%d") and 8 <= agora.hour < 21:
            est["sessao_avisada"] = agora.strftime("%Y-%m-%d")
            _salvar(est)
            enviar_dono("🔐 O agente financeiro não consegue ler a InfinitePay (sessão caiu). Quando puder, logue de novo na aba do Chrome do Braniac.")
        return None
    vistos = {(m["data"], m["desc"], m["valor"], m["hora"]) for m in est.get("movs", [])}
    novos_movs = [m for m in novos if (m["data"], m["desc"], m["valor"], m["hora"]) not in vistos]
    saldo_ant, falta_ant = est.get("saldo"), (est.get("avaliacao") or {}).get("falta")
    est["movs"] = (est.get("movs", []) + novos_movs)[-600:]
    est["saldo"], est["saldo_ts"] = saldo, agora.isoformat(timespec="minutes")
    av = avaliar(saldo, est["movs"], agora.date())
    if saldo_ant is not None and abs(saldo - saldo_ant) >= 0.5:      # o agente viu o saldo MUDAR: avisa o Jarvis, que fala com o Dono
        est["pendente_mudanca"] = mudanca_texto(saldo_ant, saldo, novos_movs, falta_ant, av)
    if est.get("pendente_mudanca") and 7 <= agora.hour < 22:         # de madrugada espera amanhecer
        enviar_dono(est.pop("pendente_mudanca"))
    ordem = {"batida": 0, "ok": 1, "atencao": 2, "critico": 3}
    hoje_s = agora.strftime("%Y-%m-%d")
    ult = est.get("alerta", {})
    mesmo_prazo = ult.get("prazo") == av["prazo"]
    if av["nivel"] == "batida":
        deve = not (mesmo_prazo and ult.get("nivel") == "batida")
    else:
        piorou = mesmo_prazo and ordem[av["nivel"]] > ordem.get(ult.get("nivel"), 0)
        deve = av["nivel"] in ("atencao", "critico") and (ult.get("dia") != hoje_s or piorou)
    if deve and 8 <= agora.hour < 21:
        enviar_dono(texto(av))
        est["alerta"] = {"nivel": av["nivel"], "prazo": av["prazo"], "dia": hoje_s}
    if est.get("resumo_dia") != hoje_s and 8 <= agora.hour < 21 and est.get("alerta", {}).get("dia") != hoje_s:     # 28/10: relatorio diario mesmo com a meta no caminho
        enviar_dono(texto(av))
        est["resumo_dia"] = hoje_s
    est["avaliacao"] = av
    _salvar(est)
    try:
        from . import barramento
        barramento.enviar("Cofre", "Compasso", "status", f"conta lida: saldo {_brl(saldo)}, meta {av['nivel']}")
    except Exception:
        pass
    return av


PERGUNTA = re.compile(r"(?i)\bsaldo\b|infinite\s?pay|\bextrato\b|\bfinanceir[oa]s?\b|\bmeta\b(?!\s+(?:ai|da\s+loja))|\bmetas\b|"
                      r"quanto\s+(?:tem|tenho|h[aá]|entrou|falta|faltam|sobrou|ganhou|recebeu|j[aá]\s+(?:tem|tenho|entrou|juntei))\b.{0,40}(?:conta|dinheiro|meta|banco|hoje|m[eê]s|1[.]?600)|"
                      r"(?:j[aá]\s+)?(?:bati|batemos|atingi|alcancei|consegui)\b.{0,20}(?:meta|1[.]?600)|\b1[.]?600\b|"
                      r"como\s+(?:est[aá]|anda|t[aá]|vai)\s.{0,30}(?:meta|conta|financeiro|dinheiro|grana)|\bgrana\b.{0,20}(?:conta|meta|m[eê]s)")


def eh_pergunta(texto):
    return bool(PERGUNTA.search(texto or ""))


def eh_vaquinha(texto):
    from . import modulos
    if not modulos.ativo("vaquinha"):
        return False
    return bool(re.search(r"(?i)vaquinha", texto or "")) and bool(re.search(r"(?i)quanto|arrecad|total|como\s+(?:est[aá]|anda|t[aá])|situa|relat[oó]rio|andamento", texto or ""))


def resposta(movs_n=6):
    """Resposta completa para quem tem acesso total (Dono, Parceira): so do que o agente ja guardou no PC, sem IA. Nunca traz senha/cartao/CPF (nao sao lidos)."""
    est = _estado()
    if est.get("saldo") is None:
        return "Ainda não consegui ler a conta da InfinitePay (o agente financeiro precisa da aba logada no Chrome do Braniac)."
    av = est.get("avaliacao") or avaliar(est["saldo"], est.get("movs", []), date.today())
    quando = datetime.fromisoformat(est["saldo_ts"]).strftime("%d/%m às %H:%M")
    ult = sorted(est.get("movs", []), key=lambda m: (m["data"], m["hora"]), reverse=True)[:movs_n]
    linhas = [f"• {date.fromisoformat(m['data']).strftime('%d/%m')} {m['hora']}  {'+' if m['valor'] > 0 else '-'}{_brl(abs(m['valor']))}  {m['desc']}" for m in ult]
    return (f"💰 Conta InfinitePay (lida em {quando}): saldo {_brl(est['saldo'])}.\n{texto(av)}\nÚltimas movimentações:\n" + "\n".join(linhas))
