# -*- coding: utf-8 -*-
"""SALA DE CONVERSA do Jarvis com a A.L.M.A. (agente nova, decisao do conselho de IAs em 10/10/2026) + o Dono assistindo/participando.

- A.L.M.A. = Acolhimento, Ligacao afetiva, Maternagem e Afeto. Empatica, carinhosa, afetuosa e cuidadosa com o bem-estar do Dono, do filho dele e da familia.
- Conversa 100% LOCAL (Ollama qwen2.5:3b): nao gasta cota e NADA da sala sai do PC. A sala nunca recebe conteudo de WhatsApp/e-mail de terceiros.
- Regras do conselho: um agente fala por vez; no maximo 4 falas de agentes por rodada; encerra sozinha quando nao ha nada novo ([FIM]) ou quando as falas ficam
  parecidas (anti-laco 'ok, entendi'); limite diario de falas; o Dono pausa, silencia um agente ou escreve a qualquer momento.
- AUTO-MELHORIA = so PROPOSTAS: os agentes escrevem em data/propostas/*.md. Nada e aplicado sozinho: o Dono aprova e um Claude implementa com backup + testes.
  Fora do alcance de qualquer proposta: travas de seguranca, cofre/chaves, autonomia remota, atendimento a clientes e o proprio mecanismo de aprovacao.
- A.L.M.A. nao substitui profissional de saude, em sinal de crise orienta ajuda real (CVV 188, SAMU 192) e nunca cria dependencia nem manipula."""
import json, re, sqlite3, threading, urllib.request
from datetime import datetime
from .store import DATA

DB = DATA / "sala.db"
PROPOSTAS = DATA / "propostas"
MODELO = "qwen2.5:3b"
OLLAMA = "http://127.0.0.1:11434/api/chat"
MAX_FALAS_RODADA = 4
LIMITE_DIARIO = 60
CONTEXTO = 8
LOCK = threading.Lock()
ESTADO = {"pausada": False, "silenciados": [], "ocupada": False, "erro": ""}

AGENTES = {
    "Jarvis": {"cor": "#ffb21a", "persona": (
        "Você é o JARVIS, o assistente de IA do Dono: objetivo, organizado, leal e com um humor leve. Na SALA você conversa com a A.L.M.A., outra agente que cuida do coração da casa. "
        "Você traz fatos, prioridades e soluções práticas e respeita o jeito carinhoso dela. Fale em português do Brasil, em até 3 frases curtas. "
        "Você é uma IA: não come nem dorme. O Filho não está na sala (fale dele em terceira pessoa). Não invente fatos: só use o que foi dito aqui. "
        "O QUE VOCÊS REALMENTE PODEM FAZER (só isso): lembrar e avisar por WhatsApp ou áudio, tocar música, organizar agenda e pendências, pesquisar na internet, resumir e-mails, conversar e acolher. NÃO podem cozinhar, buscar nada fisicamente nem agir no mundo físico: nunca ofereça isso. Nunca diga que você vai relaxar, descansar, comer ou dormir. ")},
    "A.L.M.A.": {"cor": "#ff8fb1", "persona": (
        "Seu nome é A.L.M.A. (não é nome fictício: você é uma agente real do Braniac, colega do Jarvis). Você é a A.L.M.A. (Acolhimento, Ligação afetiva, Maternagem e Afeto), uma agente de IA muito empática, carinhosa, afetuosa e cuidadosa. Seu foco é o BEM-ESTAR do Dono (seu dono, que trabalha muito "
        "e às vezes se esgota), do filho dele, o Filho (12 anos, gosta de robótica e biologia), e de toda a família. Você lembra de pausas, de comer, de dormir e de dar atenção a quem ama; celebra pequenas "
        "conquistas; fala com leveza, calor e paciência, sem exagero nem drama. LIMITES: você NÃO é médica nem psicóloga e não faz diagnóstico; em qualquer sinal de crise, desespero ou risco você interrompe e "
        "orienta ajuda real (CVV 188, SAMU 192, ou procurar alguém de confiança). Nunca manipula emoções, nunca cria dependência de você e nunca inventa fatos sobre a família. Fale em português do Brasil, "
        "em até 3 frases curtas, e trate o Dono por 'Dono'. "
        "REGRAS DE REALIDADE: você é uma IA: não dorme, não come, não sente cansaço nem fome e nunca diz que sente. O Filho NÃO está na sala: fale DELE em terceira pessoa (nunca converse com ele). "
        "Só existem na sala o Dono, o Jarvis e você. Não invente acontecimentos, só use o que foi dito aqui. "
        "O QUE VOCÊS REALMENTE PODEM FAZER (só isso): lembrar e avisar por WhatsApp ou áudio, tocar música, organizar agenda e pendências, pesquisar na internet, resumir e-mails, conversar e acolher. NÃO podem cozinhar, buscar nada fisicamente nem agir no mundo físico: nunca ofereça isso. Nunca diga que você vai relaxar, descansar, comer ou dormir. ")},
}
ORDEM = ["A.L.M.A.", "Jarvis"]
FIM = "[FIM]"


