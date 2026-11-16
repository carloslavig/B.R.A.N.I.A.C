# -*- coding: utf-8 -*-
"""BRAIN CENTER (07/11/2026): memoria central do Braniac que se consolida quando a MAIORIA dos agentes esta ociosa.
Modulos logicos (nao sao agentes): memoria de trabalho, episodica, semantica, associacao, consolidacao e recuperacao.
- Disponibilidade coletiva: % de agentes ociosos entre os DISPONIVEIS (sauraki.snapshot), sustentada por `sustentado_s`; recursos (CPU/RAM/GPU) sao 2a trava.
- Nada e apagado: episodios originais ficam; memoria velha vira 'arquivada'; contradicao fica aberta ate alguem resolver.
- So le/escreve em data/braincenter.db; nao chama agente, nao envia mensagem, nao usa internet. Config: data/braincenter/config.json (sobrepoe PADRAO)."""
import hashlib
import json
import math
import re
import sqlite3
import threading
import time
import unicodedata

from .store import DATA

PADRAO = {
    "limite_ociosidade_pct": 85.0,      # >= limite autoriza (inclusivo)
    "sustentado_s": 300,                # tempo minimo mantendo o limite antes de iniciar
    "ignorar_agentes": ["BrainCenter", "Brain Center"],
    "estados_trabalhando": ["analisando", "planejando", "executando", "consultando"],
    "estados_ociosos": ["ocioso", "concluido", "aguardando_autorizacao", "aguardando_servico"],
    "estados_indisponiveis": ["desconectado", "erro"],     # estado None (sem dado) tambem e indisponivel
    "cpu_max_pct": 70, "ram_max_pct": 85, "gpu_max_c": 80,
    "lote": 200, "max_lotes_por_tick": 3,
    "similaridade_duplicata": 0.85, "similaridade_conflito": 0.6,
    "arquivar_apos_dias": 90, "arquivar_score_abaixo": 0.25, "importante_a_partir_de": 0.8,
    "meia_vida_dias": 30,
    "pesos": {"frequencia": 0.2, "recencia": 0.2, "projeto_ativo": 0.15, "importancia": 0.25, "confianca": 0.1, "repeticao": 0.1},
    "confianca_fonte": {"dono": 1.0, "dossie": 0.9, "usuario": 1.0, "jarvis": 0.6, "agente": 0.6, "ia": 0.5, "desconhecida": 0.4},
    "projetos_ativos": ["global"],
    "permissoes": {"*": {"projetos": ["global"]}},   # agente -> {"projetos": [...] ou ["*"]}
}
ESTADOS = ("MONITORANDO", "AGUARDANDO OCIOSIDADE", "OCIOSIDADE COLETIVA ATINGIDA", "CONSOLIDANDO", "PAUSADO POR DEMANDA",
           "PAUSADO POR RECURSOS", "CONCLUÍDO", "ERRO")
PARADAS = set("de da do das dos e o a os as um uma que para por com em no na nos nas se ao the is of to and".split())
NEGA = {"nao", "nunca", "sem", "jamais"}
_lock = threading.Lock()
_est = {"desde": None, "estado": "MONITORANDO", "motivo": "ainda não avaliado", "medicao": None, "recursos": None}


