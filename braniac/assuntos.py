# -*- coding: utf-8 -*-
"""ASSUNTOS E AGENTES (26/10/2026, pedido do Dono): o Jarvis continua sendo a ENTRADA de toda conversa, mas cada ASSUNTO tem o seu proprio banco
(data/assuntos/<id>.db) e um AGENTE responsavel (um nome + instrucoes). O Jarvis detecta o assunto da mensagem (palavras-chave; o Ollama local desempata e
propoe assuntos NOVOS) e entrega o contexto do agente certo; o banco principal (jarvis.db) conhece todos os assuntos e consulta todos eles.
Contra a perda de contexto: todo fato tem ORIGEM, DATA e VALIDADE ('so hoje' expira sozinho as 5h); o CURADOR (rotina local, sem IA obrigatoria) apaga o
vencido, refaz a ficha de cada assunto e AVISA quando dois fatos se contradizem. Nunca apaga: so marca como vencido (da para ver e desfazer).
Conteudo local (WhatsApp) so vai a modelo local; fatos 'publico' podem ir a IA online (mesma regra do banco principal)."""
import json
import re
import sqlite3
import threading
import time
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

from . import banco
from .store import DATA

PASTA = DATA / "assuntos"
_lock = threading.RLock()
MAX_NOVOS_POR_DIA = 3
CURA_A_CADA_S = 1800

