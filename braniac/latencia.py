# -*- coding: utf-8 -*-
"""Latencia por provedor de IA: cada chamada vira uma linha (provedor, ms, ok) em data/latencia.jsonl. NUNCA grava o texto da pergunta.
`python -m braniac.latencia` imprime P50 e P95 por provedor."""
import json, statistics, time
from collections import deque
from . import store

JANELA = 50


def _arq():
    return store.DATA / "latencia.jsonl"     # via store.DATA: os testes ja isolam essa pasta


def registrar(provedor, ms, ok):
    try:
        _arq().parent.mkdir(parents=True, exist_ok=True)
        with _arq().open("a", encoding="utf-8") as f:
            f.write(json.dumps({"t": int(time.time()), "provedor": provedor, "ms": int(ms), "ok": bool(ok)}) + "\n")
    except OSError:
        pass                                  # medir latencia nunca derruba a resposta


def carregar(janela=JANELA):
    """{provedor: deque com os ms das ultimas `janela` chamadas que deram certo}."""
    # shortcut: le o arquivo inteiro na partida; se ficar grande (MBs), passar a ler so o fim ou rotacionar
    out = {}
    try:
        linhas = _arq().read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for l in linhas:
        try:
            d = json.loads(l)
        except ValueError:
            continue
        if d.get("ok"):
            out.setdefault(d["provedor"], deque(maxlen=janela)).append(d["ms"])
    return out


def falhas_seguidas():
    """{provedor: [quantas falhas seguidas ate agora, hora da ultima]} (so quem terminou o registro falhando)."""
    out = {}
    try:
        linhas = _arq().read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for l in linhas:
        try:
            d = json.loads(l)
        except ValueError:
            continue
        if d.get("ok"):
            out.pop(d["provedor"], None)
        else:
            out[d["provedor"]] = [out.get(d["provedor"], [0, 0])[0] + 1, d.get("t", 0)]
    return out


def mediana_s(amostras, nome):
    a = amostras.get(nome)
    return statistics.median(a) / 1000.0 if a else None


def _pct(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, int(round(p / 100.0 * (len(v) - 1))))]


def relatorio():
    por = {}
    try:
        linhas = _arq().read_text(encoding="utf-8").splitlines()
    except OSError:
        linhas = []
    for l in linhas:
        try:
            d = json.loads(l)
        except ValueError:
            continue
        r = por.setdefault(d["provedor"], {"ms": [], "falhas": 0})
        if d.get("ok"):
            r["ms"].append(d["ms"])
        else:
            r["falhas"] += 1
    if not por:
        return "Sem chamadas registradas ainda."
    out = [f"{'provedor':<24}{'P50 ms':>9}{'P95 ms':>9}{'ok':>6}{'falhas':>8}"]
    for nome, r in sorted(por.items(), key=lambda kv: _pct(kv[1]["ms"], 50) if kv[1]["ms"] else 1e12):
        p50, p95 = (_pct(r["ms"], 50), _pct(r["ms"], 95)) if r["ms"] else ("-", "-")
        out.append(f"{nome:<24}{p50:>9}{p95:>9}{len(r['ms']):>6}{r['falhas']:>8}")
    return "\n".join(out)


if __name__ == "__main__":
    print(relatorio())
