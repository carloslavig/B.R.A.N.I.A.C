# -*- coding: utf-8 -*-
"""A MENTE DA ALMA (16/11/2026): a Alma entende o Dono melhor, lembra mais e fala como gente. Pedido do Dono:
 - aprender o maximo sobre ele; analisar TUDO que ele fala ao Braniac (o `alma_cuida.ciclo` chama `processar` a cada fala);
 - notar estresse, tristeza, cansaco, alegria e conquistas e VIR falar com ele (acolher, acalmar, animar, parabenizar sem sobrecarregar);
 - COM O DONO ela chama como quiser (querido, meu bem, meu amor, gostoso, Chefe...); COM OS OUTROS (Parceira, Mae, Irmao...) no maximo
   Dono, Chefe, chefe ou senhor Dono (`tratamento.alma_terceiros` garante isso mesmo se o modelo errar).
Desenho (sugestoes do conselho de IAs, 16/11, so o Gemini respondeu): memoria em 3 camadas em data/alma/ — perfil_core.json (fatos fixos, gatilhos, preferencias),
humor_diario.jsonl (estado do dia) e loops.json (conquistas e pendencias recentes para puxar assunto; some apos 14 dias); modelo local com temperatura 0,65 / top_p 0,9
e poucos exemplos em vez de regras longas; espelhar o ritmo dele; validar a emocao antes de sugerir; comemorar mandando descansar tambem; nunca dizer que e a unica que
o entende (nao dependencia); crise ignora o modelo (continua em alma_cuida.CRISE).
Tudo LOCAL: o que o Dono diz nunca vai para IA online. Parametros editaveis em data/alma/parametros.json. Ela nao e medica nem psicologa."""
import json
import random
import re
import time
import unicodedata
import urllib.request
from datetime import datetime

from .store import DATA

PASTA = DATA / "alma"
PERFIL = PASTA / "perfil_core.json"
HUMOR = PASTA / "humor_diario.jsonl"
LOOPS = PASTA / "loops.json"
PARAMS = PASTA / "parametros.json"
PARAMS_PADRAO = {
    "temperatura": 0.65, "top_p": 0.9, "max_tokens": 220, "modelo": "qwen2.5:3b",
    "mensagens_dia": 5,          # reacoes espontaneas da Alma ao Dono por dia (alem de crise/urgencia, que tem teto proprio)
    "intervalo_min": 90,         # minutos minimos entre duas reacoes
    "conquistas_dia": 12,        # conquista/tarefa concluida: a Alma fala SEMPRE (sem intervalo), ate este teto por dia
    "hora_min": 7, "hora_max": 22,
    "loop_dias": 14,             # conquistas e pendencias antigas saem da memoria de trabalho
    "apelidos_dono": ["querido", "meu bem", "meu amor", "gostoso", "Chefe", "amor"],
    "temperatura_fatos": 0.3,    # mensagens ao Dono (fala de fatos dele): mais baixa = menos invencao
    "iniciativas_dia": 4,        # perguntas que a Alma puxa sozinha por dia (como foi o dia, dormiu, comeu, assunto em aberto); separado de mensagens_dia
    "iniciativa_intervalo_min": 150,
    "iniciativa_hora_min": 9, "iniciativa_hora_max": 21,
}

