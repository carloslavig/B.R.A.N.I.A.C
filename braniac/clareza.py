# -*- coding: utf-8 -*-
"""CLAREZA (10/11/2026): o Jarvis entender a PERGUNTA e nao responder outra coisa. Tudo barato: so regra, e uma chamada de IA gratis
apenas quando a mensagem e curta e cheia de "isso/ele/ela" (a unica que precisa de contexto).
 1. entender(): reescreve "Ue, Layla falou isso por onde?" como pergunta completa, usando as ultimas mensagens; sem contexto que resolva, manda perguntar.
 2. sem_registro(): "voce sabe o que e o projeto X?" sem nada no banco -> "nao tenho isso", em vez de chutar (caso Ocara, 04/11).
 3. fora_do_assunto()/conferir(): resposta que nao toca em nenhuma palavra da pergunta e refeita UMA vez, com a pergunta em destaque.
 4. polir(): ultimo filtro ANTES de mandar a terceiros no WhatsApp (repeticao, vazamento de Braniac/IAs, textao para pergunta curta).
 5. classificar()/resumo(): classifica as falhas por tipo e conta quantas vezes cada trava agiu (painel /falhas)."""
import json
import re
import time

from . import contexto
from .store import DATA

LOG = DATA / "clareza.jsonl"
VAZA = re.compile(r"(?i)\b(?:braniac|claude|ollama|groq|gemini|chatgpt|openai|conselho\s+de\s+ias?|modelo\s+de\s+linguagem)\b")
STOP = set("para como quando onde porque pois isso essa esse esta este aquilo aquela aquele voce voces tambem ainda muito mais menos sobre entre depois antes "
           "quais qual quem tinha tenho temos pode posso quer quero vamos fazer feito disse falou algo alguma algum nada tudo todas todos mesmo mesma seria "
           "ainda agora hoje ontem dele dela deles delas nele nela comigo conosco aquilo estou estamos ficou fica ficar".split())

ANAFORA = re.compile(r"\b(?:isso|isto|disso|nisso|aquilo|ele|ela|eles|elas|esse|essa|esses|essas|aquele|aquela|desse|dessa|nesse|nessa|l[aá]|assim|"
                     r"o\s+mesmo|a\s+mesma|de\s+novo|por\s+onde|como\s+assim|qual\s+deles|qual\s+delas)\b|^\s*(?:e\s|u[eé]\b|mas\s|ent[aã]o\s)", re.I)
ENTIDADE = re.compile(r"(?i:\b(?:projeto|app|aplicativo|sistema|site|cliente|empresa|loja|contato)\s+(?:chamad[oa]\s+|d[oa]s?\s+)?)([A-ZÀ-Ú][\wÀ-ú-]{2,30})")
PEDE_SABER = re.compile(r"(?i)\?|\bsabe\b|\bconhece\b|\blembra\b|o\s+que\s+[eé]|quem\s+[eé]|\bfalou\s+(?:de|sobre)\b")


def _evento(tipo, detalhe=""):
    try:
        DATA.mkdir(exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time(), "tipo": tipo, "d": str(detalhe)[:120]}, ensure_ascii=False) + "\n")
    except OSError:
        pass


# ---------- 1. entender a pergunta ----------

PERGUNTA = re.compile(r"\?|^\s*(?:u[eé]\b|qual|quais|quem|quando|onde|como|por\s+que|o\s+que|e\s+(?:o|a|os|as)\s|cad[eê])", re.I)


def precisa_reescrever(t):
    """PERGUNTA curta que depende de contexto ('isso', 'ele', 'por onde'...). Pedido/afirmacao ('anota isso') e pergunta completa nao gastam IA."""
    t = (t or "").strip()
    return 2 <= len(t) <= 90 and not t.startswith("/") and bool(PERGUNTA.search(t)) and bool(ANAFORA.search(t))


def _bloco_whatsapp(t_llm):
    m = re.search(r"\[Conversa recente no WhatsApp:(.*?)\]\s*$", t_llm or "", re.S)
    return m.group(1).strip() if m else ""


def contexto_recente(t_llm, historico):
    """Ultimas trocas como texto: o bloco que o dono.py anexa (WhatsApp) ou o historico da conversa (web)."""
    bloco = _bloco_whatsapp(t_llm)
    if bloco:
        return bloco[-700:]
    linhas = [("Dono" if h.get("role") == "user" else "Jarvis") + ": " + (h.get("content") or "")[:180] for h in (historico or [])[-5:]]
    return "\n".join(linhas)[-700:]