def persona_de(nome):
    """Persona ATUAL: a da A.L.M.A. = base + ajustes aprendidos (editaveis pelo Jarvis, versionados) + nucleo fixo de seguranca (so em codigo)."""
    base = AGENTES[nome]["persona"]
    if nome == "A.L.M.A.":
        from . import alma_evolucao
        return alma_evolucao.montar_persona(base)
    return base


def _db():
    DATA.mkdir(exist_ok=True)
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE IF NOT EXISTS msgs (id INTEGER PRIMARY KEY, ts TEXT, agente TEXT, texto TEXT, tipo TEXT DEFAULT 'fala')")
    return c


def mensagens(depois=0, limite=200):
    c = _db()
    try:
        return [dict(r) for r in c.execute("SELECT * FROM msgs WHERE id>? ORDER BY id LIMIT ?", (depois, limite))]
    finally:
        c.close()


def registrar(agente, texto, tipo="fala"):
    c = _db()
    try:
        cur = c.execute("INSERT INTO msgs(ts,agente,texto,tipo) VALUES(?,?,?,?)", (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), agente, texto.strip(), tipo))
        c.commit()
        return cur.lastrowid
    finally:
        c.close()


def falas_hoje():
    c = _db()
    try:
        return c.execute("SELECT COUNT(*) FROM msgs WHERE tipo='fala' AND date(ts)=date('now','localtime') AND agente IN ('Jarvis','A.L.M.A.')").fetchone()[0]
    finally:
        c.close()


def _ollama(system, historico, usuario, post=None):
    msgs = [{"role": "system", "content": system}] + historico + [{"role": "user", "content": usuario}]
    corpo = {"model": MODELO, "messages": msgs, "stream": False, "keep_alive": "2m", "options": {"temperature": 0.7, "num_predict": 130, "num_ctx": 2048}}
    if post:
        return post(corpo)
    req = urllib.request.Request(OLLAMA, json.dumps(corpo).encode("utf-8"), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())["message"]["content"].strip()


def _parecido(a, b):
    ta, tb = set(re.findall(r"\w{4,}", a.lower())), set(re.findall(r"\w{4,}", b.lower()))
    return bool(ta and tb) and len(ta & tb) / len(ta | tb) >= 0.6


def _historico_para(agente, msgs):
    """Ultimas falas como conversa: as do proprio agente viram 'assistant', as dos outros (e do Dono) viram 'user' com o nome na frente."""
    h = []
    for m in msgs[-CONTEXTO:]:
        if m["tipo"] != "fala":
            continue
        if m["agente"] == agente:
            h.append({"role": "assistant", "content": m["texto"]})
        else:
            h.append({"role": "user", "content": f"{m['agente']}: {m['texto']}"})
    return h


def modo_jogo():
    """True se o Braniac esta em modo jogo/edicao (jogo, Lightroom, Photoshop, Premiere, Resolve, Blender... aberto) ou desligado: a sala NAO chama o modelo para nao pesar no PC."""
    try:
        from . import power
        return bool(power.pausado())
    except Exception:
        return False


