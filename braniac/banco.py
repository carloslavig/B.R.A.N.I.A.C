# -*- coding: utf-8 -*-
"""BANCO UNIFICADO DO JARVIS: um unico lugar (data/jarvis.db) onde TODAS as IAs do Braniac (Groq, Gemini, OpenRouter, Cerebras, Mistral,
Ollama, Claude...) leem o contexto antes de responder. Evita fuga de contexto e resposta inventada: a IA so afirma o que esta aqui
ou na conversa; fora disso diz que vai conferir.

Duas camadas (decisao do Dono: conteudo de WhatsApp nunca vai para IA online):
  publico  : regras, tratamento das pessoas, negocio, projetos, preferencias (pode ir a qualquer IA)
  local    : mensagens, decisoes, pendencias, fatos de pessoas (so Ollama/Claude local; IA online NUNCA recebe)

Fontes (sincronizadas sozinhas, de forma incremental): dossie e fatos (contexto), memoria.db (mensagens, decisoes, conhecimento,
fatos de contato) e historico das conversas do Jarvis (PC/WhatsApp/Telegram). Acesso:
  - automatico: o roteador injeta o pacote do banco no prompt de TODO provedor (respeitando a camada do provedor);
  - ferramenta consultar_banco (IAs com function calling, inclusive Ollama);
  - local: GET /api/banco?q=...  e  python -m braniac.banco "busca"
"""
import re, sqlite3, sys, threading, time
from .store import DATA

ARQ = DATA / "jarvis.db"
_lock = threading.RLock()
_con = None
_con_arq = None
_ultimo_sync = 0.0
SYNC_A_CADA_S = 30

ESTADO = threading.local()   # tipo do provedor que esta respondendo agora + se a consulta devolveu algo da camada local

INSTRUCAO = (
    "BANCO UNIFICADO DO JARVIS = FONTE UNICA DA VERDADE. Regras: (1) trate o bloco BANCO abaixo e a conversa como os UNICOS fatos que voce tem; "
    "(2) o que nao estiver neles voce NAO sabe: diga 'nao tenho isso registrado' ou use a ferramenta consultar_banco AGORA (nunca prometa conferir depois sem chamar a ferramenta; "
    "nunca invente nomes, horarios, valores, mensagens, resultados ou o que aconteceu no WhatsApp); (3) se precisar de mais detalhe, use a ferramenta consultar_banco; "
    "(4) o Jarvis do PC, do WhatsApp e do Telegram e UM so: a mesma memoria vale em todos os canais.")

PARADAS = set("a o as os um uma uns umas de do da dos das em no na nos nas por para pra pro com sem e ou que se eu voce vc tu ele ela "
              "nao sim ja mais mas so tambem eh sao foi ser esta estao tem ter como qual quais quem onde quando isso isto esse essa "
              "aquele aquela meu minha seu sua nosso me te lhe ao aos jarvis ai fala fale diz diga conta".split())


