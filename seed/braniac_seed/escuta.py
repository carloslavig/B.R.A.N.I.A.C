# -*- coding: utf-8 -*-
"""CHAMAR PELO NOME (v0.7): com 'Ouvir meu nome' ligado, a tela de voz escuta o microfone e manda so os trechos com FALA (nao o silencio) para
virar texto pela chave do Google da propria pessoa. Se ouvir '<nome>, ta acordado?' a janela aparece na tela de voz e o assistente conversa
por voz ate ouvir 'pode descansar'. Desligado de fabrica; voz privada ligada = nunca envia audio. Nada e gravado em disco."""
import difflib
import re
import time
import unicodedata
from . import assistente, perfil, transcricao

ESTADO = {"estado": "dormindo", "ultimo": "", "historico": [], "acordou_em": 0.0}
SINAL = {"mostrar": False}
_ULTIMA = [0.0]
CHAMAR = re.compile(r"\b(?:ta|esta|tu ta|voce ta)\s+(?:acordad\w*|ai|on|ligad\w*)\b|\bacorda\w*\b|\bacordou\b|\b(?:oi|ola|ei|hey|e ai)\b", re.I)
DESCANSAR = re.compile(r"\b(?:pode\s+)?(?:descansa\w*|dormir|vai\s+dormir|desliga\w*|ate\s+mais|tchau)\b", re.I)


def _norm(t):
    t = unicodedata.normalize("NFKD", str(t or "").lower())
    return re.sub(r"[^a-z0-9 ]", " ", "".join(c for c in t if not unicodedata.combining(c)))


def ligada():
    p = perfil.carregar()
    return bool(p.get("ouvir_nome")) and not p.get("voz_privada")


def definir(ligar):
    perfil.atualizar(ouvir_nome=bool(ligar))
    ESTADO["estado"] = "dormindo"     # ligar/desligar (ou o botao Descansar) sempre volta a esperar o nome
    return estado()


def _tem_nome(texto, nome):
    alvo = _norm(nome).strip()
    if not alvo:
        return False
    palavras = _norm(texto).split()
    return any(difflib.SequenceMatcher(None, p, alvo).ratio() >= 0.75 for p in palavras) or alvo in _norm(texto)


def chamou(texto, nome):
    """'Luna, ta acordada?' / 'oi Luna' / so 'Luna' -> True."""
    n = _norm(texto).strip()
    return _tem_nome(n, nome) and (bool(CHAMAR.search(n)) or len(n.split()) <= 2)


def _anotar(quem, texto):
    ESTADO["historico"].append((quem, texto))
    del ESTADO["historico"][:-30]


def estado():
    return {"ligada": ligada(), "estado": ESTADO["estado"], "ultimo": ESTADO["ultimo"], "historico": ESTADO["historico"][-12:]}


def frase(audio_b64, conversar=None, transcrever=None):
    """Um trecho de fala do microfone. Devolve {'texto', 'acordou', 'resposta', 'estado', ...}."""
    if not ligada():
        return {"erro": "ouvir o nome está desligado"}
    agora = time.time()
    if agora - _ULTIMA[0] < 0.8:
        return {"ignorado": True}
    _ULTIMA[0] = agora
    try:
        texto = (transcrever or transcricao.transcrever)(audio_b64)
    except transcricao.TranscricaoErro as e:
        return {"erro": str(e)}
    if not texto:
        return {"texto": "", **estado()}
    ESTADO["ultimo"] = texto
    nome = perfil.carregar().get("nome_assistente") or "Assistente"
    if ESTADO["estado"] == "dormindo":
        if not chamou(texto, nome):
            return {"texto": texto, **estado()}
        ESTADO.update(estado="acordado", acordou_em=agora)
        SINAL["mostrar"] = True
        saudacao = "Estou aqui. Em que posso ajudar?"
        _anotar("eu", texto)
        _anotar("ia", saudacao)
        return {"texto": texto, "acordou": True, "resposta": saudacao, **estado()}
    _anotar("eu", texto)
    if DESCANSAR.search(_norm(texto)) and _tem_nome(texto, nome) or re.search(r"\bpode descansar\b", _norm(texto)):
        ESTADO["estado"] = "dormindo"
        r = "Tudo bem, vou descansar. É só me chamar pelo nome."
        _anotar("ia", r)
        return {"texto": texto, "resposta": r, "dormiu": True, **estado()}
    r = (conversar or assistente.conversar)(texto)
    _anotar("ia", r.get("resposta") or "")
    return {"texto": texto, **r, **estado()}


def ler_sinal():
    m, SINAL["mostrar"] = SINAL["mostrar"], False
    return m
