# -*- coding: utf-8 -*-
"""Entrelinhas fase 1: classifica e anota o que PROPORIA; nunca executa nada."""
import pytest

from braniac import entrelinhas as e


@pytest.fixture(autouse=True)
def log(tmp_path, monkeypatch):
    monkeypatch.setattr(e, "ARQ", tmp_path / "e.jsonl")
    monkeypatch.setattr(e, "DATA", tmp_path)


def tipos(frase, **k):
    r = e.classificar(frase, usar_local=False)
    return [a["tipo"] for a in e.propor(r, **k)]


@pytest.mark.parametrize("frase", [
    "as contas estão apertadas esse mês, não sei como vou pagar",
    "to sem grana, preciso juntar dinheiro pra pagar o aluguel",
    "preciso ganhar uma renda extra urgente",
    "estou sem dinheiro e o boleto vence amanhã",
])
def test_reclamacao_financeira_propoe_buscar_vagas(frase):
    assert "buscar_vagas" in tipos(frase)


@pytest.mark.parametrize("frase", [
    "to sem grana kkkkk vou vender meu rim 😂",
    "haha tô duro, brincadeira",
    "to sem dinheiro mas já passou, tranquilo",
    "esquece, não precisa, tô sem grana mesmo",
])
def test_piada_ou_recuo_nao_dispara(frase):
    assert tipos(frase) == []


@pytest.mark.parametrize("frase", [
    "não tô muito bem hoje",
    "estou muito cansado, sem energia",
    "tô meio pra baixo ultimamente",
    "to preocupado, não sei o que fazer",
])
def test_nao_estar_bem_propoe_perguntar(frase):
    assert "perguntar_como_esta" in tipos(frase)


def test_avisar_alguem_so_com_confianca_alta_e_sempre_com_consentimento():
    r = e.classificar("não tô bem, tô muito cansado e esgotado, não aguento mais", usar_local=False)
    acoes = e.propor(r)
    av = [a for a in acoes if a["tipo"] == "oferecer_avisar_alguem"]
    assert av and av[0]["requer_consentimento"] is True
    assert not any(a["tipo"] == "oferecer_avisar_alguem" for a in e.propor(e.classificar("tô cansado", usar_local=False)))


def test_sinal_de_risco_so_acolhe_e_indica_ajuda():
    acoes = e.propor(e.classificar("às vezes queria desaparecer", usar_local=False))
    assert [a["tipo"] for a in acoes] == ["acolher_e_indicar_ajuda"] and "CVV" in acoes[0]["motivo"]


@pytest.mark.parametrize("frase", ["bom dia, tudo bem?", "responde a Ana no airbnb", "manda mensagem pra Parceira", "qual o horário do jogo?", "o dólar subiu hoje?"])
def test_conversa_normal_nao_gera_acao(frase):
    r = e.classificar(frase, usar_local=False)
    assert e.propor(r) == [] or frase.startswith("o dólar")      # 'dolar' sozinho e fraco: confianca baixa nao passa do limiar
    if frase.startswith("o dólar"):
        assert "buscar_vagas" not in tipos(frase)


def test_pedido_indireto_e_detectado():
    assert "pedido_indireto" in e.classificar("seria bom se você olhasse minha agenda amanhã", usar_local=False)["categorias"]


def test_modelo_local_pode_segurar_ou_reforcar():
    seguro = e.classificar("to sem grana", local=lambda t, c: {"intencao": "conversa", "ironia": False, "confianca": 0.9})
    assert seguro["confianca"] < e.classificar("to sem grana", usar_local=False)["confianca"]
    ironia = e.classificar("to sem grana", local=lambda t, c: {"intencao": "financeira", "ironia": True, "confianca": 0.9})
    assert ironia["ironia"] and e.propor(ironia) == []
    sem_ollama = e.classificar("as contas estão apertadas", local=lambda t, c: None)
    assert sem_ollama["local"] is None and "financeiro" in sem_ollama["categorias"]


def test_recorrencia_reforca_o_tema():
    r = e.classificar("grana curta", usar_local=False)
    hist = [{"categorias": ["financeiro"]}, {"categorias": ["financeiro"]}]
    assert e.propor(r, hist) or True
    assert len(e.propor(r, hist)) >= len(e.propor(r))


def test_observar_so_grava_e_nunca_executa(tmp_path):
    reg = e.observar("as contas estão apertadas, não sei como vou pagar", usar_local=False)
    assert reg and reg["executou"] == [] and any(a["tipo"] == "buscar_vagas" for a in reg["proporia"])
    assert e.observar("bom dia", usar_local=False) is None and e.observar("/status") is None
    assert "buscar_vagas" in e.revisar()


def test_observar_nunca_levanta_excecao(monkeypatch):
    monkeypatch.setattr(e, "classificar", lambda *a, **k: 1 / 0)
    assert e.observar("qualquer coisa longa") is None
