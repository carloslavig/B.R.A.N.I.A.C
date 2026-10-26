# -*- coding: utf-8 -*-
"""O ASSISTENTE em si (tela inicial depois da instalacao): conversa por texto ou voz, com o nome e a voz que a pessoa escolheu, e age no PC
SO dentro das permissoes liberadas.

Como decide: a IA recebe a mensagem (+ um resumo da conversa) e responde um JSON {"acao", "args", "resposta"}. Ela so enxerga as ferramentas que a
pessoa liberou. Acao perigosa (apagar, escrever, rodar comando, enviar WhatsApp) NAO executa direto: vira um cartao 'Confirmar / Cancelar' na tela.
O resultado de uma ferramenta vai para a PESSOA e nunca volta para a IA (nada escondido em arquivo ou mensagem consegue dar ordens).
Modo jogo: com o assistente SUSPENSO ele nao responde nem age (nem pelo Telegram) ate a pessoa retomar."""
import base64, json, re, secrets, threading, time
from . import assinatura, auto_update, habilidades, modulos, llm, memoria_usuario, orquestrador, perfil, permissoes, pc_tools, projetos

HISTORICO = []                 # ultimas trocas desta sessao: [("eu"|"ia", texto)]
PENDENTES = {}                 # id -> {"acao", "args", "ate"}
_lock = threading.Lock()
VALIDADE_CONFIRMACAO_S = 300


def suspenso():
    return bool(perfil.carregar().get("suspenso"))


def definir_suspenso(ligado):
    perfil.atualizar(suspenso=bool(ligado))
    if ligado:
        with _lock:
            PENDENTES.clear()
    return bool(ligado)


def _nome():
    p = perfil.carregar()
    return p.get("nome_assistente") or "Assistente"


def sistema():
    p = perfil.carregar()
    nome = _nome()
    cat = pc_tools.catalogo_para_ia()
    return (f"Você é {nome}, o assistente pessoal de IA de {p.get('nome_pessoa') or 'seu dono'}, conversando por voz e texto no computador dele (Windows). "
            "Fale em português do Brasil, de forma natural, educada e CURTA (1 a 3 frases quando for conversa). Nunca invente fatos, resultados ou o que aconteceu no PC: "
            "se não souber, diga que não sabe. Converta o pedido em UMA ação quando for o caso. Responda SOMENTE um JSON: "
            '{"acao": "<nome da ferramenta ou nenhuma>", "args": {...}, "resposta": "frase curta para a pessoa"}. '
            "Use 'nenhuma' para conversa comum (coloque a fala em 'resposta'). Ferramentas liberadas pela pessoa:\n" + (cat or "(nenhuma: a pessoa não liberou acesso ao PC, então só converse)")
            + "\nSe a pessoa pedir algo que exige uma ferramenta que não está na lista, explique que ela ainda não liberou essa permissão (em Configurações)."
            + "\nAções extras (sempre liberadas): 'orquestrar' (args: {\"tarefa\": ...}) divide uma tarefa GRANDE ou com várias partes entre várias IAs ao mesmo "
            "tempo e junta o resultado; 'usar_habilidade' (args: {\"nome\": ...}) carrega o passo a passo de uma habilidade quando o pedido combina com ela. "
            "Habilidades: " + (habilidades.catalogo() or "nenhuma")
            + "\nNunca invente nomes, números, datas, preços ou o que foi combinado: use só o que a pessoa disse ou o que está na memória; se não tiver, diga que não sabe."
            + modulos.ferramentas_texto() + assinatura.PROMPT + memoria_usuario.contexto())


def _contexto(hist=None):
    hist = HISTORICO if hist is None else hist
    if not hist:
        return ""
    return "Conversa recente:\n" + "\n".join(f"{'Pessoa' if q == 'eu' else _nome()}: {t[:300]}" for q, t in hist[-8:]) + "\n\nNova mensagem da pessoa: "


def _planejar_padrao(texto, extra="", hist=None):
    extra = extra + modulos.contexto_para(texto)      # v1.1: so o agente do modulo detectado entra no prompt (custo minimo)
    bruto, _ = llm.responder(_contexto(hist) + texto, sistema=sistema() + extra)
    m = re.search(r"\{.*\}", bruto, re.S)
    if not m:
        return {"acao": "nenhuma", "args": {}, "resposta": bruto.strip()[:1500]}
    try:
        d = json.loads(m.group(0))
    except ValueError:
        return {"acao": "nenhuma", "args": {}, "resposta": bruto.strip()[:1500]}
    return {"acao": d.get("acao", "nenhuma"), "args": d.get("args") or {}, "resposta": str(d.get("resposta") or "")[:1500]}