REESCREVE = ("Reescreva a ULTIMA mensagem do usuario como uma pergunta COMPLETA e autossuficiente, trocando 'isso/ele/ela/la' pelo que o contexto indica. "
             "Responda SO com a pergunta reescrita, em uma linha, sem explicar. Se a mensagem NAO e uma pergunta (e pedido ou afirmacao), responda exatamente: IGUAL. "
             "Se o contexto NAO deixa claro a que a mensagem se refere, responda exatamente: AMBIGUO")


def reescrever(pergunta, ctx, ia):
    """ia(sistema, texto) -> texto. Devolve a pergunta completa, 'AMBIGUO' ou None (falhou: segue sem reescrita)."""
    try:
        r = ia(REESCREVE, f"CONTEXTO:\n{ctx}\n\nULTIMA MENSAGEM: {pergunta}")
        r = (r[0] if isinstance(r, tuple) else r or "").strip().strip('"')
    except Exception:
        return None
    if not r or "\n" in r or len(r) > 260:
        return None
    if r.upper().startswith("IGUAL"):
        return None
    return "AMBIGUO" if r.upper().startswith("AMBIGUO") else r


def nota_de_contexto(router, t, t_llm, conv):
    """Texto para anexar ao pedido ('' se nao precisa ou nao deu): a pergunta ja resolvida ou o aviso de que e ambigua."""
    if not precisa_reescrever(t) or not hasattr(router, "responder_neutro"):
        return ""
    try:
        hist = router.store.historico(conv, 6) if getattr(router, "store", None) else []
    except Exception:
        hist = []
    ctx = contexto_recente(t_llm, hist)
    if len(ctx) < 20:
        return ""
    r = reescrever(t, ctx, router.responder_neutro)
    if r is None:
        return ""
    if r == "AMBIGUO":
        _evento("ambiguo", t)
        return ("\n\n[ATENCAO: a mensagem do Dono depende do contexto e o contexto NAO esclarece a que ela se refere. "
                "NAO chute: pergunte numa frase curta a que ele se refere.]")
    _evento("reescreveu", f"{t} => {r}")
    return f"\n\n[A PERGUNTA DO DONO, COM O CONTEXTO RESOLVIDO: {r} (responda a esta; nao fuja dela)]"


# ---------- 2. sem dado, sem chute ----------

def sem_registro(t, tem_fato=None):
    """'voce sabe o que e o projeto Ocara?' sem nada no banco -> resposta honesta. None se nao e essa pergunta ou ha registro.
    tem_fato(nome)->bool (por padrao, o banco). So vale para 'projeto/app/sistema/cliente/loja + Nome': conhecimento geral ('o que e Pix') nao entra."""
    t = (t or "").strip()
    m = ENTIDADE.search(t)
    if not m or not PEDE_SABER.search(t) or len(t) > 140:
        return None
    nome = m.group(1)
    if tem_fato is None:
        from . import banco
        tem_fato = lambda n: bool(banco.quem_e(f"quem é {n}"))
    try:
        if tem_fato(nome):
            return None
    except Exception:
        return None
    _evento("sem_registro", nome)
    return f"Não tenho nada registrado sobre {nome}, e prefiro não chutar. Me conta o que é, ou quer que eu pesquise?"


# ---------- 3. resposta que foge do assunto ----------

def _radicais(txt):
    return {w[:5] for w in re.findall(r"[a-zà-ú]{4,}", (txt or "").lower()) if w not in STOP}


def fora_do_assunto(pergunta, resposta):
    """Pergunta com assunto claro (4+ palavras de conteudo) e resposta que nao toca em nenhuma. Pergunta de volta ('...?') nunca e 'fora'."""
    p = _radicais(pergunta)
    r = (resposta or "").strip()
    if len(p) < 4 or len(r) < 40 or r.endswith("?"):
        return False
    return not (p & _radicais(r))


PROMESSA = re.compile(r"\b(?:vou|irei|deixa eu|deixe-me)\s+(?:dar uma\s+)?(?:olhad\w*|checad\w*|conferid\w*|olhar|checar|verificar|conferir|ver)\b"
                      r"[^.!?]{0,60}?\b(?:j[aá]|logo|depois|em seguida)\s+(?:te\s+|lhe\s+)?(?:digo|falo|aviso|retorno|conto|respondo)", re.I)


def so_promessa(texto):
    """16/11: 'Vou dar uma olhada na esteira e já te digo' sem olhar (o Jarvis tinha a ferramenta). Resposta curta que só promete = refazer."""
    t = (texto or "").strip()
    return len(t) < 260 and bool(PROMESSA.search(t))


