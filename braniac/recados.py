# -*- coding: utf-8 -*-
"""RECADOS PARA O DONO (correcao de 13/10/2026): o Jarvis prometia 'vou passar pro Dono' e o recado nao chegava, ou chegava truncado/trocado por uma
interpretacao. Agora, SEM IA no caminho: sempre que (a) o Jarvis decide avisar/segurar (A/P) ou (b) a resposta enviada PROMETE repassar algo, o recado
entra numa FILA em disco com as palavras LITERAIS da pessoa (inclusive transcricao de audio) e e entregue ao Dono no WhatsApp; se o envio falhar, a fila
tenta de novo a cada ciclo da rotina (nada se perde). Um recado por pessoa e mensagem (sem repetir)."""
import hashlib
import json
import re
import time

from .store import DATA

ARQ = DATA / "recados.json"
MAX_TENTATIVAS = 6
MAX_CHARS = 700

# frases com que o Jarvis PROMETE repassar/avisar o Dono (ou diz que ele vai retornar)
PROMESSA = re.compile(
    r"(?:vou|vamos|irei|iremos|j[aá]\s+vou|posso)\s+(?:logo\s+)?(?:passar|repassar|avisar|informar|comunicar|encaminhar|levar|contar|dizer|falar|deixar\s+(?:o\s+)?recado|anotar|registrar|transmitir|mandar|enviar)\b[^.!?\n]{0,40}\b(?:dono|ele|pra\s+ele|para\s+ele)\b|"
    r"(?:passei|passo|repassei|repasso|avisei|aviso|informei|comuniquei|encaminhei|anotei|registrei|deixei|transmiti|mandei)\b[^.!?\n]{0,40}\b(?:dono|ele|recado|mensagem|pedido)\b|"
    r"(?:anotei|registrei|deixei)\s+(?:o\s+|seu\s+|esse\s+|este\s+)?(?:recado|pedido|aviso)|"
    r"(?:o\s+)?dono\s+(?:vai|ir[aá]|j[aá]|logo)\s+(?:ver|saber|retornar|te\s+(?:responder|ligar|chamar|retornar|procurar)|entrar\s+em\s+contato|falar\s+com\s+voc[eê])|"
    r"ele\s+(?:vai|ir[aá])\s+(?:ver|saber|retornar|te\s+(?:responder|ligar|chamar|retornar|procurar)|entrar\s+em\s+contato)|"
    r"pode\s+deixar\s+que\s+(?:eu\s+)?(?:aviso|passo|falo|aviso\s+o|repasso|digo)|"
    r"(?:avisarei|repassarei|informarei|comunicarei|encaminharei)\b|"
    r"(?:aviso|digo|repasso|falo)\s+(?:pra|para)\s+(?:ele|o\s+dono)|"
    r"recado\s+(?:anotado|registrado|repassado|enviado)",
    re.I)


_CUE = re.compile(r"\b(?:vou|vo|vamos|vamo|irei|iremos|ja|j[aá]|jah|pode\s+dex\w*|pode\s+deixa\w*|deixa|dexa|a\s+gente|agente|tamo|estou|to|t[aá]|ta|passei|passo|avisei|aviso|anotei|anotado|notei|registrei|repasso|repassei|informo|encaminho|mando|envio)\b", re.I)
_VERBO = re.compile(r"(?:pass[aoe]|repass|avis|inform|comunic|encaminh|dar\s+(?:o|um)\s+(?:recado|toque)|dou\s+(?:o|um)\s+(?:recado|toque)|mand[aeo]|envi[aeo]|anot|regist|notei|dexa|deix|fal[ao]|fald|dig[ao]|diz|cont[ao]|transmit|entreg|pedir|pe[cç]o)", re.I)
_ALVO = re.compile(r"\b(?:dono|ele|ela|chefe|dono|recado|mensagem|msg|pedido|aviso)\b", re.I)
_RETORNO = re.compile(r"\b(?:ele|ela|dono|a\s+gente|agente|gente)\b[^.!?\n]{0,25}\b(?:retorn|respond|cham[ae]|lig[ae]|entra\s+em\s+contato|procur|volta|fala\s+com\s+voc)", re.I)
_RETORNO2 = re.compile(r"\b(?:retorn|respond|cham|lig)\w*\b[^.!?\n]{0,15}\b(?:assim\s+que|logo\s+que)\b", re.I)