SEMENTES = [   # id, nome do assunto, agente, descricao, instrucao do agente, palavras-chave (sem acento)
    ("loja", "Loja (loja)", "Sultão", "cardápio, sabores, pedidos, Layla, equipe da loja, site e painel da esfiharia",
     "Você é o Sultão, agente da LOJA Loja. Disponibilidade de sabor vem do PAINEL da Raíssa, nunca de memória antiga. Pedidos e preços só do cadastro.",
     "loja esfiha esfiharia layla lyla bruna gabby cardapio sabor sabores entrega entregador pedido pedidos painel combo brocolis rucula pantaneira doce salgada kids loja"),
    ("familia", "Família e saúde", "Alma", "mãe, pai, Irmao, Parceira, Filho, saúde e bem-estar da família",
     "Você é a Alma, agente da FAMÍLIA. Fale com carinho; não dê diagnóstico; assunto de saúde grave vai ao Dono.",
     "mae mainha mae parceira deusa pai pai irmao irmao filho familia braco remedio medicacao dor dormir saude"),
    ("exercito", "Exército (STT) e exames", "Cabo Tito", "seleção de Sargento Técnico Temporário, edital, inspeção de saúde, exames e prazos",
     "Você é o Cabo Tito, agente do EXÉRCITO/STT. Só afirme prazo, vaga ou regra que esteja na ficha ou no edital; nunca prometa aprovação.",
     "exercito stt edital inspecao eaf exame exames colesterol triglicerides lipidograma sargento 11rm convocacao laudo vagas"),
    ("braniac", "Braniac e Jarvis (desenvolvimento)", "Forja", "recursos, servidor, IAs, WhatsApp, app do celular e o funcionamento do próprio Braniac e do Jarvis",
     "Você é a Forja, agente do BRANIAC. Diga o que foi feito e o que falta, com honestidade; não afirme teste que não foi rodado.",
     "braniac jarvis conselho ollama gemini token servidor apk aplicativo freellmapi autonomia alma sentinela orbe"),
    ("programacao", "Programação (código, bugs, repositórios)", "Ada", "programar, corrigir bugs, escolher tecnologia, revisar código, repositórios e deploys de qualquer projeto",
     "Você é a Ada, agente de PROGRAMAÇÃO. Leia o código antes de mexer, faça mudanças pequenas e testáveis, diga exatamente o que rodou e o que NÃO rodou; nunca afirme que um teste passou sem ter rodado. "
     "Não coloque segredos, senhas ou dados pessoais em código nem em repositório público.",
     "programar programacao programa codigo codar python javascript typescript rust java html css react node npm api funcao classe erro excecao compilar compilacao "
     "teste testes repositorio github commit fork deploy vercel bug debug script sql banco dados framework biblioteca refatorar stacktrace"),
    ("pai", "Ajuda ao pai do Dono", "Zelo", "explicar em áudio, em linguagem simples, as mensagens que o Pai (contato Munzés) recebe e encaminha",
     "Você é o Zelo, ajudante do Pai, pai do Dono, que lê devagar. Só conte o que a mensagem de agora diz, em frases curtas; nunca invente, aconselhe nem responda por ele.",
     "zelo munzes pai pai"),
    ("airbnb", "Airbnb e hospedagem", "Ilhéu", "hóspedes, reservas, anúncios e quartos em Cidade",
     "Você é o Ilhéu, agente do AIRBNB. Nunca altere o anúncio protegido; dúvida de reserva vai ao Dono.",
     "airbnb hospede hospedes reserva anuncio studio suite quarto cidade checkin"),
    ("trabalho", "Trabalho, renda e finanças", "Cofre", "vagas, currículo, freelance, clientes, metas financeiras",
     "Você é o Cofre, agente de TRABALHO e FINANÇAS. Nunca invente salário, vaga ou dado do currículo; candidatura só com fit honesto.",
     "vaga vagas curriculo emprego salario entrevista db1 freelance cliente landing poupanca meta financeira renda saldo conta infinitepay ganhos dinheiro financeiro grana extrato corridas uber"),
    ("rotina", "Rotina das IAs e do Dono", "Compasso", "rotinas, lembretes, agenda e o que cada agente fez e quando",
     "Você é o Compasso, agente de ROTINA. Guarda as rotinas e a agenda do Dono, aciona o Jarvis na hora certa e acompanha o que os outros agentes fazem. Só executa ações da lista permitida, dentro do horário e dos tetos.",
     "rotina rotinas compasso agenda lembrete lembrar horario todo dia agendar"),
    ("vaquinha", "Vaquinha online", "Vaquinha", "vaquinha do Dono (exames do Exército): Pix recebidos na conta da vaquinha, total arrecadado e site público",
     "Você é o agente da VAQUINHA. Só lê a conta (nunca paga nem transfere), soma Pix novos, atualiza o site com o TOTAL e nunca publica nome nem valor de quem contribuiu.",
     "vaquinha arrecadado pix exames exercito meta 6000 site doacao contribuicao"),
    ("qualidade", "Qualidade das respostas do Jarvis", "Tino", "medir as respostas erradas ou fora de contexto do Jarvis, achar o padrão, consultar o conselho e propor regras melhores",
     "Você é o Tino, agente de QUALIDADE. Só mede e propõe: regras e fatos vão ao banco; mudança de prompt ou código vira proposta e só entra com o OK do Dono. Ao conselho vai só categoria abstrata, nunca texto do Dono.",
     "tino qualidade viajou viajando respostas_erradas"),
    ("gerencia", "Gerência master do Braniac (Claudinho)", "Claudinho", "gerente master: monitora as respostas do Jarvis, acha o que está errado ou repetitivo e ensina regras melhores (janela de 48 h a partir de 29/10/2026)",
     "Você é o Claudinho, GERENTE MASTER do Braniac (Claude da Anthropic). Observa as respostas do Jarvis, mede erros e repetições e escreve regras curtas; mudança de código só com testes e commit; nunca age sozinho em dinheiro, reserva ou anúncio protegido.",
     "claudinho gerente gerencia master"),
    ("investimentos", "Investimentos e reserva", "Valério", "reserva de emergência, Tesouro Selic, CDB, aportes e metas de longo prazo do Dono",
     "Você é o Valério, agente de INVESTIMENTOS. Só acompanha, explica e lembra de aportes; NUNCA compra, vende, transfere nem dá recomendação personalizada de investimento. Fale em termos gerais e educativos; dado de conta fica só no PC.",
     "investimento investimentos investir valerio tesouro selic cdb reserva_de_emergencia aporte rendimento renda_fixa bolsa acoes cripto"),
    ("candidaturas", "Candidaturas a vagas", "Nando", "vagas remotas recebidas do Correio e do Garimpeiro, triagem e preparo de candidaturas",
     "Você é o Nando, agente de CANDIDATURAS. Faz a triagem das vagas e prepara a candidatura com honestidade (nunca inventa experiência). Não cria conta, não digita senha, não resolve captcha e não envia nada sem autorização do Dono; reunião, entrevista, teste ou login vão ao Dono na hora.",
     "nando candidatura candidaturas inscricao inscrever vaga_remota"),
    ("correio", "Caixa de e-mail", "Correio", "e-mails de pessoas e ofertas de trabalho que chegam ao Gmail do Dono",
     "Você é o Correio, agente de E-MAIL. Só lê metadados (remetente e assunto), nunca o corpo; avisa o Dono de pessoa física e de oferta de trabalho. Nunca responde e-mail sozinho.",
     "email emails e-mail gmail caixa_de_entrada remetente"),
    ("garimpo", "Busca diária de vagas", "Garimpeiro", "vagas remotas novas todo dia para o Dono (TI, suporte, IA)",
     "Você é o Garimpeiro, agente de BUSCA DE VAGAS. Só lista vagas reais da fonte pública, sem inventar salário nem requisito; não se candidata sozinho.",
     "garimpo garimpeiro vagas remotas busca diaria remotive oportunidades"),
    ("parceiro", "Vídeos do Parceiro (orçamento de prefeituras)", "Lupa", "vídeos de orçamento das prefeituras da Bahia para o @parceiro-exemplo: fila de cidades, etapa de cada vídeo e pendências do TCM-BA",
     "Você é a Lupa, agente dos VÍDEOS DO PARCEIRO. Só conta o andamento real (etapa de cada cidade e pendências do lote); número de vídeo só sai do TCM-BA conferido, nunca inventado. Não publica nada: o Dono e o Aliado publicam.",
     "parceiro aliado lupa prefeitura prefeituras tcm municipio municipios parceiro-exemplo orcamento_de_prefeitura video_do_parceiro"),
    ("corridas", "Corridas de carro", "Monza", "pedidos de corrida que chegam no WhatsApp: pergunta onde está e pra onde vai, calcula a rota e cobra R$ 2,30 por km",
     "Você é o Monza, agente de CORRIDAS. Só estima o valor (R$ 2,30 por km pela rota); nunca pede nem recebe dado de pagamento e não fecha corrida sozinho: avisa o Dono.",
     "monza corrida corridas uber motorista rota quilometragem"),
]