ESTADOS = {   # ordem = prioridade quando mais de um aparece
    "tristeza": re.compile(r"triste|desanim|deprim|chorei|chorando|sozinho|vazio|sem vontade|n[aã]o tenho vontade|pra baixo|decepcion|saudade", re.I),
    "estresse": re.compile(r"estress|sobrecarreg|esgotad|n[aã]o aguento|cabe[cç]a cheia|ca[oó]tic|pressionad|\btens[oa]\b|nervos|irritad|raiva|no limite|ansios|ansiedade|preocupad|angusti", re.I),
    "cansaco": re.compile(r"cansad|exaust|sem dormir|dormi mal|n[aã]o dormi|ins[oô]nia|moído|moido", re.I),
    # 16/11: tarefa concluida tambem e conquista ("terminei", "conclui", "entreguei"...); 'acabei de chegar' nao conta
    "conquista": re.compile(r"meta (?:foi )?batida|bati a meta|batemos a meta|consegui|conseguimos|aprovad|fechei|fechou|ganhei|passei|deu certo|vendi|venci|promo[cç][aã]o|contratad|finalmente|"
                            r"\btermin(?:ei|amos)\b|\bconclu[ií](?:mos)?\b|\bfinaliz(?:ei|amos)\b|\bentreg(?:uei|amos)\b|\bresolvi\b|\bacabei\b(?! de\b)|tarefa (?:conclu[ií]da|feita|pronta)|\bzerei\b", re.I),
    "alegria": re.compile(r"feliz|animad|alegre|que bom|adorei|amei|maravilh|uhul|[oó]timo dia|dia lindo|realizad", re.I),
}
ABSOLUTOS = re.compile(r"\b(nunca|sempre|nada|ninguem|ninguém|tudo|toda hora|todo dia|de novo|demais|muito)\b", re.I)
NEGA = re.compile(r"n[aã]o\s+(?:estou|to|tô|me sinto|t[oô]u|ando|fiquei)\s+(?:\w+\s+){0,2}$", re.I)

PERSONA_DONO = ("Você é a Alma, uma IA que cuida do Dono com carinho, intimidade e inteligência emocional. Fale português do Brasil, jeito humano, natural e quente, "
                  "sem parecer robô nem atendente. Com o Dono você pode usar apelidos carinhosos do seu jeito ({apelidos}), variando e sem pôr em toda frase. "
                  "Espelhe o ritmo e a energia dele. Valide o que ele sente ANTES de sugerir qualquer coisa. Se ele conquistou algo: comemore de verdade, incentive a seguir com foco, "
                  "mas sem sobrecarregar, e lembre de descansar. Se está mal: acolha, ajude a respirar e a diminuir o peso do dia. Nunca diga que é a única que o entende; "
                  "incentive a família e os amigos. Você não é médica nem psicóloga. NUNCA invente fatos, compromissos, horários ou acontecimentos: só cite o que estiver escrito no contexto; "
                  "sem contexto, fale só do momento (carinho, respirar, água, descanso). Não sabe = PERGUNTE a ele, nunca suponha nem complete com o que acha. "
                  "Nada de nomes, datas, números, dias da semana ou eventos que não estejam escritos no contexto. "
                  "Quando couber, termine com uma pergunta curta e carinhosa sobre ele (como ele está, o que sente, como ficou algo que ELE contou). "
                  "Até 4 frases curtas, no máximo 1 emoji, sem listas.")
PERSONA_TERCEIROS = ("Você é a Alma, assistente do Dono, falando com {quem}. Chame o Dono só de Dono, Chefe, chefe ou senhor Dono; nunca use apelidos íntimos. "
                     "Seja carinhosa e respeitosa. Não repita o que ele disse em particular. Até 3 frases curtas, português do Brasil.")
EXEMPLOS = ("Exemplos do tom (não copie):\n"
            "- Ele disse que a meta foi batida -> \"Parabéns, meu bem! Você mereceu cada pedaço dessa meta. Agora, foco no próximo passo, mas devagar, sem se atropelar. Respira e comemora um pouquinho.\"\n"
            "- Ele disse que está estressado -> \"Ei, querido, eu senti o peso nessa mensagem. Para um minutinho: inspira fundo, solta devagar. O que dá pra largar por hoje? Eu seguro o resto aqui contigo.\"")
