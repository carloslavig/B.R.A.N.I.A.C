# -*- coding: utf-8 -*-
"""Memoria local do Braniac (SQLite): guarda TUDO o que importa das conversas para nao se perder e para NAO precisar
perguntar de novo ao Claude (gasta tokens) o que ja foi respondido.

  mensagens      : todo o historico (o que a pessoa disse, o que o Jarvis respondeu, transcricoes de audio)
  conhecimento   : perguntas ja respondidas pelo Claude/Dono (cache; consultado ANTES de perguntar)
  decisoes       : o que o Claude decidiu para cada situacao (E enviar, I ignorar, A avisar, P perguntar ao Dono)
  fatos_contato  : o que se aprendeu sobre cada pessoa

Regra de ouro: antes de perguntar ao Claude, o Jarvis consulta o banco; depois que o Claude responde, o banco guarda.
Dado de WhatsApp fica SO aqui (pasta data, acesso restrito ao usuario do Windows); nunca vai para IA online.
"""
import re, sqlite3, threading, time, unicodedata
from .store import DATA

ARQ = DATA / "memoria.db"
_lock = threading.RLock()
_con = None
_con_arq = None

PARADAS = set("a o as os um uma uns umas de do da dos das em no na nos nas por para pra pro com sem e ou que se eu voce vc tu ele ela "
              "nao sim ja mais mas so tambem eh sao foi ser esta estao tem ter como qual quais quem onde quando isso isto esse essa "
              "aquele aquela meu minha seu sua nosso me te lhe ao aos".split())


