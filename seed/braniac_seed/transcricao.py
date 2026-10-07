# -*- coding: utf-8 -*-
"""Voz -> texto pela chave do Google da propria pessoa (Gemini entende audio). O audio sai do PC SO para o Google, SO quando a pessoa fala com o
microfone, e nada e guardado. Voz privada ligada: nunca envia. Sem chave do Google: a tela tenta o reconhecimento de voz do navegador ou fica so no texto."""
import base64, json, urllib.error, urllib.request
from . import cofre, perfil, voz_nuvem

MODELO = "gemini-flash-latest"
INSTRUCAO = ("Transcreva fielmente o que a pessoa disse neste áudio, em português do Brasil. Responda SOMENTE com o texto falado, sem aspas, sem comentários. "
             "Se não houver fala compreensível, responda exatamente: [inaudível]")


class TranscricaoErro(RuntimeError):
    pass


def disponivel():
    return voz_nuvem.disponivel() and not perfil.carregar().get("voz_privada")


def _post(url, chave, corpo, timeout=45):
    req = urllib.request.Request(url, json.dumps(corpo).encode("utf-8"), {"Content-Type": "application/json", "x-goog-api-key": chave})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def transcrever(wav_b64, post=None, chaves=None):
    if perfil.carregar().get("voz_privada"):
        raise TranscricaoErro("voz privada ligada: o áudio não sai do PC")
    if len(wav_b64) > 8_000_000:
        raise TranscricaoErro("áudio longo demais")
    post = post or _post
    if chaves is None:
        chaves = []
        for c in voz_nuvem.CHAVES_GOOGLE:
            try:
                k = cofre.ler(c)
            except cofre.CofreErro:
                k = None
            if k:
                chaves.append(k)
    if not chaves:
        raise TranscricaoErro("sem chave do Google")
    corpo = {"contents": [{"parts": [{"text": INSTRUCAO}, {"inline_data": {"mime_type": "audio/wav", "data": wav_b64}}]}]}
    erro = None
    for k in chaves:
        try:
            d = post(f"https://generativelanguage.googleapis.com/v1beta/models/{MODELO}:generateContent", k, corpo)
            txt = d["candidates"][0]["content"]["parts"][0]["text"].strip()
            return "" if txt.lower().startswith("[inaud") else txt
        except urllib.error.HTTPError as e:
            erro = "cota do Google esgotada agora" if e.code == 429 else f"o Google respondeu {e.code}"
        except Exception as e:
            erro = str(e)[:80]
    raise TranscricaoErro(erro or "falhou")