def _lembrar(papel, texto):
    HISTORICO.append((papel, texto))
    del HISTORICO[:-20]


COMANDOS_LOCAIS = [
    (re.compile(r"^\s*(?:pode\s+)?(?:descansar|dormir|vai\s+dormir|descansa)\b", re.I), "ocultar"),
    (re.compile(r"\bmodo\s+jogo\b|\bvou\s+(?:jogar|editar)\b|\bsuspend\w+\b", re.I), "suspender"),
]


ATUALIZAR = re.compile(r"\batualiz(?:ar|a|e)\s+(?:agora|o\s+braniac|a\s+vers[aã]o|ele)\b|\bverifi\w*\s+atualiza|\bprocur\w*\s+atualiza|\bhá\s+atualiza", re.I)
AUTO_OFF = re.compile(r"\b(?:desligu?e|desativ\w+|pare|p[aá]ra)\b.*\batualiza[cç][aã]o\s+autom", re.I)
AUTO_ON = re.compile(r"\b(?:ligu?e|ativ\w+)\b.*\batualiza[cç][aã]o\s+autom", re.I)


def _comando_atualizacao(texto):
    """Comandos locais (sem IA): ligar/desligar a atualizacao automatica e atualizar agora."""
    if AUTO_OFF.search(texto):
        auto_update.definir(False)
        return "Pronto, desliguei a atualização automática. Você pode pedir 'atualizar agora' quando quiser."
    if AUTO_ON.search(texto):
        auto_update.definir(True)
        return "Pronto, a atualização automática está ligada."
    if ATUALIZAR.search(texto):
        return auto_update.checar_e_atualizar()
    return None


def conversar(texto, planejar=None, conversa=None):
    """Devolve {"resposta": str, "imagem": base64png|None, "confirmar": {...}|None, "ui": 'ocultar'|'suspender'|None}.
    conversa = id de uma conversa de projeto (v0.7): historico proprio + instrucoes do projeto; None = conversa geral (voz, Telegram)."""
    texto = (texto or "").strip()
    if not texto:
        return {"resposta": ""}
    if assinatura.responder(texto):          # assinatura digital: deusa e mestres supremos, igual em todo Braniac
        return {"resposta": assinatura.RESPOSTA}
    if suspenso():
        return {"resposta": f"{_nome()} está suspenso (modo jogo/edição). Dê dois cliques no orbe para retomar."}
    if conversa is not None:
        return _conversar_projeto(texto, planejar, int(conversa))
    _lembrar("eu", texto)
    for rx, ui in COMANDOS_LOCAIS:
        if rx.search(texto):
            if ui == "suspender":
                definir_suspenso(True)
                r = f"Entendido. Estou suspenso para você usar o computador sem interrupções. Para me chamar de volta, dê dois cliques no meu orbe."
            else:
                r = "Tudo bem, vou descansar. Me chama quando precisar."
            _lembrar("ia", r)
            return {"resposta": r, "ui": ui}
    r = _comando_atualizacao(texto)
    if r:
        _lembrar("ia", r)
        return {"resposta": r}
    r = memoria_usuario.tratar(texto)
    if r:
        _lembrar("ia", r)
        return {"resposta": r}
    try:
        plano = (planejar or _planejar_padrao)(texto)
    except Exception as e:
        r = "Não consegui falar com nenhuma IA agora. Confira se você conectou ao menos uma chave de API em ⚙ Configurações (ou se o Ollama está instalado e ligado) e tente de novo."
        return {"resposta": r}
    acao, args = plano.get("acao"), plano.get("args") or {}
    especial = _acao_especial(acao, args, texto, planejar)
    if especial is not None:
        _lembrar("ia", especial.get("resposta") or "")
        return especial
    if acao in (None, "", "nenhuma") or acao not in pc_tools.FERRAMENTAS:
        r = plano.get("resposta") or "Não entendi. Pode explicar de outro jeito?"
        _lembrar("ia", r)
        return {"resposta": r}
    try:
        permissoes.exigir(pc_tools.FERRAMENTAS[acao][2])
    except permissoes.PermissaoNegada as e:
        r = f"{e} Você pode liberar isso em Configurações › Acesso ao PC."
        _lembrar("ia", r)
        return {"resposta": r}
    if pc_tools.precisa_confirmar(acao):
        cid = secrets.token_hex(4)
        with _lock:
            PENDENTES[cid] = {"acao": acao, "args": args, "ate": time.time() + VALIDADE_CONFIRMACAO_S}
        r = plano.get("resposta") or "Preciso da sua confirmação."
        _lembrar("ia", r)
        return {"resposta": r, "confirmar": {"id": cid, "descricao": pc_tools.descrever(acao, args)}}
    return _executar(acao, args, plano.get("resposta"))


