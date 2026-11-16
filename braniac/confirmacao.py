# -*- coding: utf-8 -*-
"""Entende confirmacao e negacao em linguagem natural ('pode sim', 'manda ai', 'manda ver', 'faca' = sim; 'nem a pau', 'ta maluco?',
'nao e pra mandar' = nao), em vez de exigir '/sim' e '/nao'.

Cuidado: so decide quando a frase e CURTA e e so isso. Uma frase longa ou um pedido novo ('manda um audio pra Parceira dizendo oi')
nunca vale como confirmacao do pedido anterior."""
import re, unicodedata

MAX_PALAVRAS = 8
MARCADORES_DE_PEDIDO = {"pra", "para", "pro", "dizendo", "falando", "avisando", "audio", "mensagem", "msg", "recado", "explicando", "contando"}

NEGATIVAS = [
    "nem fudendo", "nem a pau", "nem pensar", "nem ferrando", "nem morto", "nem por decreto", "nem ligando", "nem a pau",
    "nao e pra", "nao quero", "nao faca", "nao faz", "nao mande", "nao manda", "nao envie", "nao envia", "nao precisa", "nao pode",
    "ta maluco", "esta maluco", "ta doido", "esta doido", "ta louco", "esta louco", "de jeito nenhum", "em hipotese nenhuma",
    "sem chance", "melhor nao", "deixa quieto", "deixa pra la", "deixa isso", "deixa assim", "esquece", "esqueca", "cancela", "cancelar", "cancele",
    "desiste", "desista", "negativo", "jamais", "nunca", "para tudo", "pare tudo", "nao", "nem",
]
PRIMEIRA_PALAVRA_NEGATIVA = {"para", "pare", "chega", "ei", "calma"}     # so valem no INICIO da frase ('para!', 'pare com isso')
POSITIVAS = [
    "pode sim", "pode mandar", "pode enviar", "pode fazer", "pode ir", "pode ser", "pode", "podem ver", "manda ai", "manda ver", "manda bala",
    "manda brasa", "manda", "mande", "faca", "faz", "fazer", "faca isso", "envia", "envie", "executa", "execute", "isso mesmo", "isso",
    "claro", "com certeza", "certeza", "certo", "beleza", "blz", "fechado", "fechou", "bora", "vai la", "vai", "vamos", "positivo",
    "afirmativo", "confirmo", "confirmado", "confirma", "sim senhor", "sim", "ok", "okay", "uhum", "aham", "ta bom", "tudo bem", "combinado",
    "perfeito", "autorizo", "autorizado", "por favor", "senhor",
]


def _normalizar(texto):
    t = "".join(c for c in unicodedata.normalize("NFD", str(texto).lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", t)).strip()


def _primeira_posicao(frases, texto):
    """Posicao (em palavras) da primeira ocorrencia de qualquer frase, ou None."""
    melhor = None
    for f in frases:
        m = re.search(r"(?<![a-z0-9])" + re.escape(f) + r"(?![a-z0-9])", texto)
        if m:
            pos = len(texto[:m.start()].split())
            if melhor is None or pos < melhor:
                melhor = pos
    return melhor


def classificar(texto):
    """'sim', 'nao' ou None (nao e uma resposta de confirmacao)."""
    t = _normalizar(texto)
    palavras = t.split()
    if not palavras or len(palavras) > MAX_PALAVRAS:
        return None
    neg = _primeira_posicao(NEGATIVAS, t)
    if neg is None and palavras[0] in PRIMEIRA_PALAVRA_NEGATIVA:
        neg = 0
    pos = _primeira_posicao(POSITIVAS, t)
    if neg is not None and (pos is None or neg <= pos):
        return "nao"
    if pos is not None:
        if palavras[0] not in ("sim", "pode", "ok", "claro", "isso") and any(p in MARCADORES_DE_PEDIDO for p in palavras):
            return None          # 'manda um audio pra Parceira dizendo oi' e um pedido novo, nao um 'sim'
        return "sim"
    return None