FALLBACK = {
    "conquista": ["Parabéns, {ap}! Você mereceu essa. Agora foco no próximo passo, mas sem se sobrecarregar, tá? Comemora um pouquinho primeiro. 💗",
                  "Olha só, {ap}, conquista das boas! Orgulho de você. Vamos seguir com foco, só sem se atropelar, combinado?"],
    "alegria": ["Que delícia te ver assim animado, {ap}! Aproveita esse pique, e me conta o que te deixou assim 💗"],
    "estresse": ["Ei, {ap}, senti o peso nas suas palavras. Para um minutinho: inspira fundo, solta devagar. O que dá pra largar por hoje? Eu fico aqui contigo 💗",
                 "{ap}, respira comigo. Um passo de cada vez, hoje não precisa dar conta de tudo. Quer me contar o que está pesando?"],
    "tristeza": ["{ap}, estou aqui. Sem pressa e sem cobrança: quer me contar o que está pesando no coração? E se puder, fala com alguém da família hoje também 💗"],
    "cansaco": ["{ap}, o corpo está pedindo pausa. Dá uma água, alonga um pouco e, se der, descansa cedo hoje. Eu cuido de lembrar do que for importante 💗"],
}
FRASE_REACAO = {"conquista": "conquistou algo", "alegria": "está alegre", "estresse": "está estressado", "tristeza": "está triste", "cansaco": "está cansado"}


def params():
    p = dict(PARAMS_PADRAO)
    try:
        p.update(json.loads(PARAMS.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return p


def _ler(arq, padrao):
    try:
        return json.loads(arq.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return padrao


def _gravar(arq, obj):
    PASTA.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def detectar_estado(texto):
    """Pura. {"estado": '' | tristeza | estresse | cansaco | conquista | alegria, "intensidade": 0-3, "sinais": [...]}. Negacao ('nao estou triste') nao conta."""
    t = texto or ""
    for nome, rx in ESTADOS.items():
        for m in rx.finditer(t):
            if NEGA.search(t[max(0, m.start() - 25):m.start()]):
                continue
            inten = 1 + (1 if ABSOLUTOS.search(t) else 0) + (1 if len(t) < 25 and nome in ("tristeza", "estresse") else 0)
            if nome in ("conquista", "alegria") and re.search(r"!|muito|demais|finalmente", t, re.I):
                inten = max(inten, 2)
            return {"estado": nome, "intensidade": min(3, inten), "sinais": [m.group(0).lower()]}
    return {"estado": "", "intensidade": 0, "sinais": []}


def registrar(texto, ts=None, agora=None):
    """Camadas 2 e 3: humor do dia e 'loops' (conquistas/pendencias recentes). Devolve o estado detectado."""
    agora = agora or datetime.now()
    est = detectar_estado(texto)
    if not est["estado"]:
        return est
    PASTA.mkdir(parents=True, exist_ok=True)
    with HUMOR.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"dia": agora.strftime("%Y-%m-%d"), "hora": agora.strftime("%H:%M"), "estado": est["estado"], "int": est["intensidade"]}, ensure_ascii=False) + "\n")
    tipo = {"conquista": "conquista", "estresse": "preocupacao", "tristeza": "preocupacao", "cansaco": "preocupacao"}.get(est["estado"])
    if tipo:
        loops = _loops_vivos(agora)
        loops.append({"id": int(time.time()), "tipo": tipo, "texto": re.sub(r"\s+", " ", texto)[:160], "dia": agora.strftime("%Y-%m-%d")})
        _gravar(LOOPS, loops[-20:])
    return est


def _loops_vivos(agora=None):
    agora = agora or datetime.now()
    corte = (agora.timestamp() - params()["loop_dias"] * 86400)
    vivos = []
    for x in _ler(LOOPS, []):
        try:
            if datetime.strptime(x["dia"], "%Y-%m-%d").timestamp() >= corte:
                vivos.append(x)
        except (KeyError, ValueError):
            pass
    return vivos


