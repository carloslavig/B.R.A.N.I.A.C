# -*- coding: utf-8 -*-
"""A.L.M.A. OBSERVA E CUIDA (26/10/2026). A rotina saiu daqui (agora e do agente Compasso, compasso.py). A Alma agora:
 1. RECEBE do Jarvis tudo que o Dono diz (barramento.py, tipo 'dono_disse') e separa o que e da vida pessoal (familia, saude, emocao) do resto;
 2. APRENDE o jeito do Dono: guarda amostras das frases dele e, 1x por dia, resume o estilo (IA LOCAL) em data/alma/estilo.md para copiar a forma dele;
 3. GUARDA no banco (camada local) o que ele conta da familia/preocupacoes, e vai entendendo a urgencia pela recorrencia;
 4. E PROATIVA, sempre dentro de travas: crise/urgencia -> avisa a Parceira (e o Dono); preocupacao -> consulta o conselho de IAs com uma pergunta GENERICA
    (nunca com as palavras, nomes ou dados do Dono) e leva o conselho ate ele; pode avisar a Mae de forma carinhosa e SEM conteudo; pedido de melhoria de TI ->
    proposta + pedido ao Colega por mensagem generica. Tetos diarios por destino; nada de pagamento/senha; mensagens nao urgentes so das 7h as 22h.
Tudo que o Dono diz fica LOCAL: nada de WhatsApp/pessoal vai para IA online. Ela NAO e medica nem psicologa: em crise orienta CVV 188 / SAMU 192."""
import json
import re
import threading
import time
from datetime import datetime

from . import barramento
from .store import DATA

PASTA = DATA / "alma"
DIARIO = PASTA / "diario.jsonl"
AMOSTRAS = PASTA / "estilo_amostras.jsonl"
ESTILO = PASTA / "estilo.md"
ESTADO = PASTA / "cuida.json"
TETOS = {"parceira": 2, "mae": 1, "dono": 4, "conselho": 2, "colega": 1}
HORA_MIN, HORA_MAX = 7, 22
INTERVALO_S = 5 * 60
LOCK = threading.Lock()
PROIBIDOS = re.compile(r"cart[aã]o|cpf|senha|c[oó]digo|token|pix|transfer|pagamento|boleto|conta banc|chave|segredo|login", re.I)

CRISE = re.compile(r"suicid|me matar|quero morrer|n[aã]o quero mais viver|desistir de tudo|acabar com tudo|me machucar", re.I)
URGENTE = re.compile(r"socorro|emerg[eê]ncia|passando mal|acidente|internad|hospital|sangr|infart|desmai|n[aã]o aguento|falta de ar|dor no peito|urgente", re.I)
TEMAS = {
    "saude": re.compile(r"\bdor\b|doente|febre|m[eé]dic|rem[eé]dio|enjoo|tontura|insônia|insonia|dormi mal|n[aã]o dormi|sem comer|fome|cansad|exaust", re.I),
    "emocional": re.compile(r"triste|chateado|preocupad|angusti|ansios|ansiedade|estress|sozinho|medo|desanim|deprim|cansei|sobrecarreg|esgotad", re.I),
    "familia": re.compile(r"\bfilho\b|filho|minha m[aã]e|mainha|tia m[aá]rcia|meu pai|irm[aã]o|\bjr\b|parceira[ií]na|parceira|esposa|fam[ií]lia|\bv[oó]\b", re.I),
    "ti": re.compile(r"braniac|jarvis|\bbug\b|sistema|notebook|servidor|instal|c[oó]digo|n[aã]o consegue|queria que o jarvis|quero que o jarvis|seria bom se", re.I),
    "trabalho": re.compile(r"vaga|emprego|sal[aá]rio|d[ií]vida|prazo|entrevista|cliente|dinheiro", re.I),
}
PESSOAIS = {"saude", "emocional", "familia"}
INTERNO = re.compile(r"OBJETIVO|ETAPA \d|RESULTADOS DAS ETAPAS|Conversa recente no WhatsApp|Confira com rigor|AVALIACAO-AUTOMATICA", re.I)


def _agora():
    return datetime.now()


def _estado():
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _salvar(e):
    PASTA.mkdir(parents=True, exist_ok=True)
    ESTADO.write_text(json.dumps(e, ensure_ascii=False), encoding="utf-8")


