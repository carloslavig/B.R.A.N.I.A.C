# -*- coding: utf-8 -*-
"""Narracao de video: a voz nao pode trocar no meio (Dono Estudio, 13/11/2026)."""
import io
import wave

from braniac import voz


def _wav(n=100):
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(b"\0\0" * n)
    return b.getvalue()


def test_motor_que_falha_no_meio_e_descartado_inteiro(monkeypatch):
    usados = []

    def gemini(p, modelos=None, **k):
        usados.append("gemini")
        if len([u for u in usados if u == "gemini"]) == 2:   # falha no 2o trecho
            raise RuntimeError("sem cota")
        return _wav()

    def edge(p, **k):
        usados.append("edge")
        return _wav()

    monkeypatch.delenv("BRANIAC_VOZ_RAFAEL", raising=False)
    monkeypatch.setattr(voz, "_eleven_wav", lambda p: (_ for _ in ()).throw(RuntimeError("sem chave")))
    monkeypatch.setattr(voz, "_gemini_wav", gemini)
    monkeypatch.setattr(voz, "_edge_wav", edge)
    monkeypatch.setattr(voz, "_cfg_voz", lambda: {"nome": "Achird", "modelos": ["m1"], "estilo": ""})
    monkeypatch.setattr(voz, "mais_grave", lambda w: w)
    texto = " ".join(["Frase de teste com tamanho razoavel para encher o trecho."] * 40)   # ~2300 caracteres = varios trechos
    wav, motor = voz.falar_wav_voz_unica(texto)
    assert motor == "edge"
    n = len(voz._partes(texto))
    assert n >= 3
    assert usados == ["gemini", "gemini"] + ["edge"] * n   # o edge refez TUDO; nada do gemini sobrou
    with wave.open(io.BytesIO(wav)) as r:
        assert r.getnframes() == 100 * n