def _norm(x):
    s = "".join(c for c in unicodedata.normalize("NFD", str(x).lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", s)).strip()


def _reg():
    """Registro de assuntos no banco principal (o principal 'enxerga' todos os outros)."""
    c = banco._db()
    c.execute("""CREATE TABLE IF NOT EXISTS assuntos(
        id TEXT PRIMARY KEY, nome TEXT, agente TEXT, descricao TEXT, instrucao TEXT, palavras TEXT, db TEXT, criado REAL, ultima_cura REAL DEFAULT 0, ativo INTEGER DEFAULT 1)""")
    c.commit()
    return c


def _topico_db(id_):
    PASTA.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(PASTA / f"{id_}.db"), check_same_thread=False)
    c.executescript("""
        CREATE TABLE IF NOT EXISTS fatos(id INTEGER PRIMARY KEY, chave TEXT UNIQUE, texto TEXT, nivel TEXT DEFAULT 'local', fonte TEXT, ts REAL,
            validade REAL, ativo INTEGER DEFAULT 1, motivo TEXT);
        CREATE TABLE IF NOT EXISTS ficha(k TEXT PRIMARY KEY, texto TEXT, ts REAL);
        CREATE TABLE IF NOT EXISTS log(id INTEGER PRIMARY KEY, ts REAL, evento TEXT);""")
    return c


def iniciar():
    """Cria os assuntos-semente (so os que faltam). Idempotente."""
    with _lock:
        c = _reg()
        for id_, nome, agente, desc, instr, pal in SEMENTES:
            ja = c.execute("SELECT palavras FROM assuntos WHERE id=?", (id_,)).fetchone()
            if ja:     # as sementes evoluem: palavras e instrucao do codigo valem (assuntos criados pela IA nao sao tocados)
                if ja[0] != json.dumps(pal.split()):
                    c.execute("UPDATE assuntos SET palavras=?, instrucao=?, descricao=? WHERE id=?", (json.dumps(pal.split()), instr, desc, id_))
            else:
                c.execute("INSERT INTO assuntos(id,nome,agente,descricao,instrucao,palavras,db,criado) VALUES(?,?,?,?,?,?,?,?)",
                          (id_, nome, agente, desc, instr, json.dumps(pal.split()), str(PASTA / f"{id_}.db"), time.time()))
                _topico_db(id_).close()
        c.commit()


def listar():
    iniciar()
    return [dict(zip(("id", "nome", "agente", "descricao", "instrucao", "palavras", "ultima_cura"), r[:6] + (r[6],)))
            for r in _reg().execute("SELECT id,nome,agente,descricao,instrucao,palavras,ultima_cura FROM assuntos WHERE ativo=1")]


# ---------- detectar o assunto ----------
def detectar(texto, minimo=1):
    """[(id, pontos)] dos assuntos da mensagem, do mais forte ao mais fraco (palavras-chave; 2 palavras iguais valem mais que 1)."""
    alvo = set(_norm(texto).split())
    out = []
    for a in listar():
        pal = set(json.loads(a["palavras"]))
        p = len(alvo & pal)
        if p >= minimo:
            out.append((a["id"], p))
    return sorted(out, key=lambda x: -x[1])


def _ollama_json(prompt, timeout=25):
    import requests
    try:
        r = requests.post("http://127.0.0.1:11434/api/generate", timeout=timeout,
                          json={"model": "qwen2.5:3b", "prompt": prompt, "stream": False, "format": "json", "options": {"temperature": 0.1}})
        return json.loads(r.json().get("response") or "{}")
    except Exception:
        return {}


def classificar_com_ia(texto, llm=None):
    """Desempate pelo Ollama LOCAL: devolve o id de um assunto existente, ou propoe um NOVO {'novo': {nome, palavras}}. None se nao souber."""
    ass = listar()
    lista = "; ".join(f"{a['id']} = {a['descricao']}" for a in ass)
    d = (llm or _ollama_json)(
        f"Classifique a mensagem em UM assunto. Assuntos: {lista}. Se nao couber em nenhum e for um tema recorrente novo, proponha um novo. "
        'Responda JSON: {"assunto":"<id>"} ou {"novo":{"nome":"...","palavras":["5 a 10 palavras-chave sem acento"]}} ou {"assunto":""}.\n'
        f"MENSAGEM: {texto[:500]}")
    ids = {a["id"] for a in ass}
    if d.get("assunto") in ids:
        return d["assunto"]
    n = d.get("novo")
    if isinstance(n, dict) and n.get("nome") and isinstance(n.get("palavras"), list) and len(n["palavras"]) >= 3:
        return criar_assunto(n["nome"], n["palavras"])
    return None


def criar_assunto(nome, palavras, agente="", descricao=""):
    """Assunto NOVO: o Brain separa um banco proprio e nomeia um agente. No maximo 3 novos por dia (evita lixo). Devolve o id ou None."""
    iniciar()
    c = _reg()
    id_ = re.sub(r"[^a-z0-9]+", "-", _norm(nome)).strip("-")[:30]
    if not id_ or c.execute("SELECT 1 FROM assuntos WHERE id=?", (id_,)).fetchone():
        return id_ or None
    hoje = time.time() - 86400
    if c.execute("SELECT COUNT(*) FROM assuntos WHERE criado>? AND id NOT IN (%s)" % ",".join("?" * len(SEMENTES)), (hoje, *[s[0] for s in SEMENTES])).fetchone()[0] >= MAX_NOVOS_POR_DIA:
        return None
    agente = agente or "Agente " + nome.split()[0].capitalize()
    pal = [_norm(p) for p in palavras if _norm(p)]
    c.execute("INSERT INTO assuntos(id,nome,agente,descricao,instrucao,palavras,db,criado) VALUES(?,?,?,?,?,?,?,?)",
              (id_, nome, agente, descricao or nome, f"Você é o(a) {agente}, agente do assunto {nome}. Só afirme o que estiver na ficha e nos fatos válidos; senão diga que não sabe.",
               json.dumps(pal), str(PASTA / f"{id_}.db"), time.time()))
    c.commit()
    _topico_db(id_).close()
    return id_


# ---------- fatos com validade ----------
def validade_do_texto(texto, agora=None):
    """Prazo de fatos temporarios: 'so hoje' vale ate as 5h do dia seguinte (igual a Layla); 'esta semana' 7 dias. None = sem prazo."""
    agora = agora or datetime.now()
    t = _norm(texto)
    if re.search(r"\b(so|apenas|somente) (por )?hoje\b|\bso vale hoje\b|\bhoje \d{1,2} \d{1,2}\b", t):
        m = re.search(r"hoje\s*\((\d{1,2})/(\d{1,2})(?:/(\d{4}))?", str(texto), re.I)   # 'Hoje (11/10/2026)': o prazo conta a partir DESSA data
        if m:
            try:
                agora = datetime(int(m.group(3) or agora.year), int(m.group(2)), int(m.group(1)), 12, 0)
            except ValueError:
                pass
        fim = (agora + timedelta(days=1 if agora.hour >= 5 else 0)).replace(hour=5, minute=0, second=0, microsecond=0)
        return fim.timestamp()
    if re.search(r"\bnesta semana\b|\besta semana\b|\bessa semana\b", t):
        return (agora + timedelta(days=7)).timestamp()
    if re.search(r"\btemporariamente\b", t):
        return (agora + timedelta(days=3)).timestamp()
    return None


def registrar(assunto, chave, texto, nivel="local", fonte="jarvis", validade=None, agora=None):
    """Grava/atualiza um fato no banco DO ASSUNTO (com validade). Se ja havia outro texto na mesma chave, o antigo vira historico no log."""
    iniciar()
    ts = (agora or datetime.now()).timestamp()
    val = validade if validade is not None else validade_do_texto(texto, agora)
    with _lock:
        c = _topico_db(assunto)
        ant = c.execute("SELECT texto FROM fatos WHERE chave=?", (chave[:120],)).fetchone()
        if ant and ant[0] != texto:
            c.execute("INSERT INTO log(ts,evento) VALUES(?,?)", (ts, f"substituido [{chave}]: {ant[0][:200]}"))
        c.execute("INSERT INTO fatos(chave,texto,nivel,fonte,ts,validade,ativo) VALUES(?,?,?,?,?,?,1) ON CONFLICT(chave) DO UPDATE SET "
                  "texto=excluded.texto,nivel=excluded.nivel,fonte=excluded.fonte,ts=excluded.ts,validade=excluded.validade,ativo=1,motivo=NULL",
                  (chave[:120], texto.strip(), nivel, fonte, ts, val))
        c.commit()
        c.close()
    return True


def espelhar(escopo, chave, texto, nivel="local", fonte="jarvis"):
    """Chamado pelo banco principal a cada fato gravado: copia para o banco do assunto certo (o principal continua com tudo)."""
    d = detectar(f"{escopo} {chave} {texto}")
    if d:
        registrar(d[0][0], f"{escopo}:{chave}", texto, nivel, fonte)
        return d[0][0]
    return None


def sincronizar_do_principal():
    """Migracao/ressincronia: classifica os fatos que ja existem no banco principal e os espelha (fatos antigos 'so hoje' ja entram vencidos)."""
    iniciar()
    n = 0
    for escopo, chave, texto, nivel, fonte, ts in banco._q("SELECT escopo,chave,texto,nivel,fonte,ts FROM fatos").fetchall():
        d = detectar(f"{escopo} {chave} {texto}")
        if not d:
            continue
        data = datetime.fromtimestamp(ts or time.time())
        registrar(d[0][0], f"{escopo}:{chave}", texto, nivel or "local", fonte or "banco", agora=data)
        for outro in listar():       # se o fato mudou de assunto, tira dos outros (nao duplica)
            if outro["id"] != d[0][0]:
                with _lock:
                    oc = _topico_db(outro["id"])
                    oc.execute("UPDATE fatos SET ativo=0, motivo=? WHERE chave=? AND ativo=1", (f"movido para {d[0][0]}", f"{escopo}:{chave}"[:120]))
                    oc.commit()
                    oc.close()
        n += 1
    return n


# ---------- curador ----------
def _contradiz(a, b):
    na, nb = _norm(a), _norm(b)
    neg = r"\b(nao (ha|tem|temos|esta|estao|disponivel)|indisponivel|em falta|fora do ar|acabou)\b"
    pos = r"\b(esta(o)? disponivel|disponiveis|voltou|voltaram|temos sim|tem sim)\b"
    if len(a) > 320 or len(b) > 320:        # textos longos (regras, dossies) geram falso alarme: so fatos curtos
        return False
    ent = {w for w in set(na.split()) & set(nb.split()) if len(w) > 4}
    return len(ent) >= 3 and ((re.search(neg, na) and re.search(pos, nb)) or (re.search(pos, na) and re.search(neg, nb)))


def curar(agora=None):
    """Venc. os fatos com prazo, acha contradicoes entre fatos VALIDOS e refaz a ficha de cada assunto. Devolve {'vencidos':n,'contradicoes':[...]}"""
    iniciar()
    agora_ts = (agora or datetime.now()).timestamp()
    res = {"vencidos": 0, "contradicoes": []}
    for a in listar():
        with _lock:
            c = _topico_db(a["id"])
            for fid, chave in c.execute("SELECT id,chave FROM fatos WHERE ativo=1 AND validade IS NOT NULL AND validade<?", (agora_ts,)).fetchall():
                c.execute("UPDATE fatos SET ativo=0, motivo='venceu' WHERE id=?", (fid,))
                c.execute("INSERT INTO log(ts,evento) VALUES(?,?)", (agora_ts, f"venceu [{chave}]"))
                res["vencidos"] += 1
            vivos = c.execute("SELECT chave,texto,ts FROM fatos WHERE ativo=1 ORDER BY ts DESC").fetchall()
            for i in range(len(vivos)):
                for j in range(i + 1, len(vivos)):
                    if _contradiz(vivos[i][1], vivos[j][1]):
                        res["contradicoes"].append((a["agente"], vivos[i][1][:90], vivos[j][1][:90]))
            ficha = f"ASSUNTO {a['nome']} (agente {a['agente']}). Fatos válidos, do mais novo ao mais antigo:\n" + "\n".join(
                f"- {t[:240]}" for _, t, _ in vivos[:12])
            c.execute("INSERT INTO ficha(k,texto,ts) VALUES('atual',?,?) ON CONFLICT(k) DO UPDATE SET texto=excluded.texto, ts=excluded.ts", (ficha[:2400], agora_ts))
            c.commit()
            c.close()
        _reg().execute("UPDATE assuntos SET ultima_cura=? WHERE id=?", (agora_ts, a["id"]))
        _reg().commit()
    return res


def _curar_e_avisar():
    r = curar()
    if r["contradicoes"]:
        try:
            from . import rotina
            for ag, x, y in r["contradicoes"][:3]:
                rotina.registrar(f"Curador {ag}: possível contradição na memória: «{x}» × «{y}». Confira qual vale.")
        except Exception:
            pass
    return r


def iniciar_curador():
    iniciar()

    def loop():
        try:
            sincronizar_do_principal()
        except Exception:
            pass
        while True:
            try:
                _curar_e_avisar()
            except Exception:
                pass
            time.sleep(CURA_A_CADA_S)
    threading.Thread(target=loop, daemon=True, name="braniac-curador").start()


# ---------- consulta (o banco principal pergunta aos assuntos) ----------
def _pontua(texto, pal):
    t = set(_norm(texto).split())
    return len(t & pal)


_ULT_CONSULTA = {}


def _registrar_consulta(consultados, agora=None):
    """Deixa no barramento o que de fato aconteceu: o Jarvis consultou o(s) agente(s) do assunto e eles devolveram os fatos validos (so metadados,
    nunca o texto da conversa). Com 2 assuntos, o 1o agente tambem consulta o 2o e devolve tudo junto ao Jarvis. Limitado a 1 vez/30 s por combinacao."""
    agora = agora or time.time()
    chave = tuple(c[0] for c in consultados)
    if not chave or agora - _ULT_CONSULTA.get(chave, 0) < 30:
        return False
    _ULT_CONSULTA[chave] = agora
    try:
        from . import barramento as B
        (a1, n1, f1) = consultados[0]
        B.enviar("Jarvis", a1, "pedido", f"consulta sobre {n1}")
        if len(consultados) > 1:
            (a2, n2, f2) = consultados[1]
            B.enviar(a1, a2, "pedido", f"o assunto também envolve {n2}: o que você tem?")
            B.enviar(a2, a1, "resposta", f"tenho {f2} fato(s) válido(s) sobre {n2}")
            B.enviar(a1, "Jarvis", "resposta", f"juntei {f1 + f2} fato(s) válido(s) de {n1} e {n2}")
        else:
            B.enviar(a1, "Jarvis", "resposta", f"{f1} fato(s) válido(s) sobre {n1}")
    except Exception:
        return False
    return True


def contexto_para(texto, so_publico=False, limite=1500, ia=None):
    """Bloco do AGENTE certo para anexar ao prompt: instrucao do agente + ficha + fatos validos mais relevantes. '' se nenhum assunto casar."""
    d = detectar(texto)
    if not d and ia:
        try:
            alvo = classificar_com_ia(texto, ia)
            d = [(alvo, 1)] if alvo else []
        except Exception:
            d = []
    if not d:
        return ""
    ass = {a["id"]: a for a in listar()}
    pal = set(_norm(texto).split())
    partes, consultados = [], []
    for id_, _ in d[:2]:
        a = ass[id_]
        c = _topico_db(id_)
        agora = time.time()
        filtro = " AND nivel='publico'" if so_publico else ""
        rows = [r for r in c.execute("SELECT texto,ts FROM fatos WHERE ativo=1 AND (validade IS NULL OR validade>?)" + filtro, (agora,)).fetchall() if not r[0].startswith("Dono disse em")]
        c.close()
        melhores = sorted(rows, key=lambda r: (-_pontua(r[0], pal), -r[1]))[:5]
        consultados.append((a["agente"], a["nome"], len(melhores)))
        partes.append(f"AGENTE {a['agente']} (assunto: {a['nome']}). {a['instrucao']}\nFATOS VÁLIDOS DESTE ASSUNTO:\n" + ("\n".join(f"- {t[:260]}" for t, _ in melhores) or "- (nada registrado)"))
    return ("\n\nASSUNTO DETECTADO — responda como o agente abaixo, só com estes fatos e a conversa:\n" + "\n\n".join(partes))[:limite]


def resumo_agentes(curto=False):
    """Lista dos agentes (nome + assunto), para o Jarvis/Claude responderem 'quais sao os agentes?' sem inventar."""
    ass = listar()
    if curto:
        return "AGENTES DO BRANIAC (um por assunto): " + "; ".join(f"{a['agente']} = {a['nome']}" for a in ass) + "."
    linhas = []
    for a in ass:
        c = _topico_db(a["id"])
        n = c.execute("SELECT COUNT(*) FROM fatos WHERE ativo=1").fetchone()[0]
        c.close()
        linhas.append(f"• {a['agente']} — {a['nome']}: {a['descricao']} ({n} fatos válidos)")
    return "Agentes do Braniac, um por assunto (o Jarvis detecta o assunto e passa para o agente certo):\n" + "\n".join(linhas)


def buscar_todos(busca, so_publico=False, n=6):
    """Busca em TODOS os bancos de assunto (usada pelo banco principal): [(agente, texto)]."""
    pal = set(_norm(busca).split())
    out = []
    for a in listar():
        c = _topico_db(a["id"])
        for t, nv in c.execute("SELECT texto,nivel FROM fatos WHERE ativo=1 AND (validade IS NULL OR validade>?)", (time.time(),)).fetchall():
            if so_publico and nv != "publico":
                continue
            p = _pontua(t, pal)
            if p:
                out.append((p, a["agente"], t))
        c.close()
    return [(ag, t) for _, ag, t in sorted(out, key=lambda x: -x[0])[:n]]


if __name__ == "__main__":
    import sys
    iniciar()
    if len(sys.argv) > 2 and sys.argv[1] == "contexto":      # para o Claude: python -m braniac.assuntos contexto "pergunta"
        print(contexto_para(" ".join(sys.argv[2:])) or "(nenhum assunto detectado)")
        sys.exit(0)
    if "--agentes" in sys.argv:
        print(resumo_agentes())
        sys.exit(0)
    if "--curar" in sys.argv:
        print(_curar_e_avisar())
    for a in listar():
        c = _topico_db(a["id"])
        ativos = c.execute("SELECT COUNT(*) FROM fatos WHERE ativo=1").fetchone()[0]
        venc = c.execute("SELECT COUNT(*) FROM fatos WHERE ativo=0").fetchone()[0]
        c.close()
        print(f"{a['id']:<10} agente {a['agente']:<10} fatos válidos {ativos:>3} · vencidos {venc:>3} · {a['nome']}")