def _pode(destino, agora=None):
    """Teto diario por destino. Devolve True e CONTA o uso."""
    agora = agora or _agora()
    with LOCK:
        e = _estado()
        hoje = agora.strftime("%Y-%m-%d")
        usos = e.setdefault("usos", {})
        if usos.get("dia") != hoje:
            usos.clear()
            usos["dia"] = hoje
        if usos.get(destino, 0) >= TETOS[destino]:
            return False
        usos[destino] = usos.get(destino, 0) + 1
        _salvar(e)
    return True


def classificar(texto, recorrencia=None):
    """Pura. {tema, pessoal, urgencia 0-3, necessidade, crise}. Recorrencia (tema -> vezes na semana) sobe a urgencia aos poucos."""
    t = texto or ""
    crise = bool(CRISE.search(t))
    temas = [k for k, rx in TEMAS.items() if rx.search(t)]
    tema = next((k for k in ("saude", "emocional", "familia", "ti", "trabalho") if k in temas), "")
    urg = 3 if (crise or URGENTE.search(t)) else 0
    if not urg:
        urg = 2 if (("saude" in temas or "emocional" in temas) and re.search(r"muito|demais|forte|piorou|todo dia|de novo|h[aá] dias|n[aã]o passa", t, re.I)) else (1 if tema in PESSOAIS else 0)
        if urg and recorrencia and recorrencia.get(tema, 0) >= 3:
            urg = min(3, urg + 1)
    nec = "fisica" if "saude" in temas else ("emocional" if "emocional" in temas else "")
    return {"tema": tema, "pessoal": bool(set(temas) & PESSOAIS), "urgencia": urg, "necessidade": nec, "crise": crise}


def observar(texto, origem="web"):
    """CHAMADO PELO JARVIS a cada fala do Dono. Posta no barramento (Jarvis -> Alma) e, se for crise/urgencia, reage na hora (sem esperar o ciclo)."""
    t = (texto or "").strip()
    if len(t) < 4 or t.startswith("/") or len(t) > 900 or INTERNO.search(t):
        return False
    barramento.enviar("Jarvis", "Alma", "dono_disse", t[:600], urgencia=3 if (CRISE.search(t) or URGENTE.search(t)) else 0)
    c = classificar(t)
    if c["urgencia"] >= 3:
        threading.Thread(target=_ciclo_seguro, args=(None,), daemon=True).start()
    return True


def _ciclo_seguro(enviar):
    try:
        ciclo(enviar)
    except Exception:
        pass


def _recorrencia():
    corte = time.time() - 7 * 86400
    cont = {}
    try:
        for l in DIARIO.read_text(encoding="utf-8").splitlines()[-400:]:
            x = json.loads(l)
            if x["ts"] >= corte and x.get("tema"):
                cont[x["tema"]] = cont.get(x["tema"], 0) + 1
    except (OSError, ValueError, KeyError):
        pass
    return cont


def _guardar(item, c):
    PASTA.mkdir(parents=True, exist_ok=True)
    with DIARIO.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": item["ts"], "texto": item["texto"][:300], **c}, ensure_ascii=False) + "\n")
    if len(item["texto"]) >= 15:
        with AMOSTRAS.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": item["ts"], "texto": item["texto"][:300]}, ensure_ascii=False) + "\n")
    # (27/10) NAO grava a fala do Dono como "fato": o fato voltava no contexto como o item mais parecido com a propria pergunta e o Jarvis repetia a frase.
    # O diario local (diario.jsonl) basta; fatos de verdade vem de gravar_fato explicito.


def _nome(apelido):
    from . import compasso
    return compasso._nome_whatsapp(apelido)


def _dentro_do_horario(agora):
    return HORA_MIN <= agora.hour <= HORA_MAX


def _audio_da_alma(texto, enviar_audio=None):
    """16/11: alem do texto, a Alma manda AUDIO com a voz dela (escolhida em /vozes) so para o Dono (ele tem dificuldade de leitura). Nunca derruba o aviso de texto."""
    try:
        if enviar_audio is None:
            from . import vozes_agentes, wpp_voz
            enviar_audio = lambda nome, t: wpp_voz.enviar_voz(nome, vozes_agentes.falar_wav("alma", t[:900]))
        enviar_audio(_nome("dono"), texto)
    except Exception:
        pass