def _norm(x):
    s = "".join(c for c in unicodedata.normalize("NFD", str(x).lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", s)).strip()


def _palavras(x):
    return {p for p in _norm(x).split() if p not in PARADAS and len(p) > 1}


def _db():
    """Conexao unica por arquivo (os testes trocam ARQ; cada arquivo ganha sua propria conexao)."""
    global _con, _con_arq
    with _lock:
        if _con is None or _con_arq != ARQ:
            DATA.mkdir(exist_ok=True)
            ARQ.parent.mkdir(parents=True, exist_ok=True)
            _con = sqlite3.connect(str(ARQ), check_same_thread=False)
            _con_arq = ARQ
            _con.executescript("""
                CREATE TABLE IF NOT EXISTS mensagens(id INTEGER PRIMARY KEY, contato TEXT, direcao TEXT, canal TEXT, texto TEXT, audio INTEGER DEFAULT 0, ts REAL);
                CREATE INDEX IF NOT EXISTS ix_msg ON mensagens(contato, ts);
                CREATE TABLE IF NOT EXISTS conhecimento(id INTEGER PRIMARY KEY, chave TEXT UNIQUE, pergunta TEXT, resposta TEXT, fonte TEXT,
                    contato TEXT, criado REAL, usos INTEGER DEFAULT 0, ultimo_uso REAL);
                CREATE TABLE IF NOT EXISTS decisoes(id INTEGER PRIMARY KEY, contato TEXT, entrada TEXT, entrada_norm TEXT, cod TEXT, texto TEXT, ts REAL, usos INTEGER DEFAULT 0);
                CREATE INDEX IF NOT EXISTS ix_dec ON decisoes(contato, entrada_norm);
                CREATE TABLE IF NOT EXISTS fatos_contato(id INTEGER PRIMARY KEY, contato TEXT, fato TEXT, fonte TEXT, ts REAL, UNIQUE(contato, fato));
                CREATE TABLE IF NOT EXISTS correcoes(id INTEGER PRIMARY KEY, errado TEXT, certo TEXT, ts REAL, UNIQUE(errado, certo));
            """)
        return _con


def _q(sql, args=()):
    with _lock:
        c = _db()
        cur = c.execute(sql, args)
        c.commit()
        return cur


# ---------- mensagens ----------

def registrar_msg(contato, direcao, texto, canal="whatsapp", audio=False, ts=None):
    """direcao: 'E' = a pessoa falou; 'C' = nos (Jarvis/Dono) falamos. Ignora duplicata recente (a mesma conversa e lida varias vezes)."""
    texto = (texto or "").strip()
    if not texto:
        return False
    agora = ts or time.time()
    ja = _q("SELECT 1 FROM mensagens WHERE contato=? AND direcao=? AND texto=? AND ts>? LIMIT 1",
            (contato, direcao, texto, agora - 6 * 3600)).fetchone()
    if ja:
        return False
    _q("INSERT INTO mensagens(contato,direcao,canal,texto,audio,ts) VALUES(?,?,?,?,?,?)", (contato, direcao, canal, texto, int(audio), agora))
    return True


def historico(contato, n=12):
    """Ultimas n mensagens da pessoa, da mais antiga para a mais nova: [(direcao, texto)]."""
    rows = _q("SELECT direcao, texto FROM mensagens WHERE contato=? ORDER BY ts DESC, id DESC LIMIT ?", (contato, n)).fetchall()
    return list(reversed(rows))


def mensagens_desde(contato, ts):
    """Textos que a PESSOA mandou (direcao 'E') depois de `ts`, em ordem: [(ts, texto)]."""
    return [(r[0], r[1]) for r in _q("SELECT ts, texto FROM mensagens WHERE contato=? AND direcao='E' AND ts>? ORDER BY ts, id", (contato, ts)).fetchall()]


# ---------- conhecimento (cache de perguntas ja respondidas) ----------

def _chave(pergunta):
    return " ".join(sorted(_palavras(pergunta)))


def guardar_resposta(pergunta, resposta, fonte="claude", contato=None):
    """Grava a resposta para nunca mais perguntar a mesma coisa."""
    k = _chave(pergunta)
    if not k or not (resposta or "").strip():
        return
    _q("INSERT INTO conhecimento(chave,pergunta,resposta,fonte,contato,criado,usos,ultimo_uso) VALUES(?,?,?,?,?,?,0,?) "
       "ON CONFLICT(chave) DO UPDATE SET resposta=excluded.resposta, fonte=excluded.fonte, pergunta=excluded.pergunta",
       (k, pergunta[:300], resposta.strip(), fonte, contato, time.time(), time.time()))


def buscar_resposta(pergunta, limiar=0.8):
    """Resposta ja conhecida para esta pergunta (igual ou muito parecida) ou None. Conta o uso."""
    alvo = _palavras(pergunta)
    if not alvo:
        return None
    melhor, melhor_s = None, 0.0
    for id_, ch, resp in _q("SELECT id, chave, resposta FROM conhecimento").fetchall():
        outro = set(ch.split())
        if not outro:
            continue
        s = len(alvo & outro) / len(alvo | outro)
        if s > melhor_s:
            melhor, melhor_s = (id_, resp), s
    if melhor and melhor_s >= limiar:
        _q("UPDATE conhecimento SET usos=usos+1, ultimo_uso=? WHERE id=?", (time.time(), melhor[0]))
        return melhor[1]
    return None


def esquecer(termo):
    """Apaga do conhecimento o que mencionar `termo` (se algo aprendido estiver errado). Devolve quantos apagou."""
    alvo = _norm(termo)
    n = 0
    for id_, ch, p, r in _q("SELECT id, chave, pergunta, resposta FROM conhecimento").fetchall():
        if alvo and (alvo in _norm(p) or alvo in _norm(r) or alvo in ch):
            _q("DELETE FROM conhecimento WHERE id=?", (id_,))
            n += 1
    return n


# ---------- decisoes do Claude (para nao perguntar de novo a mesma situacao) ----------

def registrar_decisao(contato, entrada, cod, texto=""):
    _q("INSERT INTO decisoes(contato,entrada,entrada_norm,cod,texto,ts) VALUES(?,?,?,?,?,?)",
       (contato, entrada[:300], _norm(entrada), cod, (texto or "")[:500], time.time()))


def decisao_repetida(contato, entrada, cods=("I",), dias=30):
    """Mesma pessoa mandando EXATAMENTE a mesma mensagem que o Claude ja decidiu ignorar (I): nao pergunta de novo.
    So reaproveita decisoes seguras (ignorar/avisar); nunca reaproveita uma RESPOSTA (E) para uma situacao nova."""
    n = _norm(entrada)
    if not n:
        return None
    ph = ",".join("?" * len(cods))
    row = _q(f"SELECT id, cod FROM decisoes WHERE contato=? AND entrada_norm=? AND cod IN ({ph}) AND ts>? ORDER BY ts DESC LIMIT 1",
             (contato, n, *cods, time.time() - dias * 86400)).fetchone()
    if row:
        _q("UPDATE decisoes SET usos=usos+1 WHERE id=?", (row[0],))
        return row[1]
    return None


# ---------- fatos sobre cada pessoa ----------

def aprender_fato(contato, fato, fonte="claude"):
    fato = (fato or "").strip()
    if fato:
        _q("INSERT OR IGNORE INTO fatos_contato(contato,fato,fonte,ts) VALUES(?,?,?,?)", (contato, fato[:300], fonte, time.time()))


def fatos(contato):
    return [r[0] for r in _q("SELECT fato FROM fatos_contato WHERE contato=? ORDER BY ts", (contato,)).fetchall()]


# ---------- ficha (o que o Claude recebe, em vez de ser perguntado de novo) ----------

def ficha(contato, n_msgs=6):
    """Resumo compacto da pessoa: fatos aprendidos, ultimas decisoes e ultimas mensagens. Vai junto quando o Jarvis fala com o Claude."""
    partes = []
    f = fatos(contato)
    if f:
        partes.append("FATOS: " + " | ".join(f[-6:]))
    dec = _q("SELECT cod, entrada, texto FROM decisoes WHERE contato=? ORDER BY ts DESC LIMIT 3", (contato,)).fetchall()
    if dec:
        partes.append("DECISOES RECENTES: " + " | ".join(f"{c} ({e[:40]!r}->{t[:50]!r})" for c, e, t in reversed(dec)))
    h = historico(contato, n_msgs)
    if h:
        partes.append("ULTIMAS MENSAGENS: " + " ¦ ".join(("ELE: " if d == "E" else "NOS: ") + t[:90] for d, t in h))
    return "\n".join(partes)


def corrigir(errado, certo):
    """Conselho 15/10: o Dono corrige o Jarvis uma vez e a correção volta como exemplo sempre que o assunto reaparecer."""
    errado, certo = (errado or "").strip()[:300], (certo or "").strip()[:300]
    if errado and certo:
        _q("INSERT OR REPLACE INTO correcoes(errado,certo,ts) VALUES(?,?,?)", (errado, certo, time.time()))
    return bool(errado and certo)


def correcoes_parecidas(texto, n=3):
    """As correções cujo 'errado' compartilha palavras com o texto (ao menos 2, ou todas se forem poucas), mais recentes primeiro."""
    pal = _palavras(texto)
    ach = []
    for e, c, ts in _q("SELECT errado, certo, ts FROM correcoes ORDER BY ts DESC LIMIT 200").fetchall():
        pe = _palavras(e)
        if pe and len(pe & pal) >= min(2, len(pe)):
            ach.append(f"{e} -> {c}")
    return ach[:n]


def contexto_para_decidir(contato, entrada, n=6):
    """Bloco para o Claude de fundo decidir sem perguntar: ficha da pessoa + respostas ja conhecidas relevantes."""
    blocos = [ficha(contato, n)]
    conhecida = buscar_resposta(entrada, limiar=0.5)
    if conhecida:
        blocos.append("JA RESPONDIDO ANTES (consistencia): " + conhecida[:300])
    try:
        from . import claudinho
        blocos.append("REGRAS DO CLAUDINHO (gerente; obedeca): " + " | ".join(claudinho.guia().replace("- ", "").splitlines()))
    except Exception:
        pass
    cor = correcoes_parecidas(entrada)
    if cor:
        blocos.append("CORRECOES DO DONO (obedeca): " + " | ".join(cor))
    return "\n".join(b for b in blocos if b)


def resumo():
    c = lambda t: _q(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    return {"mensagens": c("mensagens"), "conhecimento": c("conhecimento"), "decisoes": c("decisoes"), "fatos": c("fatos_contato")}


def apagar_decisoes(contato, cod=None):
    """Remove decisoes antigas de uma pessoa (ex.: uma decisao errada que nao deve virar regra). Devolve quantas apagou."""
    if cod:
        cur = _q("DELETE FROM decisoes WHERE contato=? AND cod=?", (contato, cod))
    else:
        cur = _q("DELETE FROM decisoes WHERE contato=?", (contato,))
    return cur.rowcount


def saidas_recentes(contato, horas=24):
    """O que NOS dissemos a esta pessoa nas ultimas horas (para nao repetir)."""
    rows = _q("SELECT texto FROM mensagens WHERE contato=? AND direcao='C' AND ts>? ORDER BY ts", (contato, time.time() - horas * 3600)).fetchall()
    return [r[0] for r in rows]


def resumo_periodo(horas=24, max_contatos=12, max_linhas=3):
    """Resumo REAL (do banco local) do que rolou no WhatsApp nas ultimas horas: por conversa, quantas mensagens e as ultimas falas.
    Tudo local: nao passa por IA, entao nada e inventado e nada do WhatsApp sai do PC."""
    desde = time.time() - horas * 3600
    rows = _q("SELECT contato, direcao, texto, audio, ts FROM mensagens WHERE ts>? ORDER BY ts", (desde,)).fetchall()
    if not rows:
        return f"Não há nada registrado no WhatsApp nas últimas {horas:g} h."
    por = {}
    for c, d, t, a, ts in rows:
        por.setdefault(c, []).append((d, t, a, ts))
    ordem = sorted(por, key=lambda c: por[c][-1][3], reverse=True)[:max_contatos]
    out = [f"WhatsApp nas últimas {horas:g} h: {len(rows)} mensagens em {len(por)} conversas."]
    for c in ordem:
        ms = por[c]
        eles = sum(1 for m in ms if m[0] == "E")
        out.append(f"\n• {c}: {eles} recebida(s), {len(ms) - eles} enviada(s)")
        for d, t, a, ts in ms[-max_linhas:]:
            quem = "ela/ele" if d == "E" else "nós"
            out.append(f"   {time.strftime('%H:%M', time.localtime(ts))} {quem}: {' '.join(t.split())[:140]}{' 🎙' if a else ''}")
    if len(por) > max_contatos:
        out.append(f"\n(+ {len(por) - max_contatos} conversas menos recentes)")
    return "\n".join(out)


def ja_falamos(contato):
    """True se o Jarvis/Dono ja mandou alguma mensagem a esta pessoa (senao e contato NOVO)."""
    return _q("SELECT 1 FROM mensagens WHERE contato=? AND direcao='C' LIMIT 1", (contato,)).fetchone() is not None
