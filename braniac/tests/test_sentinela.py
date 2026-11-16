# -*- coding: utf-8 -*-
import pytest
from braniac import sentinela


def nova(sobe=True):
    eventos = []
    s = sentinela.Sentinela(subir=lambda: eventos.append("subir") or sobe,
                            acordar_servidor=lambda: eventos.append("acordar"),
                            bip=lambda: eventos.append("bip"), falar=lambda t: eventos.append("FALOU:" + t), abrir=lambda: None)
    s.estado = "dormindo"
    return s, eventos


def test_frase_de_acordar_sobe_o_braniac_e_pede_para_acordar():
    s, ev = nova()
    s.tratar_frase("Jarvis, tá acordado?")
    assert ev == ["bip", "subir", "acordar"]          # o vigia NAO fala: quem cumprimenta e o servidor


def test_outras_frases_nao_sobem_nada():
    s, ev = nova()
    for f in ("bom dia", "o dono tá acordado?", "jarvis qual a capital da França"):
        s.tratar_frase(f)
    assert ev == []


def test_se_o_braniac_nao_subir_nao_pede_para_acordar():
    s, ev = nova(sobe=False)
    s.tratar_frase("Jarvis, tá acordado?")
    assert ev == ["bip", "subir"]


def test_nao_sobe_duas_vezes_ao_mesmo_tempo():
    s, ev = nova()
    s._subindo = True
    s.tratar_frase("Jarvis, tá acordado?")
    assert ev == []


def test_subir_braniac_ja_no_ar_nao_abre_outro(monkeypatch):
    chamadas = []
    monkeypatch.setattr(sentinela, "porta_aberta", lambda p: True)
    monkeypatch.setattr(sentinela, "braniac_no_ar", lambda: True)
    monkeypatch.setattr(sentinela.subprocess, "Popen", lambda *a, **k: chamadas.append(a) or None)
    assert sentinela.subir_braniac(esperar_s=2) is True and chamadas == []
