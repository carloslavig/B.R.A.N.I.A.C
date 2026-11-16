# -*- coding: utf-8 -*-
"""A.L.M.A. APRENDE (01/11/2026, plano do conselho de IAs em data/conselho_alma.txt). 100% local, sem IA online.
1) Tema: regex (alma_cuida) -> Naive Bayes local treinado no diario + rotulos do Dono; confianca < 0.55 vira "indefinido" (nunca forca tema).
2) Contexto trabalho/casa/neutro como ETIQUETA no registro (nao e subsistema).
3) Sinais indiretos: so METADADOS de cada mensagem (hora, tamanho, pontuacao, emoji, giria, intervalo). O texto nao entra aqui.
4) Humor: z-score contra a propria linha de base da mesma faixa do dia; so conta com 3+ sinais fora do normal em 2 janelas seguidas (histerese). Nao e diagnostico:
   o unico efeito e a Alma pedir ao Jarvis um tom mais calmo/breve (dica_tom). Nunca pergunta sobre humor.
5) Perfil (perfil.db): estilo por janela 7/30/90d, temperamento por faixa/dia da semana, exemplos "situacao -> resposta" aprovados e correcoes, para um clone FUTURO.
6) Privacidade: consentimento por parte, pausa, ver/apagar tudo (painel /alma), retencao de 90 dias nos sinais brutos, nunca guarda segredo nem texto de crise."""
import json
import math
import re
import sqlite3
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime

from .store import DATA

PASTA = DATA / "alma"
BANCO = PASTA / "perfil.db"
CONSENT = PASTA / "consentimento.json"
ESTADO = PASTA / "humor_estado.json"
DIARIO = PASTA / "diario.jsonl"
PADRAO = {"temas": True, "sinais": True, "exemplos": True, "pausado": False}
CONF_MIN = 0.55
RETENCAO_S = 90 * 86400
LOCK = threading.Lock()
PISO = {"comp": 3.0, "excl": 0.5, "ret": 0.5, "emoji": 0.5, "giria": 0.5, "intervalo": 120.0}
SINAIS = ("comp", "excl", "ret", "emoji", "giria", "intervalo")
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
GIRIAS = re.compile(r"\b(né|tá|pra|vc|bora|cara|beleza|blz|valeu|vlw|opa|mano|poha|uai|kkk+|show|massa)\b", re.I)
SEGREDO = re.compile(r"cart[aã]o|cpf|senha|c[oó]digo|token|pix|transfer|pagamento|boleto|conta banc|chave|segredo|login|\bcvv\b", re.I)
CRISE = re.compile(r"suicid|me matar|quero morrer|n[aã]o quero mais viver|desistir de tudo|acabar com tudo|me machucar", re.I)


def _db():
    PASTA.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(BANCO))
    c.executescript("""
    CREATE TABLE IF NOT EXISTS sinais(ts REAL, hora INT, dow INT, comp REAL, excl REAL, ret REAL, emoji REAL, giria REAL, intervalo REAL);
    CREATE TABLE IF NOT EXISTS rotulos(id INTEGER PRIMARY KEY, ts REAL, texto TEXT, tema_sugerido TEXT, tema_dono TEXT);
    CREATE TABLE IF NOT EXISTS estilo(janela TEXT, ts REAL, json TEXT);
    CREATE TABLE IF NOT EXISTS temperamento(ts REAL, json TEXT);
    CREATE TABLE IF NOT EXISTS exemplos(id INTEGER PRIMARY KEY, ts REAL, situacao TEXT, resposta TEXT, contexto TEXT, aprovado INT DEFAULT 1);
    CREATE TABLE IF NOT EXISTS correcoes(ts REAL, o_que TEXT, antes TEXT, depois TEXT);""")
    return c