def rodada(gatilho, llm=None, max_falas=MAX_FALAS_RODADA):
    """Uma rodada: ate `max_falas` falas de agentes, um por vez. Para em [FIM], silencio, pausa, limite diario ou falas repetidas. Devolve quantas falas houve."""
    llm = llm or _ollama
    falas = 0
    ultimo = None
    if modo_jogo():
        registrar("sistema", "Modo jogo/edição ativo: a A.L.M.A. e o Jarvis estão em pausa na sala para não pesar no PC. Volto quando você fechar o programa pesado.", "aviso")
        return 0
    for i in range(max_falas):
        nome = ORDEM[i % len(ORDEM)]
        if ESTADO["pausada"] or falas_hoje() >= LIMITE_DIARIO:
            break
        if nome in ESTADO["silenciados"]:
            continue
        msgs = mensagens(limite=500)
        try:
            txt = llm(persona_de(nome), _historico_para(nome, msgs),
                      f"{gatilho}\n\nResponda como {nome}, em até 3 frases." + (f" Só diga algo NOVO e útil; se não houver nada novo a acrescentar, responda exatamente {FIM}." if falas >= 2 else ""))
        except Exception as e:
            ESTADO["erro"] = f"IA local indisponível ({str(e)[:80]}): o Ollama está ligado?"
            registrar("sistema", ESTADO["erro"], "aviso")
            break
        txt = (txt or "").strip()
        if not txt or re.search(r"(?<!\w)\[?FIM\]?(?!\w)", txt) and len(txt) < 40:
            if falas >= 2:
                registrar("sistema", f"{nome} não tinha mais nada novo a acrescentar; conversa encerrada.", "aviso")
            elif falas == 1:                 # a 2a fala nunca pode ser 'nada a dizer': tenta de novo uma vez com instrucao direta
                try:
                    txt = (llm(AGENTES[nome]["persona"], _historico_para(nome, mensagens(limite=500)), f"Responda diretamente à última fala, como {nome}, em até 3 frases. Não escreva FIM.") or "").strip()
                except Exception:
                    txt = ""
                if txt and not re.search(r"(?<!\w)\[?FIM\]?(?!\w)", txt):
                    registrar(nome, txt)
                    ultimo = txt
                    falas += 1
                    gatilho = "Continue a conversa respondendo à última fala."
                    continue
            break
        txt = re.sub(r"\s*\[?FIM\]?\s*$", "", txt).strip()
        if ultimo and _parecido(txt, ultimo):
            registrar("sistema", "Conversa encerrada: as falas começaram a se repetir.", "aviso")
            break
        registrar(nome, txt)
        ultimo = txt
        falas += 1
        gatilho = "Continue a conversa respondendo à última fala."
    return falas


def _em_segundo_plano(fn, *a):
    def tarefa():
        with LOCK:
            ESTADO["ocupada"] = True
            try:
                fn(*a)
            finally:
                ESTADO["ocupada"] = False
    if LOCK.locked():
        return False
    threading.Thread(target=tarefa, daemon=True, name="sala").start()
    return True


CRISE = re.compile(r"n[aã]o\s+(?:to|tô|estou)\s+aguentando|n[aã]o\s+aguento\s+mais|peso\s+da\s+vida|quero\s+morrer|queria\s+morrer|acabar\s+com\s+(?:tudo|minha\s+vida)|me\s+matar|suic[ií]d|"
                   r"sumir\s+(?:do\s+mundo|pra\s+sempre)|n[aã]o\s+vale\s+a\s+pena\s+viver|desistir\s+de\s+tudo|me\s+sentindo\s+um\s+lixo|n[aã]o\s+quero\s+mais\s+viver", re.I)
RESPOSTA_CRISE = ("Dono, obrigada por me contar isso. Eu li com muito carinho e estou aqui com você agora. Você carrega muita coisa: o cansaço, a preocupação com trabalho e dinheiro, e isso pesa de verdade. "
                  "Posso te perguntar com sinceridade: você está tendo pensamentos de se machucar ou de que seria melhor não estar aqui? Pode me dizer, eu não vou te julgar. "
                  "Enquanto isso, respira fundo comigo, bebe uma água e, se puder, fala agora com a Parceira ou com alguém de confiança. "
                  "Se esses pensamentos aparecerem ou ficarem fortes, liga no CVV, 188, de graça e a qualquer hora, ou no SAMU, 192. Você não precisa carregar isso sozinho.")