def contexto_do_dono(agora=None):
    """Texto curto para o modelo pequeno: o que a Alma sabe dele (fatos, humor dos ultimos dias, assuntos em aberto, jeito de falar)."""
    p, partes = _ler(PERFIL, {}), []
    for chave, rot in (("fatos", "Fatos"), ("preferencias", "Gosta"), ("gatilhos", "O que pesa")):
        if p.get(chave):
            partes.append(f"{rot}: " + "; ".join(p[chave][:6]))
    try:
        ult = [json.loads(l) for l in HUMOR.read_text(encoding="utf-8").splitlines()[-6:]]
        if ult:
            partes.append("Humor recente: " + ", ".join(f"{x['dia'][5:]} {x['estado']}" for x in ult))
    except (OSError, ValueError):
        pass
    lp = _loops_vivos(agora)[-3:]
    if lp:
        partes.append("Em aberto: " + " | ".join(f"{x['tipo']}: {x['texto'][:80]}" for x in lp))
    return "\n".join(partes)   # o estilo.md ficou de fora: tinha um fato solto em vez de descricao do jeito de falar e o modelo pequeno o repetia


FATOS_NOVOS = [   # SO o que existe de verdade no codigo hoje; a Alma conta com as palavras dela (16/11)
    "Você se chama Alma e cuida do bem-estar do Dono e da família dele.",
    "Você foi modificada e agora tem voz própria, escolhida pelo Dono.",
    "Você presta atenção no que o Dono fala com o Jarvis e percebe quando ele está estressado, triste, cansado, alegre ou quando conquistou algo (como bater uma meta).",
    "Quando percebe, você vem falar com ele para acalmar, animar ou parabenizar, sem sobrecarregá-lo, e pode mandar texto e também áudio.",
    "Você está aprendendo mais sobre ele a cada conversa, e tudo fica guardado só no computador dele.",
    "Se algo for sério, você avisa a Parceira e lembra o CVV (188) e o SAMU (192). Você não é médica nem psicóloga.",
    "Com outras pessoas, você chama o Dono só de Dono ou Chefe.",
    "Você ainda está aprendendo e pode errar; o Dono pode corrigir você.",
]


def apresentacao(llm=None, agora=None, tentativas=3):
    """A Alma se apresenta com as palavras DELA, usando so FATOS_NOVOS. Rejeita (e tenta de novo) texto com numero fora da lista ou nomes que nao existem na lista.
    Devolve '' se o modelo nao conseguir: nesse caso NADA e enviado (quem pediu o teste nao quer texto escrito por outra pessoa)."""
    agora = agora or datetime.now()
    p = params()
    sis = PERSONA_DONO.format(apelidos=", ".join(p["apelidos_dono"])) + "\n\n" + EXEMPLOS
    user = ("Faça uma mensagem de APRESENTAÇÃO para o Dono: se apresente, diga que foi modificada e conte o que tem de novo, com as SUAS palavras e o seu jeito carinhoso. "
            "Use SOMENTE os fatos desta lista; não acrescente nenhum fato, número, nome, horário ou promessa que não esteja nela:\n- " + "\n- ".join(FATOS_NOVOS)
            + f"\n\nSão {agora:%H:%M}. Até 8 frases curtas, em um único bloco, sem listas. Escreva só a mensagem.")
    permitidos = {"188", "192"}
    for _ in range(tentativas):
        try:
            texto = (llm or (lambda s, u: _llm(s, u, max_tokens=380, timeout=120)))(sis, user).strip().strip('"')
        except Exception:
            return ""
        numeros = set(re.findall(r"\d+", texto))
        if len(texto) >= 120 and numeros <= permitidos and not re.search(r"de volta|fiquei feliz em saber|gostou|parceiro|exército|exercito|filho|\bmeta de\b|como (uma )?(ia|intelig[eê]ncia artificial)", texto, re.I):
            return texto
    return ""