def _mandar(enviar, apelido, texto, enviar_audio=None):
    if PROIBIDOS.search(texto):
        return False
    if apelido != "dono":      # so o Dono ouve os apelidos intimos da Alma (regra dele, 16/11)
        from . import tratamento
        texto = tratamento.alma_terceiros(texto)
    enviar(_nome(apelido), texto)
    if apelido == "dono":
        _audio_da_alma(texto, enviar_audio)
    barramento.enviar("Alma", "Jarvis", "status", f"avisei {apelido}: {texto[:120]}")
    return True


def agir(item, c, enviar, conselho=None, agora=None):
    """Decide e executa a reacao proativa para UMA fala do Dono. Devolve a lista do que fez (para log/teste)."""
    agora = agora or _agora()
    fez = []
    t = item["texto"]
    if c["crise"] and _pode("dono", agora):
        _mandar(enviar, "dono", "💗 Dono, li o que você escreveu e me importo com você. Não precisa passar por isso sozinho: pode ligar agora para o CVV (188, 24h, gratuito) ou SAMU (192). "
                "Já estou chamando a Parceira pra ficar com você. Estou aqui.")
        fez.append("crise->dono")
    if c["urgencia"] >= 3 and _pode("parceira", agora):
        _mandar(enviar, "parceira", "Parceira, é a Alma, assistente do Dono. Ele escreveu agora algo que parece URGENTE (saúde ou emoção) e ele pode precisar de você. "
                "Dá uma olhada nele assim que puder, por favor 💗")
        fez.append("urgente->parceira")
    elif c["urgencia"] >= 2 and c["necessidade"] and _dentro_do_horario(agora) and _pode("conselho", agora):
        tema = "uma sobrecarga física (cansaço, dor ou sono ruim)" if c["necessidade"] == "fisica" else "uma sobrecarga emocional (preocupação, ansiedade ou estresse)"
        pergunta = (f"Uma pessoa adulta, com rotina puxada e família para cuidar, relatou {tema} e que isso vem se repetindo. Que cuidados simples e acolhedores uma assistente de IA "
                    "pode sugerir e como acompanhar sem ser invasiva nem fingir ser profissional de saúde? Responda em até 5 linhas práticas.")
        resp = (conselho(pergunta) if conselho else "") or ""
        resp = resp.strip()
        if resp and _pode("dono", agora):
            _mandar(enviar, "dono", "💗 Dono, a Alma aqui. Percebi que você anda sobrecarregado e conversei com o conselho de IAs (sem passar nada seu pra eles). O que sugeriram:\n"
                    + resp[:700] + "\nSe piorar, fala com a Parceira ou procura um profissional. Estou por aqui.")
            fez.append("conselho->dono")
    if c["tema"] == "familia" and c["urgencia"] >= 2 and _dentro_do_horario(agora) and c["urgencia"] < 3 and _pode("mae", agora):
        _mandar(enviar, "mae", "Oh minha tia, é a Alma, assistente do Dono. Ele tá com a cabeça cheia hoje, dá uma ligadinha ou um carinho nele quando puder, viu? 💗")
        fez.append("aviso->mae")
    if c["tema"] == "ti" and re.search(r"n[aã]o consegue|queria que o jarvis|quero que o jarvis|seria bom se|n[aã]o d[aá] pra", t, re.I):
        _proposta_ti(t)
        fez.append("proposta-ti")
        if _dentro_do_horario(agora) and _pode("colega", agora):
            pedido = re.sub(r"\s+", " ", t)[:160]
            if not PROIBIDOS.search(pedido):
                enviar(_nome("colega"), f"Fala, Colega! Aqui é o Jarvis, assistente do Dono. Ele comentou isto sobre o sistema: \"{pedido}\". Tem alguma sugestão de como melhorar pra gente conseguir fazer? Valeu!")
                barramento.enviar("Alma", "Forja", "pedido", f"melhoria de TI pedida ao Colega: {pedido}")
                fez.append("pedido->colega")
    return fez


def _proposta_ti(texto):
    d = DATA / "propostas"
    d.mkdir(exist_ok=True)
    with (d / f"alma-{_agora():%Y%m%d-%H%M%S}.md").open("w", encoding="utf-8") as f:
        f.write(f"# Proposta da Alma (ideia do Dono)\n\nO Dono disse: {texto[:400]}\n\nNada é aplicado sem o Dono aprovar.\n")