def consentimento():
    try:
        return {**PADRAO, **json.loads(CONSENT.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return dict(PADRAO)


def definir_consentimento(**kw):
    c = consentimento()
    c.update({k: bool(v) for k, v in kw.items() if k in PADRAO})
    PASTA.mkdir(parents=True, exist_ok=True)
    CONSENT.write_text(json.dumps(c), encoding="utf-8")
    return c


def _ativo(parte):
    c = consentimento()
    return not c["pausado"] and c.get(parte, True)


def _tokens(t):
    return [w for w in re.findall(r"[a-zà-ÿ]{3,}", (t or "").lower())]


# ---------- 1) tema + contexto ----------

def contexto(texto, tema="", agora=None):
    """trabalho | casa | neutro, por tema e palavras; horario so desempata (a programacao de madrugada nao vira 'casa')."""
    agora = agora or datetime.now()
    if tema in ("trabalho", "ti") or re.search(r"cliente|vaga|entrevista|prazo|reuni[aã]o|projeto|deploy|servidor", texto or "", re.I):
        return "trabalho"
    if tema in ("familia", "saude", "emocional") or re.search(r"casa|jantar|almo[cç]o|filho|filho|m[aã]e|mainha|pai\b", texto or "", re.I):
        return "casa"
    return "neutro"


def _treino():
    amostras = []
    try:
        for l in DIARIO.read_text(encoding="utf-8").splitlines():
            x = json.loads(l)
            if x.get("tema"):
                amostras.append((x["tema"], _tokens(x.get("texto"))))
    except (OSError, ValueError):
        pass
    with _db() as c:
        for tema, texto in c.execute("SELECT tema_dono, texto FROM rotulos WHERE tema_dono IS NOT NULL AND tema_dono != ''"):
            amostras.append((tema, _tokens(texto)))
    return amostras


def tema_nb(texto, treino=None):
    """(tema, confianca). Naive Bayes multinomial com suavizacao de Laplace. Sem dados suficientes: ("indefinido", 0.0)."""
    treino = _treino() if treino is None else treino
    toks = _tokens(texto)
    classes = Counter(t for t, _ in treino)
    if len(treino) < 20 or len(classes) < 2 or not toks:
        return "indefinido", 0.0
    vocab = {w for _, ws in treino for w in ws}
    cont = {k: Counter() for k in classes}
    for t, ws in treino:
        cont[t].update(ws)
    logs = {}
    for k in classes:
        tot = sum(cont[k].values()) + len(vocab) + 1
        logs[k] = math.log(classes[k] / len(treino)) + sum(math.log((cont[k][w] + 1) / tot) for w in toks)
    m = max(logs.values())
    exp = {k: math.exp(v - m) for k, v in logs.items()}
    s = sum(exp.values())
    melhor = max(exp, key=exp.get)
    conf = exp[melhor] / s
    return (melhor, round(conf, 2)) if conf >= CONF_MIN else ("indefinido", round(conf, 2))


def completar_tema(texto, c):
    """Chamado pelo ciclo da Alma: mantem o tema das regex; se vazio, tenta o NB. Acrescenta confianca e contexto em `c`."""
    if c.get("tema"):
        c["confianca"] = 1.0
    elif _ativo("temas"):
        tema, conf = tema_nb(texto)
        c["tema"] = "" if tema == "indefinido" else tema
        c["confianca"] = conf
        if tema == "indefinido":
            c["tema_indef"] = True
    c["contexto"] = contexto(texto, c.get("tema", ""))
    return c


def enfileirar_rotulo(texto, tema_sugerido=""):
    if not _ativo("temas") or CRISE.search(texto or "") or SEGREDO.search(texto or "") or len(texto or "") < 12:
        return False
    with LOCK, _db() as c:
        if c.execute("SELECT 1 FROM rotulos WHERE texto=?", (texto[:200],)).fetchone():
            return False
        c.execute("INSERT INTO rotulos(ts,texto,tema_sugerido) VALUES(?,?,?)", (time.time(), texto[:200], tema_sugerido))
    return True


def pendentes_rotulo(n=10):
    with _db() as c:
        return [dict(zip(("id", "texto", "sugerido"), r)) for r in c.execute(
            "SELECT id,texto,tema_sugerido FROM rotulos WHERE tema_dono IS NULL ORDER BY ts DESC LIMIT ?", (n,))]


def rotular(id_, tema):
    if tema not in ("saude", "emocional", "familia", "ti", "trabalho", "outros"):
        return False
    with LOCK, _db() as c:
        c.execute("UPDATE rotulos SET tema_dono=? WHERE id=?", (tema, id_))
        c.execute("INSERT INTO correcoes VALUES(?,?,?,?)", (time.time(), "rotulo", "", tema))
    return True


# ---------- 2) sinais e humor ----------

def metricas(texto, ts, anterior_ts=None):
    t = texto or ""
    d = datetime.fromtimestamp(ts)
    pal = max(1, len(t.split()))
    return {"ts": ts, "hora": d.hour, "dow": d.weekday(), "comp": float(pal), "excl": float(t.count("!")),
            "ret": float(len(re.findall(r"\.\.\.|…", t))), "emoji": float(len(EMOJI.findall(t))), "giria": float(len(GIRIAS.findall(t))),
            "intervalo": float(min(21600, ts - anterior_ts)) if anterior_ts else 0.0}


def registrar_sinais(texto, ts=None):
    """Guarda SO numeros. Texto de crise ou com segredo nem gera metrica."""
    ts = ts or time.time()
    if not _ativo("sinais") or CRISE.search(texto or "") or SEGREDO.search(texto or ""):
        return False
    with LOCK, _db() as c:
        ant = c.execute("SELECT MAX(ts) FROM sinais").fetchone()[0]
        m = metricas(texto, ts, ant)
        c.execute("INSERT INTO sinais VALUES(?,?,?,?,?,?,?,?,?)", tuple(m[k] for k in ("ts", "hora", "dow", *SINAIS)))
    return True


def _faixa(h):
    return 0 if h < 6 else 1 if h < 12 else 2 if h < 18 else 3


def _linhas(c, de, ate):
    return c.execute("SELECT ts,hora," + ",".join(SINAIS) + " FROM sinais WHERE ts>=? AND ts<? ORDER BY ts", (de, ate)).fetchall()


def _janela_fora(linhas, base):
    """Quantos sinais saem do normal (|z| > 1.5) e o z medio de energia/tensao. base: {sinal: (media, desvio)}."""
    zs = {}
    for i, s in enumerate(SINAIS):
        mu, sd = base[s]
        media = sum(l[2 + i] for l in linhas) / len(linhas)
        zs[s] = (media - mu) / max(sd, PISO[s])      # piso: base sem variacao nao pode dividir por ~zero
    fora = sum(abs(z) > 1.5 for z in zs.values())
    energia = (zs["comp"] + zs["excl"] + zs["emoji"] - zs["intervalo"]) / 4
    tensao = (zs["excl"] + zs["ret"]) / 2
    return fora, energia, tensao, zs


def estado_humor(agora=None):
    """{estado, alerta, energia, tensao, confianca}. Exige linha de base (>=30 msgs na faixa, 14+ dias) e 2 janelas de 3h seguidas com 3+ sinais fora."""
    agora = agora or time.time()
    vazio = {"estado": "sem linha de base", "alerta": False, "energia": 0.0, "tensao": 0.0, "confianca": 0.0}
    if not _ativo("sinais"):
        return {**vazio, "estado": "pausado"}
    with _db() as c:
        ini = c.execute("SELECT MIN(ts) FROM sinais").fetchone()[0]
        if not ini or agora - ini < 14 * 86400:
            return vazio
        w1 = _linhas(c, agora - 3 * 3600, agora + 1)
        w2 = _linhas(c, agora - 6 * 3600, agora - 3 * 3600)
        faixa = _faixa(datetime.fromtimestamp(agora).hour)
        hist = [l for l in _linhas(c, agora - 30 * 86400, agora - 6 * 3600) if _faixa(l[1]) == faixa]
    if len(hist) < 30 or len(w1) < 2:
        return vazio
    base = {}
    for i, s in enumerate(SINAIS):
        v = [l[2 + i] for l in hist]
        mu = sum(v) / len(v)
        base[s] = (mu, math.sqrt(sum((x - mu) ** 2 for x in v) / len(v)))
    f1, e1, t1, _ = _janela_fora(w1, base)
    f2 = _janela_fora(w2, base)[0] if len(w2) >= 2 else 0
    try:
        ativo = json.loads(ESTADO.read_text(encoding="utf-8")).get("alerta", False)
    except (OSError, ValueError):
        ativo = False
    # histerese: entra com 3+ sinais em 2 janelas; so sai quando cai para menos de 2 sinais fora
    alerta = (f1 >= 3 and f2 >= 3) or (ativo and f1 >= 2)
    PASTA.mkdir(parents=True, exist_ok=True)
    ESTADO.write_text(json.dumps({"alerta": alerta, "ts": agora}), encoding="utf-8")
    est = "diferente do normal" if alerta else "normal"
    return {"estado": est, "alerta": alerta, "energia": round(e1, 2), "tensao": round(t1, 2), "confianca": round(min(1.0, len(hist) / 120), 2)}


def dica_tom():
    """Trecho que o roteador acrescenta ao prompt do Jarvis. Vazio quando esta tudo normal (o caso comum)."""
    try:
        h = estado_humor()
    except Exception:
        return ""
    if not h["alerta"]:
        return ""
    return ("\n\nTOM AGORA (sinal discreto da Alma): o Dono parece diferente do habitual. Seja um pouco mais breve, calmo e acolhedor. "
            "NÃO pergunte como ele está, NÃO comente que percebeu algo, NÃO fale em humor ou emoção a menos que ele puxe o assunto.")


# ---------- 3) perfil para o clone futuro ----------

def atualizar_perfil(agora=None):
    agora = agora or time.time()
    with LOCK, _db() as c:
        c.execute("DELETE FROM sinais WHERE ts<?", (agora - RETENCAO_S,))
        for nome, dias in (("7d", 7), ("30d", 30), ("90d", 90)):
            ls = _linhas(c, agora - dias * 86400, agora + 1)
            if len(ls) < 5:
                continue
            m = {s: round(sum(l[2 + i] for l in ls) / len(ls), 2) for i, s in enumerate(SINAIS)}
            m["n"] = len(ls)
            m["horas_ativas"] = [h for h, _ in Counter(l[1] for l in ls).most_common(4)]
            c.execute("DELETE FROM estilo WHERE janela=?", (nome,))
            c.execute("INSERT INTO estilo VALUES(?,?,?)", (nome, agora, json.dumps(m)))
        ls = _linhas(c, agora - 90 * 86400, agora + 1)
        if len(ls) >= 30:
            por = defaultdict(list)
            for l in ls:
                por[_faixa(l[1])].append(l)
            curva = {str(f): {"n": len(v), "comp": round(sum(x[2] for x in v) / len(v), 1), "excl": round(sum(x[3] for x in v) / len(v), 2),
                              "intervalo": round(sum(x[7] for x in v) / len(v))} for f, v in por.items()}
            c.execute("DELETE FROM temperamento")
            c.execute("INSERT INTO temperamento VALUES(?,?)", (agora, json.dumps(curva)))


def registrar_exemplo(situacao, resposta, contexto_="neutro"):
    """'Como ele responderia a X': so com aprovacao dele. Segredo e crise nunca entram."""
    if not _ativo("exemplos") or any(SEGREDO.search(x or "") or CRISE.search(x or "") for x in (situacao, resposta)):
        return False
    with LOCK, _db() as c:
        c.execute("INSERT INTO exemplos(ts,situacao,resposta,contexto) VALUES(?,?,?,?)", (time.time(), situacao[:400], resposta[:600], contexto_))
    return True


def parecidos(situacao, k=3):
    a = set(_tokens(situacao))
    if not a:
        return []
    with _db() as c:
        rows = c.execute("SELECT situacao,resposta,contexto FROM exemplos WHERE aprovado=1").fetchall()
    pont = sorted(((len(a & set(_tokens(s))) / len(a | set(_tokens(s))), s, r, ctx) for s, r, ctx in rows), reverse=True)
    return [{"situacao": s, "resposta": r, "contexto": ctx, "similaridade": round(p, 2)} for p, s, r, ctx in pont[:k] if p > 0]


# ---------- painel: ver, corrigir, apagar, pausar ----------

def sabe():
    with _db() as c:
        n = lambda q: c.execute(q).fetchone()[0]  # noqa: E731
        est = {j: json.loads(x) for j, x in c.execute("SELECT janela,json FROM estilo")}
        temp = c.execute("SELECT json FROM temperamento").fetchone()
        out = {"consentimento": consentimento(), "sinais": n("SELECT COUNT(*) FROM sinais"), "exemplos": n("SELECT COUNT(*) FROM exemplos"),
               "rotulos_pendentes": n("SELECT COUNT(*) FROM rotulos WHERE tema_dono IS NULL"), "estilo": est,
               "temperamento": json.loads(temp[0]) if temp else {}, "humor": estado_humor()}
    try:
        linhas = [json.loads(l) for l in DIARIO.read_text(encoding="utf-8").splitlines()]
    except (OSError, ValueError):
        linhas = []
    out["diario"] = len(linhas)
    out["sem_tema_pct"] = round(100 * sum(1 for x in linhas if not x.get("tema")) / len(linhas)) if linhas else 0
    out["por_tema"] = dict(Counter(x.get("tema") or "sem tema" for x in linhas))
    return out


def apagar(escopo):
    """escopo: sinais | exemplos | rotulos | perfil | diario | tema:<nome> | tudo."""
    with LOCK:
        with _db() as c:
            if escopo in ("sinais", "tudo", "perfil"):
                c.execute("DELETE FROM sinais")
            if escopo in ("exemplos", "tudo"):
                c.execute("DELETE FROM exemplos")
            if escopo in ("rotulos", "tudo"):
                c.execute("DELETE FROM rotulos")
            if escopo in ("perfil", "tudo"):
                c.execute("DELETE FROM estilo")
                c.execute("DELETE FROM temperamento")
            c.execute("INSERT INTO correcoes VALUES(?,?,?,?)", (time.time(), "apagar", escopo, ""))
        try:
            if escopo in ("diario", "tudo"):
                DIARIO.write_text("", encoding="utf-8")
            elif escopo.startswith("tema:"):
                tema = escopo[5:]
                DIARIO.write_text("".join(l + "\n" for l in DIARIO.read_text(encoding="utf-8").splitlines() if json.loads(l).get("tema") != tema), encoding="utf-8")
        except (OSError, ValueError):
            pass
    return True


def resumo_semanal():
    """Texto curto para o Jarvis dar em audio: o que a Alma aprendeu na semana (so numeros, nada do que ele escreveu)."""
    s = sabe()
    e = s["estilo"].get("7d")
    partes = [f"{s['diario']} registros no diário, {s['sem_tema_pct']}% ainda sem tema", f"{s['rotulos_pendentes']} frases esperando você dar um tema"]
    if e:
        partes.append(f"nos últimos 7 dias, {e['n']} mensagens, de {e['comp']:.0f} palavras em média")
    return "Resumo da Alma: " + "; ".join(partes) + ". Você pode ver, corrigir ou apagar tudo em /alma."