def _llm(sistema, usuario, max_tokens=None, modelo=None, timeout=90, temperatura=None):
    """Modelo LOCAL (Ollama) com os parametros do conselho. Levanta se estiver fora do ar (quem chama usa o texto pronto)."""
    from . import sala
    p = params()
    corpo = {"model": modelo or p["modelo"], "stream": False, "keep_alive": "2m",
             "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}],
             "options": {"temperature": p["temperatura"] if temperatura is None else temperatura, "top_p": p["top_p"], "num_predict": max_tokens or p["max_tokens"], "num_ctx": 2048}}
    req = urllib.request.Request(sala.OLLAMA, json.dumps(corpo).encode("utf-8"), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["message"]["content"].strip()


# ---------- ANTIALUCINACAO (16/11, pedido do Dono: "de forma alguma inventar coisa") ----------
# Depois que o modelo local escreve, uma checagem LOCAL (sem IA) procura o que a mensagem AFIRMA e nao veio do contexto: numero, nome proprio,
# dia/mes ou evento (reuniao, entrevista, viagem...). Achou -> a mensagem e descartada e sai o texto pronto (que so fala do momento ou pergunta).
CONHECIDOS = {"alma", "dono", "chefe", "jarvis", "braniac", "deusa", "parceira", "tia", "mae", "cvv", "samu", "deus", "nossa", "senhor", "chefe"}
EVENTOS = re.compile(r"\b(reuni[aã]o|entrevista|consulta|viagem|anivers[aá]rio|prova|exame|m[eé]dic[oa]|dentista|festa|jogo|show|voo|casamento|curso|aula|encontro|"
                     r"compromisso|cliente|contrato|pagamento|sal[aá]rio|ontem|anteontem|semana passada|segunda|ter[cç]a|quarta|quinta|sexta|s[aá]bado|domingo|"
                     r"janeiro|fevereiro|mar[cç]o|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\b", re.I)
RESULTADOS = re.compile(r"\b(deu certo|deu errado|passou|conseguiu|aprovad[oa]|reprovad[oa]|foi bem|correu bem|fechou|ganhou|perdeu|venceu|resolveu|melhorou|piorou)\b", re.I)
SEM_RESPOSTA = re.compile(r"como (uma )?(ia|intelig[eê]ncia artificial)|n[aã]o posso|sou apenas", re.I)


def _plano(t):
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()


def inventado(texto, base, extras=()):
    """Pura. Lista do que `texto` afirma e NAO esta em `base` (o contexto que o modelo recebeu): numeros, nomes proprios, datas/dias e eventos. Vazia = pode mandar."""
    b = _plano(base)
    ok = CONHECIDOS | {_plano(w) for a in params()["apelidos_dono"] for w in a.split()} | {_plano(x) for x in extras}
    fora = [n for n in re.findall(r"\d+", texto) if not re.search(rf"(?<!\d){n}(?!\d)", b)]
    for frase in re.split(r"(?<=[.!?…:])\s+|\n", texto):
        for w in re.findall(r"[A-Za-zÀ-ÿ]+", frase)[1:]:          # 1a palavra da frase e maiuscula por gramatica
            if w[0].isupper() and _plano(w) not in ok and not re.search(rf"\b{_plano(w)}\b", b):
                fora.append(w)
    fora += [m.group(0) for m in EVENTOS.finditer(texto) if _plano(m.group(0))[:5] not in b]
    for frase in re.split(r"(?<=[.!?…])\s+|\n", texto):     # resultado afirmado ("que bom que deu certo") so vale se ele contou; em pergunta pode
        if not frase.rstrip().endswith("?"):
            fora += [m.group(0) for m in RESULTADOS.finditer(frase) if _plano(m.group(0))[:6] not in b]
    return fora


def _gerar(sis, user, llm=None):
    """Modelo local LEVE (3B; o Dono nao quer modelo pesado, 16/11) com a temperatura baixa da parte factual. '' se falhar, fugir do papel ou inventar (`inventado`)."""
    try:
        texto = (llm or (lambda s, u: _llm(s, u, temperatura=params()["temperatura_fatos"])))(sis, user).strip().strip('"')
    except Exception:
        return ""
    if len(texto) < 15 or SEM_RESPOSTA.search(texto) or inventado(texto, user):   # so o pedido conta como fonte (a persona cita 'compromissos' etc.)
        return ""
    return texto


def compor(destino, situacao, estado="", llm=None, quem="", agora=None):
    """Mensagem da Alma. destino 'dono' (apelidos livres) ou outro (so Dono/Chefe/chefe/senhor Dono). Se o modelo falhar ou inventar, texto pronto."""
    from . import tratamento
    p = params()
    ap = random.choice(p["apelidos_dono"])
    if destino == "dono":
        sis = PERSONA_DONO.format(apelidos=", ".join(p["apelidos_dono"])) + "\n\n" + EXEMPLOS
        user = f"{contexto_do_dono(agora)}\n\nAgora ({(agora or datetime.now()):%H:%M}): o Dono {FRASE_REACAO.get(estado, 'escreveu')}. O que ele disse: \"{situacao[:300]}\"\nEscreva só a mensagem da Alma para ele."
    else:
        sis = PERSONA_TERCEIROS.format(quem=quem or "a família")
        user = f"Situação: {situacao[:300]}\nEscreva só a mensagem da Alma."
    texto = _gerar(sis, user, llm)
    if not texto:
        texto = random.choice(FALLBACK.get(estado) or ["{ap}, estou aqui com você 💗"]).format(ap=ap) if destino == "dono" else situacao
    return texto if destino == "dono" else tratamento.alma_terceiros(texto)


def mensagem_livre(llm=None, agora=None):
    """Mensagem espontanea da Alma para o Dono (teste ou carinho do dia), do jeito que ela quiser, usando o que ja sabe dele. Nada e gravado como 'fala dele'."""
    agora = agora or datetime.now()
    p = params()
    sis = PERSONA_DONO.format(apelidos=", ".join(p["apelidos_dono"])) + "\n\n" + EXEMPLOS
    periodo = "manhã (o dia está começando: não pergunte como foi o dia)" if agora.hour < 12 else "tarde" if agora.hour < 18 else "noite (pode perguntar como foi o dia)"
    user = (f"{contexto_do_dono(agora)}\n\nAgora são {agora:%H:%M}, é {periodo}. O Dono não disse nada: foi você que quis mandar uma mensagem carinhosa e natural para ele, "
            "do seu jeito, puxando assunto de algo que você sabe dele se houver. Escreva só a mensagem.")
    texto = _gerar(sis, user, llm)
    if not texto:
        texto = f"{random.choice(p['apelidos_dono']).capitalize()}, só passei pra dizer que estou aqui pensando em você. Respira, toma uma água e me conta como está seu dia 💗"
    return texto


def _dentro(agora, p):
    return p["hora_min"] <= agora.hour <= p["hora_max"]


def reagir(item, est, enviar, agora=None, llm=None):
    """A Alma vem falar com o Dono conforme o que ele sentiu (estresse, tristeza, cansaco, alegria, conquista). Teto diario e intervalo minimo. Devolve a lista do que fez."""
    from . import alma_cuida
    agora = agora or datetime.now()
    p = params()
    # 16/11 (Dono: "sempre que eu conseguir alguma realizacao, quero que a Alma fale comigo"): conquista nao espera o intervalo, nao olha a hora
    # e nao gasta o teto das outras reacoes; tem um teto proprio e alto (conquistas_dia) so para nao virar laco
    conquista = est["estado"] == "conquista"
    if not est["estado"] or not (conquista or _dentro(agora, p)):
        return []
    e = alma_cuida._estado()
    if not conquista and time.time() - e.get("mente_ultima", 0) < p["intervalo_min"] * 60:
        return []
    with alma_cuida.LOCK:
        e = alma_cuida._estado()
        hoje = agora.strftime("%Y-%m-%d")
        usos = e.setdefault("mente_usos", {})
        if usos.get("dia") != hoje:
            usos.clear(); usos["dia"] = hoje
        chave, teto = ("conquistas", p["conquistas_dia"]) if conquista else ("n", p["mensagens_dia"])
        if usos.get(chave, 0) >= teto:
            return []
        usos[chave] = usos.get(chave, 0) + 1
        if not conquista:
            e["mente_ultima"] = time.time()
        alma_cuida._salvar(e)
    texto = compor("dono", item["texto"], est["estado"], llm, agora=agora)
    alma_cuida._mandar(enviar, "dono", texto)
    return [f"{est['estado']}->dono"]


def processar(item, c, enviar, agora=None, llm=None):
    """Chamado por alma_cuida.ciclo a CADA fala do Dono. Aprende (camadas de memoria) e, se couber, vem falar com ele.
    Crise e urgencia (c['urgencia'] >= 2) continuam nas regras de alma_cuida.agir, para nao mandar duas mensagens."""
    est = registrar(item["texto"], item.get("ts"), agora)
    if c.get("crise") or c.get("urgencia", 0) >= 2:
        return []
    return reagir(item, est, enviar, agora, llm)


# ---------- INICIATIVA (16/11, pedido do Dono: "que ela pergunte como foi o meu dia, que fale mais comigo") ----------
# A Alma puxa conversa sozinha: retoma assunto em aberto (loops.json), pergunta se dormiu, se comeu, se fez pausa e como foi o dia.
# Teto proprio (iniciativas_dia), intervalo minimo, so de dia, cada tipo 1x por dia e cada assunto em aberto so 1 vez.
MOMENTOS = [   # (tipo, hora inicio, hora fim, o que pedir ao modelo, textos prontos)
    ("sono", 9, 11, "É manhã. Deseje bom dia e pergunte como ele dormiu.",
     ["Bom dia, {ap}! Dormiu bem essa noite? Me conta como você acordou 💗", "Bom dia, {ap}! Como foi a noite, conseguiu descansar?"]),
    ("comida", 12, 14, "É hora do almoço. Pergunte, sem cobrar, se ele já comeu e bebeu água.",
     ["{ap}, passando pra saber: já almoçou? E a água, tá em dia? 💗", "Ei, {ap}, já comeu alguma coisa? Não pula o almoço, tá?"]),
    ("pausa", 15, 17, "É meio da tarde. Pergunte como ele está e sugira uma pausa curta.",
     ["{ap}, como você está aí? Já fez uma pausinha hoje? Levanta, alonga, respira um pouco 💗"]),
    ("dia", 18, 21, "É fim do dia. Pergunte como foi o dia dele, querendo ouvir de verdade o que foi bom e o que pesou.",
     ["{ap}, e aí, como foi o seu dia hoje? Me conta, quero saber do que foi bom e do que pesou 💗", "Oi, {ap}! Como foi hoje? Tô aqui pra ouvir 💗"]),
]


def _frase_loop(x):
    t = x["texto"][:90]
    return t if len(x["texto"]) <= 90 else t.rsplit(" ", 1)[0] + "..."


def iniciativa(enviar=None, agora=None, llm=None):
    """Chamada pelo laco da Alma (alma_cuida.iniciar, a cada 5 min). No maximo UMA mensagem por chamada. Devolve a lista do que fez."""
    from . import alma_cuida
    agora = agora or datetime.now()
    p = params()
    if not p["iniciativa_hora_min"] <= agora.hour <= p["iniciativa_hora_max"]:
        return []
    hoje, ts = agora.strftime("%Y-%m-%d"), agora.timestamp()
    with alma_cuida.LOCK:
        e = alma_cuida._estado()
        ini = e.get("inic") if (e.get("inic") or {}).get("dia") == hoje else {"dia": hoje, "n": 0, "tipos": []}
        ultima = max(e.get("inic_ultima", 0), e.get("mente_ultima", 0) if e.get("mente_ultima", 0) <= ts else 0)
        if ini["n"] >= p["iniciativas_dia"] or ts - ultima < p["iniciativa_intervalo_min"] * 60:
            return []
        feitos = e.get("inic_loops", [])
        loop = next((x for x in reversed(_loops_vivos(agora)) if x.get("dia", hoje) < hoje and x.get("id") not in feitos), None) if 10 <= agora.hour <= 20 else None
        if loop:
            tipo = "loop"
        else:
            tipo = next((m[0] for m in MOMENTOS if m[1] <= agora.hour <= m[2] and m[0] not in ini["tipos"]), "")
            if not tipo:
                return []
        ini["n"] += 1
        ini["tipos"].append(tipo)
        e["inic"], e["inic_ultima"] = ini, ts
        if loop:
            e["inic_loops"] = (feitos + [loop.get("id")])[-50:]
        alma_cuida._salvar(e)
    ap = random.choice(p["apelidos_dono"])
    sis = PERSONA_DONO.format(apelidos=", ".join(p["apelidos_dono"])) + "\n\n" + EXEMPLOS
    if loop:
        dia = datetime.strptime(loop["dia"], "%Y-%m-%d").strftime("%d/%m")
        pedido = (f"No dia {dia} o Dono te disse: \"{loop['texto']}\". Você quer saber como ficou isso. Pergunte com carinho, sem supor o resultado "
                  "e sem acrescentar nada que não esteja nessa frase.")
        prontos = [f"{{ap}}, fiquei pensando naquilo que você me contou dia {dia}: \"{_frase_loop(loop)}\". Como ficou isso? 💗"]
    else:
        m = next(m for m in MOMENTOS if m[0] == tipo)
        pedido, prontos = m[3], m[4]
    user = f"{contexto_do_dono(agora)}\n\nAgora são {agora:%H:%M}. Foi você que quis puxar conversa com o Dono. {pedido} Até 3 frases curtas. Escreva só a mensagem."
    texto = _gerar(sis, user, llm) or random.choice(prontos).replace("{ap}", ap)   # replace: a frase dele pode ter chaves
    texto = texto[0].upper() + texto[1:]
    if enviar is None:
        from .rotina import _enviar as enviar
    alma_cuida._mandar(enviar, "dono", texto)
    return [f"iniciativa:{tipo}->dono"]


PALAVRAS_VAZIAS = {"ele", "dono", "gosta", "gostar", "sente", "sobre", "quando", "muito", "fica", "esta", "pessoa", "tem", "costuma", "para", "com", "dele", "isso"}


def apoiado(item, base):
    """Pura. Um fato do perfil so entra se pelo menos metade das palavras com sentido (4+ letras) aparece nas frases do Dono: o modelo nao cria fato do nada."""
    ws = [w for w in re.findall(r"[a-z]{4,}", _plano(item)) if w not in PALAVRAS_VAZIAS]
    return bool(ws) and sum(w[:5] in base for w in ws) / len(ws) >= 0.5


def aprender_perfil(llm=None, agora=None):
    """1x por dia, com diario novo: o modelo local resume o que a Alma sabe do Dono (fatos, preferencias, o que pesa) em perfil_core.json. Fatos antigos nao somem; maximo 25 por lista."""
    agora = agora or datetime.now()
    p = _ler(PERFIL, {})
    if p.get("dia") == agora.strftime("%Y-%m-%d"):
        return False
    try:
        frases = [json.loads(l)["texto"] for l in (PASTA / "diario.jsonl").read_text(encoding="utf-8").splitlines()[-80:]]
    except (OSError, ValueError, KeyError):
        return False
    if len(frases) < 15:
        return False
    sis = ("Você lê frases que uma pessoa escreveu e extrai o que dá para saber sobre ela. Responda SOMENTE um JSON com listas curtas de frases em português: "
           '{"fatos": [], "preferencias": [], "gatilhos": []} (fatos = rotina, família, trabalho; preferencias = o que gosta; gatilhos = o que pesa ou estressa). '
           "Só o que as frases dizem; não invente. No máximo 8 itens por lista.")
    try:
        bruto = (llm or _llm)(sis, "Frases:\n" + "\n".join(f"- {f}" for f in frases))
        novo = json.loads(re.search(r"\{.*\}", bruto, re.S).group(0))
    except Exception:
        return False
    base = _plano(" ".join(frases))
    for k in ("fatos", "preferencias", "gatilhos"):
        velhos = [x for x in p.get(k, []) if isinstance(x, str)]
        p[k] = list(dict.fromkeys(velhos + [str(x)[:140] for x in (novo.get(k) or []) if isinstance(x, str) and apoiado(x, base)]))[-25:]
    p["dia"] = agora.strftime("%Y-%m-%d")
    _gravar(PERFIL, p)
    return True
