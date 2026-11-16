# -*- coding: utf-8 -*-
"""IAs GRATIS EXTRAS no Braniac (24/10/2026), vindas do FreeLLMAPI (MIT, nosso fork carloslavig/freellmapi): catalogo de modelos gratis com os limites de
cada um (por minuto e por dia). Basta a chave do provedor estar no .env que os melhores modelos dele entram na cadeia do roteador, SEM mudar a interface.
O roteador respeita os limites (nao gasta chamada que daria 429) e o descanso/troca automatica que ja existia faz o resto.
Mandar texto a esses servicos so acontece para perguntas sem dado pessoal (o roteador ja bloqueia o conteudo sensivel das IAs online).
Ver o que esta ativo: python -m braniac.gratis"""
import json
import os
import re
import time
from pathlib import Path

DADOS = Path(__file__).resolve().parent / "data"
CACHE = DADOS / "gratis_modelos.json"
TTL_S = 12 * 3600
FAMILIAS = re.compile(r"(?i)gpt-oss|deepseek|kimi|qwen3|nemotron|llama-3\.3|llama-4|gemma-3|mistral-large|magistral|glm-4|minimax")   # modelos novos que o catalogo antigo nao conhece
ARQ = Path(__file__).resolve().parent / "catalogo_gratis.json"
POR_PROVEDOR = 3          # quantos modelos de cada provedor entram (os melhores pelo ranking)
CONTEXTO_MIN = 30000      # o Braniac manda dossie + historico: modelo com contexto pequeno nao serve


def catalogo():
    try:
        return json.loads(ARQ.read_text(encoding="utf-8"))["provedores"]
    except (OSError, ValueError, KeyError):
        return {}


RUIM = re.compile(r"(?i)embed|whisper|guard|vision|image|tts|rerank|safety|moderation|orpheus|-vl\b|prompt")   # nao sao modelos de conversa


def _melhores(modelos, n, vivos=None, excluir=()):
    """Os n melhores (ranking do catalogo). `vivos` = ids que o provedor oferece AGORA: o catalogo envelhece (modelo some/muda de nome),
    entao so vale o que existe de verdade; se faltar, completa com modelos recentes das familias fortes (sem limites conhecidos)."""
    ok = [(v["inteligencia"], v["velocidade"], mid, v) for mid, v in modelos.items()
          if (v.get("contexto") or 0) >= CONTEXTO_MIN and (vivos is None or mid in vivos) and mid not in excluir and not RUIM.search(mid)]
    escolhidos = [(mid, v) for _, _, mid, v in sorted(ok)[:n]]
    if vivos is not None and len(escolhidos) < n:
        usados = {m for m, _ in escolhidos}
        for mid in sorted(vivos):
            if len(escolhidos) >= n:
                break
            if mid not in usados and mid not in modelos and mid not in excluir and FAMILIAS.search(mid) and not RUIM.search(mid):
                escolhidos.append((mid, {"inteligencia": 50, "velocidade": 9, "rpm": None, "rpd": None, "contexto": None}))
    return escolhidos


def _listar_vivos(plat, d, chave):
    """Ids de modelos que o provedor oferece agora (GET /models com a chave), em cache de 12 h. None se nao der para saber."""
    try:
        cache = json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    c = cache.get(plat)
    if c and time.time() - c["ts"] < TTL_S:
        return set(c["ids"])
    try:
        import requests
        r = requests.get(d["base"].rstrip("/") + "/models", headers={"Authorization": "Bearer " + chave}, timeout=6)
        itens = r.json().get("data") or []
        ids = sorted({str(i["id"]) for i in itens if i.get("id") and (plat != "openrouter" or str(i["id"]).endswith(":free"))})
        if r.status_code == 200 and ids:
            cache[plat] = {"ts": time.time(), "ids": ids}
            DADOS.mkdir(exist_ok=True)
            CACHE.write_text(json.dumps(cache), encoding="utf-8")
            return set(ids)
    except Exception:
        pass
    return set(c["ids"]) if c else None


def estender(cfg, env=None, n=POR_PROVEDOR, listar=None):
    """Acrescenta a cfg['cadeia'] os melhores modelos gratis dos provedores com chave no ambiente. Devolve os nomes adicionados."""
    env = os.environ if env is None else env
    cadeia = cfg["cadeia"]
    ja = {(p.get("url"), p.get("modelo")) for p in cadeia}
    novos = []
    for plat, d in catalogo().items():
        if not str(env.get(d["env"], "")).strip():
            continue
        url = d["base"].rstrip("/") + "/chat/completions"
        vivos = (listar or _listar_vivos)(plat, d, str(env.get(d["env"])).strip())
        if vivos is None:
            continue      # nao deu para conferir quais modelos existem agora: nao arrisca ids velhos
        for mid, v in _melhores(d["modelos"], n, vivos, {m for u, m in ja if u == url}):
            p = {"nome": f"gratis:{plat}:{mid}", "tipo": "online", "api": "openai", "url": url, "modelo": mid, "chave_env": d["env"],
                 "classe": "rapido" if v["velocidade"] <= 3 else "padrao"}
            for k, campo in (("limite_min", "rpm"), ("limite_dia", "rpd")):
                if v.get(campo):          # sem limite conhecido = sem a chave (o roteador usa um padrao; None quebrava o calculo de custo)
                    p[k] = v[campo]
            novos.append(p)
    pos = next((i for i, p in enumerate(cadeia) if p["tipo"] != "online"), len(cadeia))   # antes do Ollama e do Claude
    cadeia[pos:pos] = novos
    return [p["nome"] for p in novos]


def diagnostico(env=None):
    env = os.environ if env is None else env
    linhas = []
    for plat, d in catalogo().items():
        tem = bool(str(env.get(d["env"], "")).strip())
        vivos = _listar_vivos(plat, d, str(env.get(d["env"], "")).strip()) if tem else None
        modelos = [mid for mid, _ in _melhores(d["modelos"], POR_PROVEDOR, vivos)]
        linhas.append(f"{'ATIVO  ' if tem else 'sem chave'} {d['nome']:<12} {d['env']:<22} " + (", ".join(modelos) if tem else f"crie a chave em {d['criar_chave']}"))
    return "\n".join(linhas)


if __name__ == "__main__":
    from .router import carregar_env
    carregar_env()
    print(diagnostico())
