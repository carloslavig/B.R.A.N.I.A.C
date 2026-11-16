# -*- coding: utf-8 -*-
"""EMPRESA DE INVESTIMENTOS "Quantix" (01/11/2026, pedido do Dono): andar de agentes que investe por perfil de risco (daytrade, swing, holding).
Nome, equipe, salas e limites vieram do conselho de IAs (data/conselho_inv.txt) e ficam em data/empresa_inv/equipe.json.
Método das skills day-trader-skill e claude-trading-skills (MIT), copiadas em .claude/skills e braniac/skills.
TRAVAS: tudo é SIMULAÇÃO (paper). Não existe caminho de ordem real aqui: ordem real exige o OK 2 do Dono, por ordem, e uma integração
com corretora que NÃO foi feita. Só compra (sem short, sem alavancagem). Cada proposta passa por Sigma (tamanho) -> Vigil (risco) -> Guarda (disciplina)
e só executa com o OK 1 do dono. Nada aqui paga, transfere ou pede dado bancário."""
import json
import re
import threading
import time
import urllib.request
from datetime import datetime

from .store import DATA

PASTA = DATA / "empresa_inv"
EQUIPE_JSON = PASTA / "equipe.json"
CARTEIRA_JSON = PASTA / "carteira.json"
PROPOSTAS_JSON = PASTA / "propostas.json"
PERFIS = ("daytrade", "swing", "holding")
TICKER = re.compile(r"^[A-Z0-9.\-]{1,10}$")
AVISO = "Simulação, não é consultoria financeira, sem garantia de retorno."
JANELA = {"semana": 7, "mes": 30, "trimestre": 90}
_lock = threading.RLock()


def _ler(p, padrao):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return padrao


def _gravar(p, d):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def config():
    return _ler(EQUIPE_JSON, {"empresa": "Quantix", "agentes": [], "perfis": {}})


def agentes():
    return config().get("agentes", [])


def nomes():
    return [a["nome"] for a in agentes()]


def carteira():
    c = _ler(CARTEIRA_JSON, {})
    for p in PERFIS:
        c.setdefault(p, {"capital": 0.0, "caixa": 0.0, "posicoes": [], "fechadas": []})
    return c


def depositar(perfil, valor):
    """Depósito VIRTUAL no perfil (simulação). Dinheiro real nunca passa por aqui."""
    if perfil not in PERFIS or valor <= 0:
        return "Perfil inválido ou valor <= 0."
    with _lock:
        c = carteira()
        c[perfil]["capital"] += valor
        c[perfil]["caixa"] += valor
        _gravar(CARTEIRA_JSON, c)
    return f"Depósito virtual de {valor:.2f} no perfil {perfil}. {AVISO}"