def conferir(resposta, pergunta, refazer):
    """Resposta fora do assunto ou que só promete olhar depois: refaz UMA vez (refazer(dica)->(texto, e_da_ia)); se a nova tambem nao
    servir, fica com a nova mesmo assim."""
    texto = resposta[0] if isinstance(resposta, tuple) else resposta
    promessa = so_promessa(texto)
    if not promessa and not fora_do_assunto(pergunta, texto):
        return resposta
    _evento("so_promessa" if promessa else "fora_do_assunto", pergunta[:80])
    try:
        nova = refazer(("\n\n[ATENCAO: sua resposta anterior so PROMETEU verificar depois. Use AGORA a ferramenta certa e responda com o dado; "
                        "se nao houver ferramenta para isso, diga o que sabe e o que nao sabe. Nada de 'vou ver e ja te digo'.]") if promessa else
                       f"\n\n[ATENCAO: sua resposta anterior NAO respondeu a pergunta. Responda DIRETAMENTE a: \"{pergunta}\". "
                       f"Se faltar dado, diga que nao tem; nao invente nem mude de assunto.]")
        return nova if nova and (nova[0] if isinstance(nova, tuple) else nova) else resposta
    except Exception:
        return resposta


# ---------- 4. filtro ANTES de mandar a terceiros ----------

FRASES = re.compile(r"(?<=[.!?])\s+")


def _de_casa(nome):
    n = contexto._norm(nome or "")
    casa = {contexto._norm(contexto.contato(k) or "") for k in ("dono", "parceira", "mae")} - {""}
    return n.startswith("dono") or n in casa


def polir(nome, texto, pergunta="", saidas=None):
    """Texto final para um TERCEIRO ou None (nao mandar). Dono, Parceira e Mae passam direto (tom e acesso deles sao outros)."""
    if not (texto or "").strip():
        return None
    if _de_casa(nome):
        return texto
    if pergunta and contexto.agradecimento(pergunta):
        _evento("polir_agradecimento", nome)
        return None
    from . import revisao
    if saidas and len(texto) > 30 and revisao.repete(texto, saidas):      # resposta curta ('Tem sim!') pode se repetir
        _evento("polir_repeticao", nome)
        return None
    frases = FRASES.split(texto.strip())
    if any(VAZA.search(f) for f in frases):
        frases = [f for f in frases if not VAZA.search(f)]
        _evento("polir_vazamento", nome)
        if not frases:
            return None
    saida = " ".join(frases)
    if pergunta and len(pergunta.strip()) <= 40 and len(saida) > 320 and not re.search(r"(?i)detalh|explic|passo|como\s+funciona", pergunta):
        try:
            abertura = contexto.abertura_padrao(nome)      # a apresentacao do 1o contato fica inteira; so o corpo e cortado
        except Exception:
            abertura = ""
        corpo = saida[len(abertura):] if abertura and saida.startswith(abertura) else saida
        fr = FRASES.split(corpo.strip())
        if len(fr) > 2:
            saida = (abertura if corpo is not saida else "") + " ".join(fr[:2])      # corta so ENTRE frases (nunca no meio de uma)
            _evento("polir_tamanho", nome)
    return saida


# ---------- 5. classificar e contar falhas ----------

def classificar(pedido, resposta):
    tipos = []
    if fora_do_assunto(pedido, resposta):
        tipos.append("fora_do_assunto")
    if VAZA.search(resposta or ""):
        tipos.append("vazou_interno")
    if len((pedido or "").strip()) <= 40 and len(resposta or "") > 320:
        tipos.append("exagerou")
    if contexto._QUEM_SOU.search(resposta or ""):
        tipos.append("reapresentou")
    if re.match(r"(?i)\s*sim,", resposta or "") and ENTIDADE.search(pedido or "") and sem_registro(pedido) is not None:
        tipos.append("inventou")
    return tipos or ["outro"]


def _jsonl(arq):
    try:
        return [json.loads(l) for l in arq.read_text(encoding="utf-8").splitlines() if l.strip()]
    except (OSError, ValueError):
        return []


def resumo(dias=7):
    """{marcados: {tipo: n}, claudinho: {tipo: n}, travas: {tipo: n}} dos ultimos `dias`."""
    corte = time.time() - dias * 86400
    marcados, claud, travas = {}, {}, {}
    for e in _jsonl(DATA / "erros_jarvis.jsonl"):
        if float(e.get("ts", 0)) >= corte:
            for tp in e.get("tipos") or classificar(e.get("pedido", ""), e.get("resposta_errada", "")):
                marcados[tp] = marcados.get(tp, 0) + 1
    for a in _jsonl(DATA / "claudinho" / "achados.jsonl"):
        if a.get("ts", 0) >= corte:
            claud[a["tipo"]] = claud.get(a["tipo"], 0) + 1
    for e in _jsonl(LOG):
        if e.get("ts", 0) >= corte:
            travas[e["tipo"]] = travas.get(e["tipo"], 0) + 1
    return {"dias": dias, "marcados": marcados, "claudinho": claud, "travas": travas}


if __name__ == "__main__":
    print(json.dumps(resumo(), ensure_ascii=False, indent=1))