def promete_repassar(resposta):
    """True se a resposta PROMETE repassar recado ou diz que o Dono vai retornar. Por frase: (1a pessoa/futuro + verbo de repassar + alvo) ou 'ele/a gente ... retorna'."""
    if PROMESSA.search(resposta or ""):
        return True
    for frase in re.split(r"[.!?\n]+", resposta or ""):
        if _CUE.search(frase) and _VERBO.search(frase) and _ALVO.search(frase):
            return True
        if _RETORNO.search(frase) or _RETORNO2.search(frase):
            return True
    return False


def _ler():
    try:
        return json.loads(ARQ.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _gravar(fila):
    DATA.mkdir(exist_ok=True)
    ARQ.write_text(json.dumps(fila[-300:], ensure_ascii=False, indent=1), encoding="utf-8")


def _chave(nome, entrada):
    return hashlib.sha1((nome + "|" + re.sub(r"\s+", " ", entrada).strip().lower()).encode("utf-8")).hexdigest()[:16]


def formatar(nome, entrada, resposta="", nota=""):
    corpo = re.sub(r"[ \t]+", " ", entrada).strip()
    if len(corpo) > MAX_CHARS:
        corpo = corpo[:MAX_CHARS].rstrip() + "…"
    linhas = [f"📩 Recado de {nome}:", f"«{corpo}»"]
    if nota:
        linhas.append(f"Obs. do Jarvis: {nota.strip()[:160]}")
    elif resposta:
        linhas.append(f"Jarvis respondeu: «{resposta.strip()[:140]}»")
    return "\n".join(linhas)


def enfileirar(nome, entrada, resposta="", nota="", agora=None):
    """Guarda o recado (uma vez por pessoa+mensagem). Devolve True se entrou na fila agora."""
    entrada = (entrada or "").strip()
    if not nome or not entrada:
        return False
    k = _chave(nome, entrada)
    fila = _ler()
    if any(r["k"] == k for r in fila):
        return False
    fila.append({"k": k, "nome": nome, "texto": formatar(nome, entrada, resposta, nota), "entrada": entrada[:MAX_CHARS], "resposta": (resposta or "")[:300], "ts": agora or time.time(), "estado": "pendente", "tentativas": 0})
    _gravar(fila)
    return True


def pendentes():
    return [r for r in _ler() if r["estado"] == "pendente"]


def entregar(enviar, destino, audio=None):
    """Envia os recados pendentes ao Dono. enviar(destino, texto) -> str ('✅...' se enviou).
    Com `audio(destino, fala)`: UM áudio por pessoa, em tom de conversa (recado_falado); se o áudio falhar, cai no texto de sempre.
    Devolve quantos recados foram entregues."""
    fila = _ler()
    n = 0
    if audio:
        por_pessoa = {}
        for r in fila:
            if r["estado"] == "pendente":
                por_pessoa.setdefault(r["nome"], []).append(r)
        for nome, rs in por_pessoa.items():
            try:
                from . import recado_falado
                fala = recado_falado.roteiro(nome, [r.get("entrada") or r["texto"] for r in rs], [r["resposta"] for r in rs if r.get("resposta")])
                res = str(audio(destino, fala))
            except Exception as e:
                res = f"erro {e!r}"
            if res.startswith("✅"):
                for r in rs:
                    r["estado"], r["entregue_em"] = "entregue", time.time()
                n += len(rs)
    for r in fila:
        if r["estado"] != "pendente":
            continue
        try:
            res = str(enviar(destino, r["texto"]))
        except Exception as e:
            res = f"erro {e!r}"
        r["tentativas"] += 1
        if res.startswith("✅"):
            r["estado"], r["entregue_em"] = "entregue", time.time()
            n += 1
        elif r["tentativas"] >= MAX_TENTATIVAS:
            r["estado"] = "falhou"
        else:
            break              # WhatsApp indisponivel: para e tenta no proximo ciclo (mantem a ordem)
    _gravar(fila)
    return n