def config():
    try:
        extra = json.loads((DATA / "braincenter" / "config.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        extra = {}
    c = {**PADRAO, **{k: v for k, v in extra.items() if k in PADRAO}}
    c["pesos"] = {**PADRAO["pesos"], **(extra.get("pesos") or {})}
    return c


def _norm(x):
    s = "".join(c for c in unicodedata.normalize("NFD", str(x).lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", s)).strip()


def _pal(x):
    return {w for w in _norm(x).split() if (len(w) > 2 or w.isdigit()) and w not in PARADAS}


def _jac(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


# ---------- banco ----------
def _db():
    d = DATA / "braincenter.db"
    d.parent.mkdir(exist_ok=True)
    c = sqlite3.connect(str(d), timeout=15)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript("""
    CREATE TABLE IF NOT EXISTS trabalho(id INTEGER PRIMARY KEY, agente TEXT, contexto TEXT, conteudo TEXT, ts REAL, expira REAL, UNIQUE(agente,contexto));
    CREATE TABLE IF NOT EXISTS episodica(id INTEGER PRIMARY KEY, origem TEXT UNIQUE, ts REAL, agente TEXT, projeto TEXT DEFAULT 'global', assunto TEXT DEFAULT 'geral',
        tipo TEXT DEFAULT 'evento', chave TEXT, texto TEXT, privado INTEGER DEFAULT 0, importancia REAL DEFAULT 0.5, fonte TEXT DEFAULT 'agente', consolidado INTEGER DEFAULT 0);
    CREATE INDEX IF NOT EXISTS ep_cons ON episodica(consolidado,id);
    CREATE TABLE IF NOT EXISTS semantica(id INTEGER PRIMARY KEY, projeto TEXT, assunto TEXT, chave TEXT, texto TEXT, tipo TEXT DEFAULT 'fato', confianca REAL, importancia REAL DEFAULT 0.5,
        estado TEXT DEFAULT 'ativa', privado INTEGER DEFAULT 0, dono TEXT, agente_origem TEXT, uso INTEGER DEFAULT 0, n_fontes INTEGER DEFAULT 1, criado REAL, atualizado REAL, ultimo_uso REAL,
        score REAL DEFAULT 0, norm TEXT);
    CREATE INDEX IF NOT EXISTS se_chave ON semantica(projeto,assunto,chave);
    CREATE TABLE IF NOT EXISTS historico(id INTEGER PRIMARY KEY, sem_id INTEGER, texto_anterior TEXT, ts REAL, motivo TEXT);
    CREATE TABLE IF NOT EXISTS origem(sem_id INTEGER, ep_id INTEGER, UNIQUE(sem_id,ep_id));
    CREATE TABLE IF NOT EXISTS conflitos(id INTEGER PRIMARY KEY, sem_a INTEGER, sem_b INTEGER, motivo TEXT, aberto INTEGER DEFAULT 1, ts REAL, UNIQUE(sem_a,sem_b));
    CREATE TABLE IF NOT EXISTS associacoes(a INTEGER, b INTEGER, peso REAL, UNIQUE(a,b));
    CREATE TABLE IF NOT EXISTS indice(palavra TEXT, sem_id INTEGER, UNIQUE(palavra,sem_id));
    CREATE INDEX IF NOT EXISTS ix_p ON indice(palavra);
    CREATE TABLE IF NOT EXISTS ciclos(id INTEGER PRIMARY KEY, inicio REAL, fim REAL, estado TEXT, lotes INTEGER DEFAULT 0, novos INTEGER DEFAULT 0, criadas INTEGER DEFAULT 0,
        atualizadas INTEGER DEFAULT 0, duplicadas INTEGER DEFAULT 0, conflitos INTEGER DEFAULT 0, arquivadas INTEGER DEFAULT 0, erro TEXT, duracao_s REAL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
    """)
    return c


def _meta(c, k, padrao=None):
    r = c.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
    return r[0] if r else padrao


def _setmeta(c, k, v):
    c.execute("INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, str(v)))


# ---------- memoria de trabalho ----------
def trabalho_set(agente, contexto, conteudo, ttl_s=3600):
    with _db() as c:
        c.execute("INSERT INTO trabalho(agente,contexto,conteudo,ts,expira) VALUES(?,?,?,?,?) ON CONFLICT(agente,contexto) DO UPDATE SET conteudo=excluded.conteudo,ts=excluded.ts,expira=excluded.expira",
                  (agente, contexto, str(conteudo)[:4000], time.time(), time.time() + ttl_s))


def trabalho_get(agente, contexto):
    with _db() as c:
        r = c.execute("SELECT conteudo FROM trabalho WHERE agente=? AND contexto=? AND expira>?", (agente, contexto, time.time())).fetchone()
        return r[0] if r else None


# ---------- memoria episodica ----------
def registrar(agente, texto, projeto="global", assunto="geral", tipo="evento", chave=None, privado=False, importancia=0.5, fonte="agente", origem=None):
    """Grava um episodio (nunca e apagado nem alterado). `origem` unica evita duplicar reenvios."""
    texto = (texto or "").strip()
    if not texto:
        return False
    origem = origem or hashlib.sha1(f"{agente}|{projeto}|{assunto}|{chave}|{texto}".encode()).hexdigest()
    try:
        with _db() as c:
            c.execute("INSERT INTO episodica(origem,ts,agente,projeto,assunto,tipo,chave,texto,privado,importancia,fonte) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                      (origem, time.time(), agente, projeto, assunto, tipo, chave, texto[:2000], int(bool(privado)), importancia, fonte))
        return True
    except sqlite3.IntegrityError:
        return False


def ingerir():
    """Traz o que ja existe (fatos do banco unificado) como episodios, de forma incremental. Fato 'local' entra PRIVADO."""
    try:
        from . import banco
        ult = float(_meta(c := _db(), "ing_fatos_ts", "0"))
        linhas = banco._q("SELECT escopo,chave,texto,nivel,fonte,ts FROM fatos WHERE ts>? AND (validade IS NULL OR validade>?) ORDER BY ts LIMIT 500", (ult, time.time())).fetchall()
    except Exception:
        return 0
    n = 0
    for escopo, chave, texto, nivel, fonte, ts in linhas:
        f = (fonte or "desconhecida").lower()
        n += registrar(fonte or "banco", texto, "global", escopo or "geral", "fato", chave, privado=(nivel != "publico"),
                       fonte="dossie" if "dossie" in f else "dono" if "dono" in f else "jarvis" if "jarvis" in f else "desconhecida",
                       origem=f"fato:{escopo}:{chave}:{int(ts or 0)}")
    if linhas:
        with c:
            _setmeta(c, "ing_fatos_ts", max(l[5] or 0 for l in linhas))
    c.close()
    return n


# ---------- disponibilidade coletiva ----------
def medir(agentes, cfg=None):
    """Funcao pura. agentes = lista de {'nome','estado'}. Indisponivel (desconectado/erro/sem dado) fica fora e nao conta como ocioso."""
    cfg = cfg or config()
    ign = {_norm(x) for x in cfg["ignorar_agentes"]}
    tr = oc = ind = 0
    for a in agentes:
        if _norm(a.get("nome", "")) in ign:
            continue
        e = a.get("estado")
        if e is None or e in cfg["estados_indisponiveis"]:
            ind += 1
        elif e in cfg["estados_trabalhando"]:
            tr += 1
        elif e in cfg["estados_ociosos"]:
            oc += 1
        else:
            ind += 1
    disp = tr + oc
    return {"total": tr + oc + ind, "disponiveis": disp, "trabalhando": tr, "ociosos": oc, "indisponiveis": ind,
            "pct_ociosos": round(100.0 * oc / disp, 1) if disp else 0.0}


def recursos_ok(cfg=None, leitura=None):
    """(ok, motivo, dados). Sem leitura disponivel nao bloqueia, mas diz isso."""
    cfg = cfg or config()
    r = leitura
    if r is None:
        try:
            from . import termico
            r = termico.atual()
        except Exception:
            r = {}
    if not r or r.get("pronto") is False:
        return True, "sem leitura de recursos (liberado)", {}
    d = {k: r.get(k) for k in ("cpu_pct", "ram_pct", "gpu_c")}
    if (d["cpu_pct"] or 0) > cfg["cpu_max_pct"]:
        return False, f"CPU em {d['cpu_pct']}% (máx {cfg['cpu_max_pct']}%)", d
    if (d["ram_pct"] or 0) > cfg["ram_max_pct"]:
        return False, f"RAM em {d['ram_pct']}% (máx {cfg['ram_max_pct']}%)", d
    if (d["gpu_c"] or 0) > cfg["gpu_max_c"]:
        return False, f"GPU a {d['gpu_c']} °C (máx {cfg['gpu_max_c']} °C)", d
    return True, "recursos dentro dos limites", d


def avaliar(agentes, agora=None, cfg=None, leitura=None, em_ciclo=False):
    """Maquina de estados da disponibilidade coletiva. Devolve (autorizado, estado, motivo, medicao)."""
    cfg, agora = cfg or config(), agora or time.time()
    m = medir(agentes, cfg)
    rok, rmot, rdados = recursos_ok(cfg, leitura)
    _est["medicao"], _est["recursos"] = m, rdados
    atingiu = m["disponiveis"] > 0 and m["pct_ociosos"] >= cfg["limite_ociosidade_pct"]
    if not atingiu:
        _est["desde"] = None
        est = "PAUSADO POR DEMANDA" if em_ciclo else "AGUARDANDO OCIOSIDADE"
        mot = f"{m['pct_ociosos']}% ociosos de {m['disponiveis']} disponíveis (precisa {cfg['limite_ociosidade_pct']}%)"
        return _fin(False, est, mot, m)
    if _est["desde"] is None:
        _est["desde"] = agora
    falta = cfg["sustentado_s"] - (agora - _est["desde"])
    if falta > 0 and not em_ciclo:
        return _fin(False, "OCIOSIDADE COLETIVA ATINGIDA", f"{m['pct_ociosos']}% ociosos; aguardando {int(falta)} s sustentados", m)
    if not rok:
        return _fin(False, "PAUSADO POR RECURSOS", rmot, m)
    return _fin(True, "CONSOLIDANDO", f"{m['pct_ociosos']}% ociosos e {rmot}", m)


def _fin(ok, est, mot, m):
    _est["estado"], _est["motivo"] = est, mot
    return ok, est, mot, m


# ---------- consolidacao ----------
def _tipo(texto):
    t = _norm(texto)
    if re.search(r"\b(so hoje|hoje|agora|temporari\w*|neste momento|por enquanto|amanha)\b", t):
        return "temporario"
    if re.search(r"\b(acho|talvez|provavelmente|parece|suponho|possivelmente|hipotese)\b", t):
        return "hipotese"
    if re.search(r"\b(prefiro|gosto|na minha opiniao|opiniao|detesto|adoro)\b", t):
        return "opiniao"
    return "fato"


def pontuar(m, agora, cfg):
    """Score 0..1 (nao e verdade: confianca vem da FONTE). uso e repeticao so contam com teto."""
    p = cfg["pesos"]
    dias = max(0.0, (agora - (m["ultimo_uso"] or m["atualizado"] or agora)) / 86400)
    rec = math.exp(-math.log(2) * dias / cfg["meia_vida_dias"])
    freq = min(1.0, math.log1p(m["uso"] or 0) / math.log(11))
    rep = min(1.0, ((m["n_fontes"] or 1) - 1) / 4)
    proj = 1.0 if m["projeto"] in cfg["projetos_ativos"] else 0.0
    s = p["frequencia"] * freq + p["recencia"] * rec + p["projeto_ativo"] * proj + p["importancia"] * (m["importancia"] or 0) + p["confianca"] * (m["confianca"] or 0) + p["repeticao"] * rep
    return round(s / sum(p.values()), 4)


def _indexar(c, sid, texto):
    c.execute("DELETE FROM indice WHERE sem_id=?", (sid,))
    c.executemany("INSERT OR IGNORE INTO indice(palavra,sem_id) VALUES(?,?)", [(w, sid) for w in _pal(texto)])


def _associar(c, sid, projeto, texto, cfg):
    pal = _pal(texto)
    if not pal:
        return
    cand = {r[0] for w in pal for r in c.execute("SELECT sem_id FROM indice WHERE palavra=?", (w,)).fetchall()} - {sid}
    pontos = []
    for o in cand:
        r = c.execute("SELECT texto,projeto FROM semantica WHERE id=? AND estado!='arquivada'", (o,)).fetchone()
        if r and r["projeto"] == projeto:          # associacao nunca cruza projetos
            j = _jac(pal, _pal(r["texto"]))
            if j >= 0.25:
                pontos.append((j, o))
    for j, o in sorted(pontos, reverse=True)[:5]:
        a, b = sorted((sid, o))
        c.execute("INSERT INTO associacoes(a,b,peso) VALUES(?,?,?) ON CONFLICT(a,b) DO UPDATE SET peso=excluded.peso", (a, b, round(j, 3)))


def _consolidar_episodio(c, ep, cfg, st):
    tipo = _tipo(ep["texto"])
    if tipo == "temporario":
        st["temporarios"] = st.get("temporarios", 0) + 1       # fica so no episodico; nao vira conhecimento estavel
        return
    norm = _norm(ep["texto"])
    pal = _pal(ep["texto"])
    chave = _norm(ep["chave"]) if ep["chave"] else None
    projeto, assunto = ep["projeto"], ep["assunto"]
    conf = cfg["confianca_fonte"].get(ep["fonte"], cfg["confianca_fonte"]["desconhecida"])
    dono = ep["agente"] if ep["privado"] else None
    linhas = c.execute("SELECT * FROM semantica WHERE projeto=? AND assunto=? AND estado!='arquivada' AND IFNULL(dono,'')=IFNULL(?,'')", (projeto, assunto, dono)).fetchall()
    for m in linhas:                                   # 1) duplicata
        if m["norm"] == norm or not (chave and m["chave"] == chave) and _jac(pal, _pal(m["texto"])) >= cfg["similaridade_duplicata"] and bool(NEGA & set(norm.split())) == bool(NEGA & set(m["norm"].split())):
            c.execute("INSERT OR IGNORE INTO origem(sem_id,ep_id) VALUES(?,?)", (m["id"], ep["id"]))
            n = c.execute("SELECT COUNT(DISTINCT e.agente) FROM origem o JOIN episodica e ON e.id=o.ep_id WHERE o.sem_id=?", (m["id"],)).fetchone()[0]
            c.execute("UPDATE semantica SET n_fontes=?, atualizado=? WHERE id=?", (n, time.time(), m["id"]))
            st["duplicadas"] += 1
            return
    mesma = [m for m in linhas if chave and m["chave"] == chave]
    if mesma:                                           # 2) mesma chave, texto diferente: atualizacao ou conflito
        m = mesma[0]
        if m["agente_origem"] == ep["agente"] and (m["importancia"] or 0) < cfg["importante_a_partir_de"] and m["estado"] == "ativa":
            c.execute("INSERT INTO historico(sem_id,texto_anterior,ts,motivo) VALUES(?,?,?,?)", (m["id"], m["texto"], time.time(), f"atualizado por {ep['agente']}"))
            c.execute("UPDATE semantica SET texto=?,norm=?,tipo=?,confianca=?,atualizado=? WHERE id=?", (ep["texto"], norm, tipo, max(conf, m["confianca"] or 0), time.time(), m["id"]))
            c.execute("INSERT OR IGNORE INTO origem(sem_id,ep_id) VALUES(?,?)", (m["id"], ep["id"]))
            _indexar(c, m["id"], ep["texto"])
            _associar(c, m["id"], projeto, ep["texto"], cfg)
            st["atualizadas"] += 1
            return
        novo = _criar(c, ep, tipo, norm, chave, conf, dono, "conflito")
        c.execute("UPDATE semantica SET estado='conflito' WHERE id=?", (m["id"],))
        c.execute("INSERT OR IGNORE INTO conflitos(sem_a,sem_b,motivo,ts) VALUES(?,?,?,?)", (m["id"], novo, "mesma chave, texto diferente, outra origem ou memória importante", time.time()))
        st["conflitos"] += 1
        return
    for m in linhas:                                    # 3) contradicao por negacao em texto muito parecido
        if _jac(pal, _pal(m["texto"])) >= cfg["similaridade_conflito"] and bool(NEGA & set(norm.split())) != bool(NEGA & set(m["norm"].split())):
            novo = _criar(c, ep, tipo, norm, chave, conf, dono, "conflito")
            c.execute("UPDATE semantica SET estado='conflito' WHERE id=?", (m["id"],))
            c.execute("INSERT OR IGNORE INTO conflitos(sem_a,sem_b,motivo,ts) VALUES(?,?,?,?)", (m["id"], novo, "afirmação e negação sobre o mesmo assunto", time.time()))
            st["conflitos"] += 1
            return
    _criar(c, ep, tipo, norm, chave, conf, dono, "ativa")
    st["criadas"] += 1


def _criar(c, ep, tipo, norm, chave, conf, dono, estado):
    agora = time.time()
    cur = c.execute("INSERT INTO semantica(projeto,assunto,chave,texto,tipo,confianca,importancia,estado,privado,dono,agente_origem,criado,atualizado,norm) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (ep["projeto"], ep["assunto"], chave, ep["texto"], tipo, conf, ep["importancia"], estado, ep["privado"], dono, ep["agente"], agora, agora, norm))
    sid = cur.lastrowid
    c.execute("INSERT INTO origem(sem_id,ep_id) VALUES(?,?)", (sid, ep["id"]))
    _indexar(c, sid, ep["texto"])
    _associar(c, sid, ep["projeto"], ep["texto"], config())
    return sid


def _arquivar(c, cfg, agora):
    n = 0
    for m in c.execute("SELECT * FROM semantica WHERE estado='ativa'").fetchall():
        s = pontuar(m, agora, cfg)
        arq = (agora - (m["atualizado"] or agora)) / 86400 >= cfg["arquivar_apos_dias"] and s < cfg["arquivar_score_abaixo"] and (m["importancia"] or 0) < cfg["importante_a_partir_de"]
        c.execute("UPDATE semantica SET score=?, estado=? WHERE id=?", (s, "arquivada" if arq else "ativa", m["id"]))
        n += arq
    return n


def consolidar(avaliador=None, cfg=None):
    """Roda ate `max_lotes_por_tick` lotes. `avaliador()` -> bool (continua autorizado?) e checado ENTRE lotes: se cair, para no checkpoint.
    O checkpoint (ultimo episodio consolidado) vive no banco: o proximo ciclo retoma dali. Nao permite 2 ciclos juntos."""
    cfg = cfg or config()
    if not _lock.acquire(blocking=False):
        return {"estado": "ja_rodando"}
    c = None
    try:
        c = _db()
        ativo = _meta(c, "ciclo_ativo")
        if ativo and time.time() - float(ativo) < 600:
            return {"estado": "ja_rodando"}
        with c:
            _setmeta(c, "ciclo_ativo", time.time())
        ing = ingerir()
        rid = _meta(c, "ciclo_aberto")
        if not rid or not c.execute("SELECT 1 FROM ciclos WHERE id=? AND estado='pausado'", (rid,)).fetchone():
            with c:
                rid = c.execute("INSERT INTO ciclos(inicio,estado) VALUES(?,?)", (time.time(), "consolidando")).lastrowid
                _setmeta(c, "ciclo_aberto", rid)
        else:
            c.execute("UPDATE ciclos SET estado='consolidando' WHERE id=?", (rid,))
            c.commit()
        t0 = time.time()
        st = {"criadas": 0, "atualizadas": 0, "duplicadas": 0, "conflitos": 0, "novos": ing}
        lotes, estado = 0, "concluido"
        while lotes < cfg["max_lotes_por_tick"]:
            if avaliador and lotes and not avaliador():
                estado = "pausado"
                break
            pend = c.execute("SELECT * FROM episodica WHERE consolidado=0 ORDER BY id LIMIT ?", (cfg["lote"],)).fetchall()
            if not pend:
                break
            with c:                                           # 1 transacao por lote: falha = nada do lote e aplicado
                for ep in pend:
                    _consolidar_episodio(c, ep, cfg, st)
                c.executemany("UPDATE episodica SET consolidado=1 WHERE id=?", [(e["id"],) for e in pend])
                _setmeta(c, "checkpoint", pend[-1]["id"])
            lotes += 1
            st["novos"] += len(pend)
        else:
            estado = "pausado" if c.execute("SELECT 1 FROM episodica WHERE consolidado=0 LIMIT 1").fetchone() else "concluido"
        arq = 0
        if estado == "concluido":
            with c:
                arq = _arquivar(c, cfg, time.time())
        with c:
            c.execute("UPDATE ciclos SET fim=?,estado=?,lotes=lotes+?,novos=novos+?,criadas=criadas+?,atualizadas=atualizadas+?,duplicadas=duplicadas+?,conflitos=conflitos+?,arquivadas=arquivadas+?,duracao_s=duracao_s+? WHERE id=?",
                      (time.time(), estado, lotes, st["novos"], st["criadas"], st["atualizadas"], st["duplicadas"], st["conflitos"], arq, round(time.time() - t0, 2), rid))
            if estado == "concluido":
                _setmeta(c, "ciclo_aberto", "")
        _est["estado"] = "CONCLUÍDO" if estado == "concluido" else "PAUSADO POR DEMANDA"
        return {"estado": estado, "lotes": lotes, **st, "arquivadas": arq}
    except Exception as e:
        try:
            if c:
                with c:
                    c.execute("INSERT INTO ciclos(inicio,fim,estado,erro) VALUES(?,?,?,?)", (time.time(), time.time(), "erro", str(e)[:300]))
        except Exception:
            pass
        _est["estado"], _est["motivo"] = "ERRO", str(e)[:200]
        return {"estado": "erro", "erro": str(e)[:200]}
    finally:
        try:
            if c:
                with c:
                    _setmeta(c, "ciclo_ativo", "")
                c.close()
        except Exception:
            pass
        _lock.release()


# ---------- recuperacao ----------
def permitido(agente, projeto, cfg=None):
    cfg = cfg or config()
    p = cfg["permissoes"].get(agente) or cfg["permissoes"].get("*") or {}
    lista = p.get("projetos", [])
    return "*" in lista or projeto in lista or projeto == "global"


def consultar(agente, texto, projeto="global", n=5):
    """Memorias relevantes. Privadas so ao dono; projeto sem permissao e recusado; conflito aparece marcado; arquivadas so se nada mais acha."""
    if not permitido(agente, projeto):
        return []
    pal = _pal(texto)
    if not pal:
        return []
    c = _db()
    cand = {}
    for w in pal:
        for r in c.execute("SELECT sem_id FROM indice WHERE palavra=?", (w,)).fetchall():
            cand[r[0]] = cand.get(r[0], 0) + 1
    out = []
    for sid, hit in cand.items():
        m = c.execute("SELECT * FROM semantica WHERE id=?", (sid,)).fetchone()
        if not m or m["projeto"] not in (projeto, "global") or (m["privado"] and m["dono"] != agente):
            continue
        rel = hit / len(pal)
        out.append((rel * 0.6 + (m["score"] or 0) * 0.2 + (m["confianca"] or 0) * 0.2 - (0.3 if m["estado"] == "arquivada" else 0), m))
    out.sort(key=lambda x: -x[0])
    res = []
    with c:
        for _, m in out[:n]:
            c.execute("UPDATE semantica SET uso=uso+1, ultimo_uso=? WHERE id=?", (time.time(), m["id"]))
            res.append({"id": m["id"], "texto": m["texto"], "tipo": m["tipo"], "estado": m["estado"], "assunto": m["assunto"], "projeto": m["projeto"],
                        "confianca": m["confianca"], "origem": m["agente_origem"], "conflito": m["estado"] == "conflito"})
    c.close()
    return res


def resolver_conflito(conflito_id, manter_sem_id, quem="dono"):
    """So uma pessoa valida: mantem uma memoria, arquiva a outra (preservada) e fecha o conflito."""
    with _db() as c:
        r = c.execute("SELECT * FROM conflitos WHERE id=? AND aberto=1", (conflito_id,)).fetchone()
        if not r or manter_sem_id not in (r["sem_a"], r["sem_b"]):
            return False
        outro = r["sem_b"] if manter_sem_id == r["sem_a"] else r["sem_a"]
        c.execute("UPDATE semantica SET estado='ativa' WHERE id=?", (manter_sem_id,))
        c.execute("UPDATE semantica SET estado='arquivada' WHERE id=?", (outro,))
        c.execute("INSERT INTO historico(sem_id,texto_anterior,ts,motivo) VALUES(?,?,?,?)", (outro, "(arquivada ao resolver conflito)", time.time(), f"resolvido por {quem}"))
        c.execute("UPDATE conflitos SET aberto=0 WHERE id=?", (conflito_id,))
    return True


# ---------- orquestracao e painel ----------
def tick(agentes=None, agora=None, em_thread=True):
    """Chamado pela rotina. Barato quando nao autorizado. Roda a consolidacao numa thread para nunca travar o ciclo."""
    cfg = config()
    try:
        if agentes is None:
            from . import sauraki
            agentes = sauraki.snapshot()["agentes"]
        ok, est, mot, m = avaliar(agentes, agora, cfg)
    except Exception as e:
        _est["estado"], _est["motivo"] = "ERRO", str(e)[:200]
        return _est["estado"]
    if not ok:
        return est

    def _rodar():
        def ainda():
            try:
                from . import sauraki
                return avaliar(sauraki.snapshot()["agentes"], None, cfg, em_ciclo=True)[0]
            except Exception:
                return False
        consolidar(ainda, cfg)
    if em_thread:
        threading.Thread(target=_rodar, daemon=True).start()
    else:
        _rodar()
    return est


def painel():
    cfg = config()
    c = _db()
    try:
        q = lambda s, a=(): c.execute(s, a).fetchone()[0]
        ult = c.execute("SELECT * FROM ciclos WHERE estado IN ('concluido','pausado','erro') ORDER BY id DESC LIMIT 1").fetchone()
        hist = [dict(r) for r in c.execute("SELECT id,inicio,fim,estado,lotes,novos,criadas,atualizadas,duplicadas,conflitos,arquivadas,duracao_s,erro FROM ciclos ORDER BY id DESC LIMIT 10")]
        return {"estado": _est["estado"], "motivo": _est["motivo"], "medicao": _est["medicao"], "recursos": _est["recursos"],
                "limite_pct": cfg["limite_ociosidade_pct"], "sustentado_s": cfg["sustentado_s"],
                "pendentes": q("SELECT COUNT(*) FROM episodica WHERE consolidado=0"), "episodios": q("SELECT COUNT(*) FROM episodica"),
                "memorias": q("SELECT COUNT(*) FROM semantica WHERE estado!='arquivada'"), "arquivadas": q("SELECT COUNT(*) FROM semantica WHERE estado='arquivada'"),
                "conflitos_abertos": q("SELECT COUNT(*) FROM conflitos WHERE aberto=1"), "associacoes": q("SELECT COUNT(*) FROM associacoes"),
                "trabalho": q("SELECT COUNT(*) FROM trabalho WHERE expira>?", (time.time(),)),
                "ultima_consolidacao": ult["fim"] if ult else None, "ultimo_tempo_s": ult["duracao_s"] if ult else None, "historico": hist}
    finally:
        c.close()