def _acao_especial(acao, args, texto, planejar=None, hist=None, extra=""):
    """'orquestrar' e 'usar_habilidade' (v0.7) e as ferramentas dos modulos instalados (v1.1). Devolve a resposta, ou None se nao for uma delas."""
    if acao and modulos.eh_ferramenta(acao):
        return {"resposta": modulos.executar(acao, args)}
    if acao == "orquestrar":
        try:
            o = orquestrador.orquestrar(args.get("tarefa") or texto)
        except Exception as e:
            return {"resposta": f"Não consegui orquestrar as IAs agora ({str(e)[:120]})."}
        quem = ", ".join(sorted({q for _, q in o["partes"]}))
        return {"resposta": o["resposta"][:3900] + (f"\n\n(feito em {len(o['partes'])} partes por: {quem})" if len(o["partes"]) > 1 else "")}
    if acao == "usar_habilidade":
        passos = habilidades.carregar(args.get("nome"))
        if not passos:
            return None
        if planejar is not None:
            plano = planejar(texto)
        else:
            plano = _planejar_padrao(texto, extra + "\n\nSiga esta habilidade:\n" + passos[:6000], hist)
        if plano.get("acao") == "orquestrar":
            return _acao_especial("orquestrar", plano.get("args") or {}, texto)
        if plano.get("acao") in pc_tools.FERRAMENTAS:
            return None     # a habilidade levou a uma ferramenta do PC: segue o fluxo normal (permissoes/confirmacao)
        return {"resposta": plano.get("resposta") or "Pronto."}
    return None


def _conversar_projeto(texto, planejar, conversa):
    """Conversa de projeto: mesma logica, com historico e instrucoes proprios; as falas ficam guardadas na conversa."""
    nome_proj, instr = projetos.instrucoes(conversa)
    if nome_proj is None:
        return {"resposta": "Essa conversa não existe mais."}
    hist = projetos.historico(conversa, 16)
    projetos.anotar(conversa, "eu", texto)
    extra = f"\n\nProjeto atual: {nome_proj}." + (f" Instruções do projeto (siga sempre): {instr[:3000]}" if instr.strip() else "")
    try:
        plano = planejar(texto) if planejar else _planejar_padrao(texto, extra, hist)
    except Exception:
        r = {"resposta": "Não consegui falar com nenhuma IA agora. Confira suas chaves em ⚙ Configurações (ou o Ollama) e tente de novo."}
        projetos.anotar(conversa, "ia", r["resposta"])
        return r
    acao, args = plano.get("acao"), plano.get("args") or {}
    r = _acao_especial(acao, args, texto, planejar, hist, extra)
    if r is None and acao in pc_tools.FERRAMENTAS:
        try:
            permissoes.exigir(pc_tools.FERRAMENTAS[acao][2])
            if pc_tools.precisa_confirmar(acao):
                cid = secrets.token_hex(4)
                with _lock:
                    PENDENTES[cid] = {"acao": acao, "args": args, "ate": time.time() + VALIDADE_CONFIRMACAO_S}
                r = {"resposta": plano.get("resposta") or "Preciso da sua confirmação.", "confirmar": {"id": cid, "descricao": pc_tools.descrever(acao, args)}}
            else:
                r = _executar(acao, args, plano.get("resposta"))
        except permissoes.PermissaoNegada as e:
            r = {"resposta": f"{e} Você pode liberar isso em Configurações › Acesso ao PC."}
    if r is None:
        r = {"resposta": plano.get("resposta") or "Não entendi. Pode explicar de outro jeito?"}
    projetos.anotar(conversa, "ia", r.get("resposta") or "")
    return r


def _executar(acao, args, fala=None):
    try:
        texto, imagem = pc_tools.executar_ferramenta(acao, args)
    except (permissoes.PermissaoNegada, pc_tools.FerramentaErro) as e:
        _lembrar("ia", str(e))
        return {"resposta": f"🚫 {e}"}
    except Exception as e:
        return {"resposta": f"Deu erro ao executar: {str(e)[:200]}"}
    _lembrar("ia", (fala or "") + " [" + acao + " executado]")
    return {"resposta": (texto or fala or "Pronto.")[:3900], "imagem": base64.b64encode(imagem).decode() if imagem else None}


def confirmar(cid, sim):
    with _lock:
        pend = PENDENTES.pop(cid, None)
    if not pend or time.time() > pend["ate"]:
        return {"resposta": "Essa confirmação expirou. Peça de novo."}
    if not sim:
        return {"resposta": "Cancelado. Nada foi feito."}
    if suspenso():
        return {"resposta": "Estou suspenso: nada foi executado."}
    return _executar(pend["acao"], pend["args"])
