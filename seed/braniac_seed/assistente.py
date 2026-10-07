# -*- coding: utf-8 -*-
"""O ASSISTENTE em si (tela inicial depois da instalacao): conversa por texto ou voz, com o nome e a voz que a pessoa escolheu, e age no PC
SO dentro das permissoes liberadas.

Como decide: a IA recebe a mensagem (+ um resumo da conversa) e responde um JSON {"acao", "args", "resposta"}. Ela so enxerga as ferramentas que a
pessoa liberou. Acao perigosa (apagar, escrever, rodar comando, enviar WhatsApp) NAO executa direto: vira um cartao 'Confirmar / Cancelar' na tela.
O resultado de uma ferramenta vai para a PESSOA e nunca volta para a IA (nada escondido em arquivo ou mensagem consegue dar ordens).
Modo jogo: com o assistente SUSPENSO ele nao responde nem age (nem pelo Telegram) ate a pessoa retomar."""
import base64, json, re, secrets, threading, time
from . import llm, perfil, permissoes, pc_tools

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
            + "\nSe a pessoa pedir algo que exige uma ferramenta que não está na lista, explique que ela ainda não liberou essa permissão (em Configurações).")


def _contexto():
    if not HISTORICO:
        return ""
    return "Conversa recente:\n" + "\n".join(f"{'Pessoa' if q == 'eu' else _nome()}: {t[:300]}" for q, t in HISTORICO[-8:]) + "\n\nNova mensagem da pessoa: "


def _planejar_padrao(texto):
    bruto, _ = llm.responder(_contexto() + texto, sistema=sistema())
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


def conversar(texto, planejar=None):
    """Devolve {"resposta": str, "imagem": base64png|None, "confirmar": {...}|None, "ui": 'ocultar'|'suspender'|None}."""
    texto = (texto or "").strip()
    if not texto:
        return {"resposta": ""}
    if suspenso():
        return {"resposta": f"{_nome()} está suspenso (modo jogo/edição). Dê dois cliques no orbe para retomar."}
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
    try:
        plano = (planejar or _planejar_padrao)(texto)
    except Exception as e:
        r = "Não consegui falar com nenhuma IA agora. Confira se você conectou ao menos uma chave de API em ⚙ Configurações (ou se o Ollama está instalado e ligado) e tente de novo."
        return {"resposta": r}
    acao, args = plano.get("acao"), plano.get("args") or {}
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