def preco(ticker):
    """Último preço (Yahoo Finance, gratuito). None se falhar."""
    if not TICKER.match(ticker):
        return None
    try:
        rq = urllib.request.Request(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1d&interval=1m", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(rq, timeout=10) as r:
            return float(json.load(r)["chart"]["result"][0]["meta"]["regularMarketPrice"])
    except Exception:
        return None


def _pnl_dia(cp):
    h = datetime.now().strftime("%Y-%m-%d")
    return sum(f["pnl"] for f in cp["fechadas"] if f["fechada_em"][:10] == h)


def _perda_janela(cp, dias):
    lim = time.time() - dias * 86400
    perdas = sum(f["pnl"] for f in cp["fechadas"] if f["ts_fechada"] >= lim)
    return max(0.0, -perdas) / cp["capital"] * 100 if cp["capital"] else 0.0


def avaliar(perfil, ticker, entrada, stop, alvo, cart=None):
    """Sigma dimensiona; Vigil e Guarda vetam. Devolve (qtd, [motivos de veto])."""
    cart = cart or carteira()
    cfg = config().get("perfis", {}).get(perfil)
    if not cfg:
        return 0, ["perfil desconhecido"]
    cp = cart[perfil]
    if not TICKER.match(ticker or "") or not (entrada > 0 and 0 < stop < entrada):
        return 0, ["Guarda: ticker inválido, ou não é compra com stop abaixo da entrada"]
    if cp["capital"] <= 0:
        return 0, ["Vigil: perfil sem capital (faça um depósito virtual)"]
    risco_un = entrada - stop
    qtd = int(min(cp["capital"] * cfg["risco_trade"] / 100 / risco_un, cp["capital"] * cfg["exposicao"] / 100 / entrada))   # Sigma
    vetos = []
    if qtd < 1:
        vetos.append("Sigma: capital pequeno demais para 1 unidade dentro do limite")
    if qtd * entrada > cp["caixa"]:
        vetos.append("Vigil: caixa insuficiente")
    rr = (alvo - entrada) / risco_un if alvo else 0
    if cfg["rr_min"] and rr < cfg["rr_min"]:
        vetos.append(f"Guarda: retorno/risco {rr:.2f} abaixo de {cfg['rr_min']}")
    if cfg.get("perda_dia") and -_pnl_dia(cp) >= cp["capital"] * cfg["perda_dia"] / 100:
        vetos.append("Vigil: perda máxima do dia atingida")
    dd = _perda_janela(cp, JANELA.get(cfg["breaker_janela"], 30))
    if dd >= cfg["breaker"]:
        vetos.append(f"Vigil: circuit breaker (perda de {dd:.1f}% na janela de {cfg['breaker_janela']})")
    return qtd, vetos


def propor(perfil, ticker, entrada, stop, alvo=0.0, tese=""):
    """Abre uma proposta; só vira posição com aprovar() (OK 1 do dono)."""
    ticker = (ticker or "").upper().strip()
    qtd, vetos = avaliar(perfil, ticker, entrada, stop, alvo)
    with _lock:
        ps = _ler(PROPOSTAS_JSON, [])
        p = {"id": f"Q{len(ps) + 1:03d}", "perfil": perfil, "ticker": ticker, "entrada": entrada, "stop": stop, "alvo": alvo, "qtd": qtd,
             "risco_max": round(qtd * (entrada - stop), 2) if qtd else 0, "tese": tese[:300], "estado": "vetada" if vetos else "aguardando_ok",
             "vetos": vetos, "criada": time.time()}
        ps.append(p)
        _gravar(PROPOSTAS_JSON, ps)
    if vetos:
        return f"{p['id']} vetada: " + "; ".join(vetos)
    return f"{p['id']}: {perfil} compra {qtd} {ticker} a {entrada}, stop {stop}, alvo {alvo}, risco máx {p['risco_max']}. Aguardando o OK do Dono. {AVISO}"


def aprovar(id_):
    """OK 1: executa em PAPEL (agente Papel), reavaliando os limites na hora. Ordem real não existe aqui."""
    with _lock:
        ps = _ler(PROPOSTAS_JSON, [])
        p = next((x for x in ps if x["id"] == id_.upper()), None)
        if not p or p["estado"] != "aguardando_ok":
            return "Proposta não encontrada ou não está aguardando OK."
        cart = carteira()
        qtd, vetos = avaliar(p["perfil"], p["ticker"], p["entrada"], p["stop"], p["alvo"], cart)
        if vetos:
            p.update(estado="vetada", vetos=vetos)
            _gravar(PROPOSTAS_JSON, ps)
            return f"{p['id']} vetada na reavaliação: " + "; ".join(vetos)
        cp = cart[p["perfil"]]
        cp["caixa"] -= qtd * p["entrada"]
        cp["posicoes"].append({"id": p["id"], "ticker": p["ticker"], "qtd": qtd, "entrada": p["entrada"], "stop": p["stop"], "alvo": p["alvo"],
                               "aberta_em": datetime.now().isoformat(timespec="seconds")})
        p["estado"] = "executada_papel"
        _gravar(CARTEIRA_JSON, cart)
        _gravar(PROPOSTAS_JSON, ps)
    return f"{p['id']} executada em PAPEL: {qtd} {p['ticker']} a {p['entrada']}. {AVISO}"


def fechar(id_, preco_saida):
    """Encerra a posição (stop, alvo ou decisão) e registra no diário (Cronos)."""
    with _lock:
        cart = carteira()
        for perfil in PERFIS:
            cp = cart[perfil]
            pos = next((x for x in cp["posicoes"] if x["id"] == id_.upper()), None)
            if pos:
                pnl = round((preco_saida - pos["entrada"]) * pos["qtd"], 2)
                cp["posicoes"].remove(pos)
                cp["caixa"] += pos["qtd"] * preco_saida
                cp["capital"] += pnl
                cp["fechadas"].append({**pos, "saida": preco_saida, "pnl": pnl, "fechada_em": datetime.now().isoformat(timespec="seconds"), "ts_fechada": time.time()})
                _gravar(CARTEIRA_JSON, cart)
                return f"Cronos: {pos['id']} {pos['ticker']} fechada a {preco_saida}, resultado {pnl:+.2f}."
    return "Posição não encontrada."


def tick(agora=None, enviar=None):
    """Vigil: fecha em papel as posições que tocaram stop ou alvo. Sem posição aberta não faz nada (nem rede)."""
    saidas = []
    for cp in carteira().values():
        for pos in list(cp["posicoes"]):
            px = preco(pos["ticker"])
            if px is not None and (px <= pos["stop"] or (pos["alvo"] and px >= pos["alvo"])):
                saidas.append(fechar(pos["id"], px))
    if saidas and enviar:
        enviar("\n".join(saidas))
    return saidas


def situacao():
    c = carteira()
    return {"empresa": config().get("empresa"), "agentes": len(agentes()), "modo": "simulacao",
            "perfis": {p: {"capital": round(c[p]["capital"], 2), "posicoes": len(c[p]["posicoes"]), "fechadas": len(c[p]["fechadas"])} for p in PERFIS},
            "propostas_aguardando": sum(1 for x in _ler(PROPOSTAS_JSON, []) if x["estado"] == "aguardando_ok")}


def quadro():
    s = situacao()
    return (f"Quantix ({s['modo']}): " + "; ".join(f"{p}: capital {v['capital']}, {v['posicoes']} aberta(s)" for p, v in s["perfis"].items())
            + f"; {s['propostas_aguardando']} proposta(s) aguardando OK. {AVISO}")