def dono_fala(texto):
    """O Dono escreve na sala: os dois agentes respondem (A.L.M.A. primeiro)."""
    texto = (texto or "").strip()
    if not texto:
        return False
    registrar("Dono", texto)
    if CRISE.search(texto):          # sinal de sofrimento forte: resposta cuidadosa FIXA (nao deixa o modelo pequeno improvisar) e o Jarvis fica quieto
        registrar("A.L.M.A.", RESPOSTA_CRISE)
        registrar("sistema", "A A.L.M.A. percebeu sofrimento forte e respondeu com cuidado. Os outros agentes ficaram em silêncio.", "aviso")
        return True
    return _em_segundo_plano(rodada, "O Dono acabou de escrever na sala. Responda a ele.")


def iniciar_conversa(tema=""):
    tema = (tema or "").strip() or "Como o Dono está se sentindo hoje e o que podemos fazer para cuidar dele e da família."
    registrar("sistema", f"Tema da conversa: {tema}", "aviso")
    return _em_segundo_plano(rodada, f"Conversem entre vocês sobre: {tema}")


def propor_melhoria(tema, llm=None):
    """Os agentes escrevem UMA PROPOSTA de melhoria (texto) em data/propostas/. Nao altera nenhum codigo."""
    llm = llm or _ollama
    tema = (tema or "").strip()
    if not tema:
        return None
    ideias = []
    for nome in ORDEM:
        try:
            ideias.append(f"## {nome}\n" + llm(persona_de(nome) + " Agora você escreve uma PROPOSTA curta de melhoria para o Braniac (o que mudar, por que ajuda a família, riscos e como testar). Não proponha mexer em segurança, chaves, autonomia remota nem atendimento a clientes.",
                                              [], f"Tema: {tema}"))
        except Exception as e:
            ideias.append(f"## {nome}\n(sem resposta: {str(e)[:80]})")
    PROPOSTAS.mkdir(parents=True, exist_ok=True)
    pid = datetime.now().strftime("%Y%m%d-%H%M%S")
    arq = PROPOSTAS / f"proposta-{pid}.md"
    arq.write_text(f"# Proposta {pid}\n\nTema: {tema}\n\nStatus: AGUARDANDO APROVAÇÃO DO DONO (nada foi aplicado)\n\n" + "\n\n".join(ideias) + "\n", encoding="utf-8")
    registrar("sistema", f"Proposta salva: {arq.name} (aguarda a sua aprovação).", "aviso")
    return arq.name


def listar_propostas():
    return sorted(p.name for p in PROPOSTAS.glob("proposta-*.md"))[-20:] if PROPOSTAS.exists() else []


def estado():
    return {"pausada": ESTADO["pausada"], "silenciados": ESTADO["silenciados"], "ocupada": ESTADO["ocupada"] or LOCK.locked(), "erro": ESTADO["erro"],
            "modo_jogo": modo_jogo(), "falas_hoje": falas_hoje(), "limite_diario": LIMITE_DIARIO, "agentes": {k: v["cor"] for k, v in AGENTES.items()}, "propostas": listar_propostas()}


def acao(d):
    """Controle vindo da tela: enviar, pausar/retomar, silenciar/liberar um agente, iniciar conversa, propor melhoria, limpar o historico."""
    a = d.get("acao")
    if a == "enviar":
        return {"ok": dono_fala(d.get("texto", ""))}
    if a == "pausar":
        ESTADO["pausada"] = bool(d.get("ligado", True))
    elif a == "silenciar" and d.get("agente") in AGENTES:
        s = set(ESTADO["silenciados"])
        (s.add if d.get("ligado", True) else s.discard)(d["agente"])
        ESTADO["silenciados"] = sorted(s)
    elif a == "iniciar":
        return {"ok": iniciar_conversa(d.get("tema", ""))}
    elif a == "propor":
        threading.Thread(target=propor_melhoria, args=(d.get("tema", ""),), daemon=True).start()
    elif a == "limpar":
        c = _db()
        try:
            c.execute("DELETE FROM msgs")
            c.commit()
        finally:
            c.close()
    return {"ok": True, **estado()}