def ciclo(enviar=None, conselho=None, agora=None):
    """Le a caixa da Alma no barramento, classifica, guarda e age. Devolve quantas mensagens processou."""
    if enviar is None:
        from . import rotina
        enviar = rotina._enviar
    n = 0
    for m in barramento.caixa("Alma", n=10):
        barramento.marcar_lida(m["id"])
        if m["tipo"] != "dono_disse":
            continue
        item = {"ts": m["ts"], "texto": m["texto"]}
        c = classificar(item["texto"], _recorrencia())
        try:
            from . import alma_aprende
            alma_aprende.completar_tema(item["texto"], c)           # NB local quando as regex nao acham tema; etiqueta trabalho/casa
            alma_aprende.registrar_sinais(item["texto"], item["ts"])  # so metadados, nunca o texto
            if c.get("tema_indef"):
                alma_aprende.enfileirar_rotulo(item["texto"])
        except Exception:
            pass
        _guardar(item, c)
        try:
            from . import alma_mente
            alma_mente.processar(item, c, enviar, agora)     # 16/11: humor, memoria em camadas e reacao propria (parabens, acalmar, animar)
        except Exception:
            pass
        if c["urgencia"] >= 3:
            barramento.enviar("Alma", "Jarvis", "alerta", f"urgência {c['urgencia']} ({c['tema'] or 'sem tema'}): o Jarvis decide como avisar o Dono", urgencia=3)   # mesmo barramento, sem canal novo
        try:
            agir(item, c, enviar, conselho, agora)
        except Exception:
            pass
        n += 1
    return n


def aprender_estilo(llm, agora=None):
    """1x por dia, com >=25 frases novas: resume o jeito do Dono (tom, palavras, tamanho) com IA LOCAL em data/alma/estilo.md."""
    agora = agora or _agora()
    e = _estado()
    if e.get("estilo_dia") == agora.strftime("%Y-%m-%d"):
        return False
    try:
        frases = [json.loads(l)["texto"] for l in AMOSTRAS.read_text(encoding="utf-8").splitlines()[-120:]]
    except (OSError, ValueError, KeyError):
        return False
    if len(frases) < 25:
        return False
    sis = "Você analisa o jeito de escrever de uma pessoa e descreve em português, em até 12 linhas: tom, gírias e expressões que repete, tamanho das frases, como cumprimenta e como pede as coisas. Só descreva, não invente."
    ant = ESTILO.read_text(encoding="utf-8")[:1500] if ESTILO.exists() else ""
    try:
        txt = llm(sis, [], ("Descrição anterior:\n" + ant + "\n\n" if ant else "") + "Frases dele:\n" + "\n".join(f"- {f}" for f in frases)).strip()
    except Exception:
        return False
    if len(txt) < 40:
        return False
    PASTA.mkdir(parents=True, exist_ok=True)
    ESTILO.write_text(txt, encoding="utf-8")
    e["estilo_dia"] = agora.strftime("%Y-%m-%d")
    _salvar(e)
    return True


def iniciar(router):
    """Thread local (como grupo_ia): a cada 5 min processa a caixa da Alma; o estilo e aprendido 1x por dia com o Ollama local."""
    def conselho(pergunta):
        from . import conselho as C, jarvis
        rel = C.reunir(pergunta, jarvis.consultar_reuniao, lambda p: router.responder_neutro("Sintetize em português, até 5 linhas práticas.", p)[0], "até 5 linhas práticas")
        return rel.split("Síntese:")[-1].strip()

    def loop():
        time.sleep(120)
        while True:
            try:
                from . import power
                if not power.pausado():
                    ciclo(None, conselho)
                    from . import sala
                    aprender_estilo(sala._ollama)
                    from . import alma_mente
                    alma_mente.aprender_perfil()                            # 1x por dia: o que a Alma sabe do Dono (perfil_core.json)
                    alma_mente.iniciativa()                                 # 16/11: ela puxa conversa (como foi o dia, dormiu, comeu, assunto em aberto), com teto proprio
                    from . import voz_do_dono, jarvis
                    voz_do_dono.refinar(jarvis.consultar_reuniao)       # 1x por semana: a Alma pede ao conselho o guia de voz (descricao abstrata)
                    from . import alma_aprende
                    alma_aprende.atualizar_perfil()                         # estilo 7/30/90d, temperamento e retencao de 90 dias
            except Exception:
                pass
            time.sleep(INTERVALO_S)
    threading.Thread(target=loop, daemon=True, name="alma_cuida").start()
