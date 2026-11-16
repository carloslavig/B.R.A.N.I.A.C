# -*- coding: utf-8 -*-
"""Funil unico dos avisos AUTOMATICOS ao Dono (16/11/2026, Dono: "o Jarvis me manda mensagem demais").
- CRITICO (crise, CVV/SAMU, familia precisando dele) sai na hora, sempre.
- URGENTE (hospede, reserva, venda, ataque...) sai na hora, de dia e ate o teto diario; fora disso vai para o resumo.
- O resto vai para o RESUMO das horas em `horas_resumo` (um audio curto + um texto com os detalhes).
- Repetido some: o mesmo aviso (sem contar numeros e links) nao sai 2x em 6 h; na fila, o mais novo substitui o antigo.
Respostas ao que o Dono perguntou NAO passam por aqui: so as rotinas (rotina.tick) e os blocos [resumo] do outbox.
Config em data/funil_config.json (horas_resumo, silencio [inicio, fim], teto_dia, ligado)."""
import json, re, threading, time
from datetime import datetime

from .store import DATA

ARQ = DATA / "funil_dono.json"
CFG = DATA / "funil_config.json"
PADRAO = {"ligado": True, "horas_resumo": [9, 13, 19], "silencio": [22, 7], "teto_dia": 8}
CRITICO = re.compile(r"\bcrise\b|\bcvv\b|\bsamu\b|socorro|suic|emerg[eê]ncia|falou algo importante|precis[ao] de voc[eê] agora", re.I)
URGENTE = re.compile(r"urgent|h[oó]spede|reserva|check-?in|airbnb|quer fechar|fechou|\bvenda\b|\blead\b|invas|ataque|senha errada|login suspeito", re.I)
REPETE_S = 6 * 3600
_LK = threading.Lock()


def cfg():
    try:
        return {**PADRAO, **json.loads(CFG.read_text(encoding="utf-8"))}
    except Exception:
        return dict(PADRAO)


def _ler():
    try:
        return json.loads(ARQ.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _gravar(est):
    ARQ.write_text(json.dumps(est, ensure_ascii=False), encoding="utf-8")


def chave(texto):
    """O mesmo aviso com outro numero/link conta como repetido (ex.: 'saldo era X, agora Y', 'link novo: ...')."""
    t = re.sub(r"https?://\S+|\d+([.,:]\d+)*", "", (texto or "").lower())
    return re.sub(r"\W+", "", t)[:80]


def _silencio(h, c):
    ini, fim = c["silencio"]
    return h >= ini or h < fim if ini > fim else ini <= h < fim


def passar(texto, origem="rotina", agora=None):
    """Decide um aviso automatico. 'agora' = manda ja; 'fila' = vai para o resumo; 'repetido' = descartado."""
    c = cfg()
    if not c["ligado"]:
        return "agora"
    agora = agora or datetime.now()
    ts, hoje, k = agora.timestamp(), agora.strftime("%Y-%m-%d"), chave(texto)
    with _LK:
        est = _ler()
        env = {kk: t for kk, t in est.get("enviados", {}).items() if ts - t < REPETE_S}
        est["enviados"] = env
        if k and k in env:
            _gravar(est)
            return "repetido"
        cont = est.get("contagem", {})
        cont = {hoje: cont.get(hoje, 0)}
        critico = bool(CRITICO.search(texto or ""))
        urgente = bool(URGENTE.search(texto or "")) and not _silencio(agora.hour, c) and cont[hoje] < c["teto_dia"]
        if critico or urgente:
            env[k] = ts
            cont[hoje] += 1
            est["contagem"] = cont
            _gravar(est)
            return "agora"
        fila = [x for x in est.get("fila", []) if x["k"] != k] + [{"k": k, "texto": str(texto)[:900], "origem": origem, "ts": ts}]
        est["fila"] = fila[-40:]
        _gravar(est)
        return "fila"


def envolver(enviar, dono=None):
    """enviar(nome, texto) -> mesmo formato, mas o que vai ao Dono passa pelo funil (o resto passa direto)."""
    from . import contexto
    def f(nome, texto, origem="rotina"):
        alvo = dono or contexto.contato("dono") or "Eu"
        if contexto._norm(nome or "") != contexto._norm(alvo):
            return enviar(nome, texto)
        d = passar(texto, origem)
        return enviar(nome, texto) if d == "agora" else f"✅ Aviso {d} (funil do Dono)."
    return f


def _fala(x):
    t = re.sub(r"https?://\S+|[A-Za-z]:[\\/]\S+|[🀀-🿿☀-➿]", "", x)
    t = " ".join(t.split())
    m = re.match(r"(.{20,160}?[.!?:])(\s|$)", t)
    return (m.group(1) if m else t[:160]).strip()


def resumo(fila):
    """(fala curta, texto com detalhes) do resumo."""
    n = len(fila)
    fala = f"Resumo do Jarvis, senhor Dono: {n} aviso{'s' if n > 1 else ''}. " + " ".join(f"{i}. {_fala(x['texto'])}" for i, x in enumerate(fila[:6], 1))
    if n > 6:
        fala += f" E mais {n - 6} no texto."
    texto = "📋 Resumo do Jarvis\n\n" + "\n\n".join(f"• {x['texto']}" for x in fila)
    return fala[:1100], texto[:3500]


def tick(agora, enviar, audio, nome=None):
    """Na hora de resumo (fora do silencio), manda a fila acumulada: audio curto + texto. Devolve quantos avisos entregou."""
    from . import contexto
    c = cfg()
    if agora.hour not in c["horas_resumo"] or _silencio(agora.hour, c):
        return 0
    marca = agora.strftime("%Y-%m-%d %H")
    with _LK:
        est = _ler()
        fila = est.get("fila", [])
        if not fila or est.get("ultimo_resumo") == marca:
            return 0
        est["ultimo_resumo"] = marca
        _gravar(est)
    nome = nome or contexto.contato("dono") or "Eu"
    fala, texto = resumo(fila)
    ok = str(enviar(nome, texto)).startswith("✅")
    if ok:
        try:
            audio(nome, fala)
        except Exception:
            pass
        with _LK:
            est = _ler()
            mandados = {(x["k"], x["ts"]) for x in fila}    # o que chegou na fila durante o envio fica para o proximo resumo
            est["fila"] = [x for x in est.get("fila", []) if (x["k"], x["ts"]) not in mandados]
            est.setdefault("enviados", {}).update({k: agora.timestamp() for k, _ in mandados})
            _gravar(est)
        return len(fila)
    with _LK:    # falhou: tenta de novo no proximo tick da mesma hora
        est = _ler()
        est.pop("ultimo_resumo", None)
        _gravar(est)
    return 0