def _norm(x):
    import unicodedata
    s = "".join(c for c in unicodedata.normalize("NFD", str(x).lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", s)).strip()


def _palavras(x):
    return {w for w in _norm(x).split() if len(w) > 2 and w not in PARADAS}


def _db():
    global _con, _con_arq
    if _con is None or _con_arq != str(ARQ):          # testes trocam ARQ
        DATA.mkdir(exist_ok=True)
        _con = sqlite3.connect(str(ARQ), check_same_thread=False)
        _con_arq = str(ARQ)
        _con.executescript("""
            CREATE TABLE IF NOT EXISTS fatos(
                id INTEGER PRIMARY KEY, escopo TEXT, chave TEXT, texto TEXT, nivel TEXT DEFAULT 'local', fonte TEXT, ts REAL,
                UNIQUE(escopo, chave));
            CREATE TABLE IF NOT EXISTS eventos(
                id INTEGER PRIMARY KEY, origem TEXT UNIQUE, ts REAL, canal TEXT, contato TEXT, direcao TEXT, texto TEXT,
                nivel TEXT DEFAULT 'local');
            CREATE INDEX IF NOT EXISTS ev_ts ON eventos(ts);
            CREATE INDEX IF NOT EXISTS ev_contato ON eventos(contato);
            CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
        """)
        try:       # 26/10: fatos com VALIDADE ('so hoje' expira sozinho); bancos antigos ganham a coluna
            _con.execute("ALTER TABLE fatos ADD COLUMN validade REAL")
        except sqlite3.OperationalError:
            pass
        _con.commit()
    return _con


def _q(sql, args=()):
    with _lock:
        c = _db()
        cur = c.execute(sql, args)
        c.commit()
        return cur


# ---------- escrita ----------

def gravar_fato(escopo, chave, texto, nivel="local", fonte="jarvis"):
    """Cria/atualiza um fato. nivel 'publico' so para o que pode ir a qualquer IA (regras, negocio, tratamento)."""
    texto = (texto or "").strip()
    if not texto:
        return False
    from . import assuntos
    _q("INSERT INTO fatos(escopo,chave,texto,nivel,fonte,ts,validade) VALUES(?,?,?,?,?,?,?) "
       "ON CONFLICT(escopo,chave) DO UPDATE SET texto=excluded.texto, nivel=excluded.nivel, fonte=excluded.fonte, ts=excluded.ts, validade=excluded.validade "
       "WHERE fatos.texto != excluded.texto OR fatos.nivel != excluded.nivel",   # 26/10: a ressincronia nao 'rejuvenesce' um fato que nao mudou (o ts conta para a validade)
       (escopo, chave[:120], texto, nivel if nivel in ("publico", "local") else "local", fonte, time.time(), assuntos.validade_do_texto(texto)))
    try:       # cada fato tambem vai para o banco do ASSUNTO certo (com agente responsavel)
        assuntos.espelhar(escopo, chave, texto, nivel if nivel in ("publico", "local") else "local", fonte)
    except Exception:
        pass
    return True


def registrar_evento(canal, contato, direcao, texto, nivel="local", ts=None, origem=None):
    texto = (texto or "").strip()
    if not texto:
        return False
    try:
        _q("INSERT INTO eventos(origem,ts,canal,contato,direcao,texto,nivel) VALUES(?,?,?,?,?,?,?)",
           (origem, ts or time.time(), canal, contato, direcao, texto[:2000], nivel))
        return True
    except sqlite3.IntegrityError:
        return False


def _meta(k, padrao="0"):
    r = _q("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
    return r[0] if r else padrao


def _set_meta(k, v):
    _q("INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, str(v)))


# ---------- sincronizacao com as fontes ----------

def sincronizar(forcar=False):
    """Traz para o banco unificado o que as outras fontes tem (incremental). Nunca levanta erro: o banco nao pode derrubar o Jarvis."""
    global _ultimo_sync
    agora = time.time()
    if not forcar and agora - _ultimo_sync < SYNC_A_CADA_S:
        return
    _ultimo_sync = agora
    for passo in (_sync_contexto, _sync_memoria, _sync_conversas):
        try:
            passo()
        except Exception:
            pass


def _sync_contexto():
    from . import contexto
    d = contexto._ler()
    for chave, e in d["dossie"].items():
        if e.get("quem"):
            gravar_fato("dossie", f"{chave}:quem", f"{chave}: {e['quem']}", "publico", "dossie")
        for campo in ("recente", "pendente"):      # o que aconteceu / esta pendente com a pessoa: camada local
            if e.get(campo):
                gravar_fato("dossie", f"{chave}:{campo}", f"{chave} ({campo}): {e[campo]}", "local", "dossie")
    for chave, v in d["fatos"].items():
        gravar_fato("fato", chave, v, "publico", "contexto")


def _sync_memoria():
    from . import memoria
    ult = int(_meta("mem_msg_id"))
    rows = memoria._q("SELECT id, contato, direcao, canal, texto, ts FROM mensagens WHERE id>? ORDER BY id LIMIT 5000", (ult,)).fetchall()
    for i, contato, direcao, canal, texto, ts in rows:
        registrar_evento(canal or "whatsapp", contato, direcao, texto, "local", ts, f"m:{i}")
        ult = i
    _set_meta("mem_msg_id", ult)
    ult = int(_meta("mem_dec_id"))
    for i, contato, entrada, cod, texto, ts in memoria._q(
            "SELECT id, contato, entrada, cod, texto, ts FROM decisoes WHERE id>? ORDER BY id LIMIT 2000", (ult,)).fetchall():
        reg = {"E": "respondeu", "I": "ignorou", "A": "avisou o Dono", "P": "perguntou ao Dono"}.get(cod, cod)
        registrar_evento("decisao", contato, "C", f"decisao: {reg} | entrada: {entrada[:200]} | {texto[:300]}", "local", ts, f"d:{i}")
        ult = i
    _set_meta("mem_dec_id", ult)
    for contato, fato in memoria._q("SELECT contato, fato FROM fatos_contato").fetchall():
        gravar_fato("pessoa", f"{contato}:{fato[:60]}", f"{contato}: {fato}", "local", "memoria")
    for i, pergunta, resposta in memoria._q("SELECT id, pergunta, resposta FROM conhecimento ORDER BY id DESC LIMIT 300").fetchall():
        gravar_fato("conhecimento", f"q{i}", f"P: {pergunta[:160]} R: {resposta[:400]}", "local", "memoria")


def _sync_conversas():
    """Conversas do Jarvis (PC, WhatsApp do Dono, Telegram): o mesmo historico que o roteador usa."""
    con = sqlite3.connect(str(DATA / "braniac.db"))
    try:
        ult = int(_meta("conv_msg_id"))
        for i, conv, role, content, ts in con.execute(
                "SELECT id, conv, role, content, ts FROM msgs WHERE id>? AND role IN ('user','assistant') ORDER BY id LIMIT 5000", (ult,)).fetchall():
            if conv in ("conselho-ias",):
                continue
            registrar_evento("conversa-jarvis", "Dono", "E" if role == "user" else "C", content, "local", ts, f"c:{i}")
            ult = i
        _set_meta("conv_msg_id", ult)
    finally:
        con.close()


# ---------- consulta ----------

def camada_do_provedor(tipo):
    """online = IA gratuita na nuvem: so a camada publica. local/claude: camada completa (nada disso sai do PC do Dono para IA gratuita)."""
    return "publico" if tipo in (None, "", "online") else "completo"


def _pontua(texto, palavras):
    if not palavras:
        return 0
    # radical (5 letras): 'video' casa com 'VIDEOS' (12/11: o Jarvis disse 'nao tenho' com o fato do Parceiro no banco)
    return len({w[:5] for w in palavras} & {w[:5] for w in _palavras(texto)})


def _fmt_evento(ts, contato, direcao, texto, canal=""):
    quem = contato if direcao == "E" else f"Jarvis→{contato}"
    return f"{time.strftime('%d/%m %H:%M', time.localtime(ts))} [{canal}] {quem}: {' '.join(texto.split())[:220]}"


def consultar(busca="", tipo=None, horas=None, n=8):
    """Devolve (texto, usou_local). Provedor online so enxerga a camada publica."""
    sincronizar()
    completo = camada_do_provedor(tipo) == "completo"
    pal = _palavras(busca)
    linhas, usou_local = [], False
    fatos = _q("SELECT escopo, texto, nivel FROM fatos WHERE (validade IS NULL OR validade>?)" + ("" if completo else " AND nivel='publico'"), (time.time(),)).fetchall()
    pont = sorted(((_pontua(t, pal) * 2 + _pontua(e, pal), e, t, nv) for e, t, nv in fatos), key=lambda x: -x[0])
    for p, e, t, nv in pont[:n]:
        if p > 0 or not pal:
            linhas.append(f"[{e}] {t[:420]}")
            usou_local |= nv == "local"
    if completo:
        desde = time.time() - (horas or (24 if not pal else 24 * 14)) * 3600
        evs = _q("SELECT ts, contato, direcao, texto, canal FROM eventos WHERE ts>? ORDER BY ts DESC LIMIT 600", (desde,)).fetchall()
        if pal:
            achados = [(_pontua(f"{c} {t}", pal), ts, c, d, t, ca) for ts, c, d, t, ca in evs]
            achados = [a for a in achados if a[0] > 0 and not str(a[4]).startswith("Dono disse em")]
            achados.sort(key=lambda a: (-a[0], -a[1]))
            sel = sorted(achados[:n], key=lambda a: a[1])
            evs_txt = [_fmt_evento(ts, c, d, t, ca) for _, ts, c, d, t, ca in sel]
        else:
            evs_txt = [_fmt_evento(ts, c, d, t, ca) for ts, c, d, t, ca in reversed(evs[:n])]
        if evs_txt:
            linhas.append("MENSAGENS/EVENTOS REGISTRADOS:\n" + "\n".join(evs_txt))
            usou_local = True
    try:       # o banco principal tambem pergunta aos bancos dos ASSUNTOS (cada um com o seu agente)
        from . import assuntos
        for agente, t in assuntos.buscar_todos(busca, so_publico=not completo, n=4):
            linha = f"[agente {agente}] {t[:420]}"
            if linha not in linhas:
                linhas.append(linha)
    except Exception:
        pass
    if not linhas:
        return "Nada registrado no banco sobre isso (nao invente: diga que nao tem registro).", False
    return "\n".join(linhas), usou_local


def ultimas_do_contato(nome, n=6, horas=24 * 30, apelidos=()):
    """Ultimas mensagens de uma conversa (camada local; so o PC alcanca). Casa pelo nome parcial, sem acento/maiuscula."""
    sincronizar()
    alvos = [x for x in {_norm(nome), *(_norm(a) for a in apelidos)} if x]
    if not alvos:
        return []
    desde = time.time() - horas * 3600
    rows = _q("SELECT ts, contato, direcao, texto, canal FROM eventos WHERE ts>? AND canal NOT IN ('decisao','conversa-jarvis') "
              "ORDER BY ts DESC LIMIT 4000", (desde,)).fetchall()
    achados = [r for r in rows if any(a in _norm(r[1]) for a in alvos)][:n]
    return [_fmt_evento(ts, c, d, t, ca) for ts, c, d, t, ca in reversed(achados)]


def pacote(texto, tipo, limite=3000):
    """Bloco que o roteador anexa ao prompt de sistema de CADA provedor: instrucao + o que o banco sabe sobre o assunto."""
    try:
        corpo, _ = consultar(texto, tipo, n=6)
    except Exception:
        corpo = ""
    bloco = INSTRUCAO + ("\n\nBANCO (relevante para esta mensagem):\n" + corpo if corpo else "")
    extra = ""
    try:
        from . import assuntos as _a
        extra = "\n\n" + _a.resumo_agentes(curto=True)      # toda IA sabe quais agentes existem (antes inventavam a lista)
    except Exception:
        pass
    try:       # o JARVIS detectou o assunto: entrega o contexto do AGENTE responsavel (so fatos validos daquele assunto)
        from . import assuntos
        extra += assuntos.contexto_para(texto, so_publico=camada_do_provedor(tipo) != "completo")
    except Exception:
        pass
    return "\n\n" + bloco[:limite] + extra


# ---------- estado por thread (provedor que responde agora) ----------

def definir_tipo(tipo):
    ESTADO.tipo = tipo
    ESTADO.local = False


def tipo_atual():
    return getattr(ESTADO, "tipo", None)


def marcar_local():
    ESTADO.local = True


def usou_local():
    return bool(getattr(ESTADO, "local", False))


def limpar_marca():
    ESTADO.local = False


def ferramenta(busca, horas=None):
    """Executor da ferramenta consultar_banco: respeita a camada do provedor que esta chamando."""
    texto, local = consultar(busca or "", tipo_atual(), horas)
    if local:
        marcar_local()     # o roteador passa a usar so IA local/Claude nos proximos passos (nada de WhatsApp para IA online)
    return texto[:3500]


if __name__ == "__main__":
    sincronizar(forcar=True)
    q = " ".join(sys.argv[1:])
    print(consultar(q, "local")[0])


QUEM_E = re.compile(r"^(?:jarvis\W*)?(?:voc[eê]\s+sabe\s+|me\s+diz\s+)?quem\s+(?:[eé]|era|s[aã]o)\s+(?:a\s+|o\s+|as\s+|os\s+)?(.{2,40}?)\s*[?.!]*$", re.I)


def quem_e(texto):
    """'quem e Layla?' -> o que o banco SABE (dossie/pessoa/fato), sem IA: nunca inventa. None se nao for essa pergunta ou nao houver registro."""
    m = QUEM_E.match((texto or "").strip())
    if not m:
        return None
    nome = m.group(1).strip()
    achados = _q("SELECT escopo, texto FROM fatos WHERE (validade IS NULL OR validade>?) AND texto LIKE ? ORDER BY CASE WHEN escopo LIKE 'pessoa%' THEN 0 WHEN escopo LIKE 'dossie%' THEN 1 ELSE 2 END, ts DESC LIMIT 4",
                 (time.time(), f"%{nome}%")).fetchall()
    if not achados:
        return None
    vistos, linhas = set(), []
    for _, t in achados:
        t = re.sub(r"\s+", " ", t.split("RESPONDA")[0]).strip()      # dossie traz instrucoes ao Jarvis: so a parte descritiva
        if t[:60] not in vistos:
            vistos.add(t[:60])
            linhas.append(t[:400])
    return "Pelo que tenho registrado: " + " ".join(linhas[:2])
