# -*- coding: utf-8 -*-
"""CHAMAR O JARVIS PELO CELULAR (24/10/2026): o app manda so os trechos com FALA (WAV 16 kHz); aqui o Whisper local transcreve, '<nome>, ta acordado?'
acorda e o Jarvis conversa por voz ate ouvir 'pode descansar' (ou 3 min sem falar). A resposta volta em texto + WAV (a mesma voz do notebook).
Mesma conversa de voz ('voz') do PC. Nada do audio e guardado: o arquivo temporario e apagado na hora."""
import base64
import os
import tempfile
import time

from . import escuta, voz

ESTADO = {"acordado": False, "ultima": 0.0}
IDLE_S = 180


def _tocar_texto(resp):
    try:
        return base64.b64encode(voz.falar_wav(resp[:600], rapido=True)).decode()
    except Exception:
        return ""       # sem voz agora: o app mostra so o texto


def fala(router, wav_b64, tratar=None, transcrever=None):
    """Um trecho de fala. Devolve {'texto','estado','resposta'?,'audio'?}."""
    agora = time.time()
    if ESTADO["acordado"] and agora - ESTADO["ultima"] > IDLE_S:
        ESTADO["acordado"] = False
    if transcrever is None:
        fd, caminho = tempfile.mkstemp(suffix=".wav")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(base64.b64decode(wav_b64))
            texto = voz.transcrever(caminho, rapido=True)
        finally:
            try:
                os.unlink(caminho)
            except OSError:
                pass
    else:
        texto = transcrever(wav_b64)
    texto = (texto or "").strip()
    if len(texto) < 2:
        return {"texto": "", "estado": "acordado" if ESTADO["acordado"] else "dormindo"}
    if not ESTADO["acordado"]:
        if not escuta.quer_acordar(texto):
            return {"texto": texto, "estado": "dormindo"}
        ESTADO.update(acordado=True, ultima=agora)
        r = "Estou aqui, Dono. Em que posso ajudar?"
        return {"texto": texto, "estado": "acordado", "acordou": True, "resposta": r, "audio": _tocar_texto(r)}
    ESTADO["ultima"] = agora
    if escuta.quer_descansar(texto):
        ESTADO["acordado"] = False
        r = "Tudo bem, vou descansar. É só me chamar."
        return {"texto": texto, "estado": "dormindo", "resposta": r, "audio": _tocar_texto(r)}
    from . import jarvis
    resp = (tratar or (lambda t: jarvis.processar(router, t, "voz", None, origem="web")[0]))(texto)
    return {"texto": texto, "estado": "acordado", "resposta": resp, "audio": _tocar_texto(resp)}
