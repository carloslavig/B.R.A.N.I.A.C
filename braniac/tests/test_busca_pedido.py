import pytest

from braniac import busca_maps as m
from braniac import busca_pedido as b

AUDIO = ("Você não tem como procurar ver para mim quanto é o resto da nossa magnética do Ombro Direito em Itabuna. Para ver se tem umas clínicas que façam mais de valores para mim.")
CARTAO = {"nome": "Multimagem Pontalzinho: Ressonância Magnética, Itabuna BA", "url": "https://www.google.com/maps/place/X/data=!4m7",
          "texto": "Multimagem Pontalzinho\n4,9(420)\nCentro de diagnóstico médico por imagem ·  · R. Antônio Muniz, 200\nAberto · Fecha 23:00 · (73) 3043-0000\n\nWebsite\n\nRotas"}
CLINICA_ZAP = {"nome": "Clínica Zap", "url": "", "nota": "4,5", "endereco": "Rua A, 1", "telefone": "(73) 99876-5432", "site": False}
CLINICA_FIXO = {"nome": "Clínica Fixo", "url": "", "nota": None, "endereco": None, "telefone": "(73) 3043-0000", "site": True}


@pytest.fixture(autouse=True)
def isolado(tmp_path, monkeypatch):
    monkeypatch.setattr(b, "PEDIDOS", tmp_path / "pedidos.json")
    monkeypatch.setattr(b, "CONTATOS", tmp_path / "contatos.json")
    monkeypatch.setattr(b, "_fn_ia", lambda t: "ressonância magnética ombro direito preço Itabuna")
    yield
    b._fn_nivel = b._fn_lugares = b._fn_pesquisar = None


def test_reconhece_pedido_de_busca_e_ignora_conversa():
    assert b.eh_pedido(AUDIO)
    assert not b.eh_pedido("Hoje dormi bem, mas o braço dói muito e o pescoço também, tia cansada")
    assert not b.eh_pedido("ok")


def test_maps_interpreta_cartao_e_distingue_celular_de_fixo():
    c = m.interpretar(CARTAO)
    assert c["telefone"] == "(73) 3043-0000" and c["nota"] == "4,9" and c["endereco"] == "R. Antônio Muniz, 200" and c["site"]
    assert m.whatsapp_de("(73) 3043-0000") is None
    assert m.whatsapp_de("(73) 99876-5432") == "+55 73 99876-5432"


def test_resposta_traz_telefone_e_so_preco_que_esta_na_pagina():
    fontes = [{"url": "https://clinica.exemplo/r", "titulo": "Clínica X", "texto": "Ressonância ombro R$ 450,00 ou R$ 1.200,00"}]
    r = b.montar_resposta("ressonância Itabuna", fontes, cidade="Itabuna", lugares=[CLINICA_ZAP, CLINICA_FIXO])
    assert "(73) 99876-5432" in r and "(73) 3043-0000" in r and "R$ 450,00" in r and r.count("R$") == 2
    assert "não vi Itabuna na página" in r
    assert "Não consegui" in b.montar_resposta("x", [])


def _rodar(nivel, lugares=(CLINICA_ZAP, CLINICA_FIXO)):
    enviados, zaps, avisos = [], [], []
    b._fn_nivel = lambda: nivel
    b._fn_lugares = lambda q, n: list(lugares)
    b._fn_pesquisar = lambda c, n: []
    b.iniciar("mainha", AUDIO, enviados.append, avisos.append, lambda fone, t: zaps.append((fone, t)) or "✅ ok", sincrono=True)
    return enviados[0], zaps, avisos


def test_proatividade_baixa_so_informa():
    texto, zaps, _ = _rodar(3)
    assert "Quer que eu mande" not in texto and zaps == []


def test_proatividade_neutra_pergunta_e_so_manda_depois_do_sim():
    texto, zaps, avisos = _rodar(5)
    assert "Quer que eu mande mensagem pra Clínica Zap" in texto and zaps == []      # o fixo nao entra na oferta
    assert b.confirmacao("mainha", "tia, hoje chove muito aqui na cidade né", lambda *a: "✅", None) is None   # nao e resposta curta
    assert b.confirmacao("mainha", "Hoje foi bom", lambda *a: "✅", None) is None
    enviar = lambda fone, t: zaps.append((fone, t)) or "✅ ok"
    resp = b.confirmacao("mainha", "Sim, pode mandar", enviar, avisos.append)
    assert "Clínica Zap" in resp and "Não marquei nada" in resp
    assert zaps[0][0] == "+55 73 99876-5432" and "nada será agendado" in zaps[0][1] and "da Mãe" in zaps[0][1]
    assert b.confirmacao("mainha", "sim", enviar, None) is None                        # oferta consumida: nao manda duas vezes


def test_resposta_nao_cancela_e_nao_manda():
    _rodar(6)
    zaps = []
    assert "não mando nada" in b.confirmacao("mainha", "Não, deixa", lambda f, t: zaps.append(f) or "✅", None) and zaps == []


def test_proatividade_alta_ja_contata_sem_repetir():
    texto, zaps, _ = _rodar(9)
    assert "Já mandei mensagem pra Clínica Zap" in texto and len(zaps) == 1
    assert len(b.contatar("mainha", [CLINICA_ZAP], "ressonância", lambda f, t: "✅")) == 0        # mesmo lugar nas ultimas 24 h: nao repete


def test_resposta_da_clinica_volta_para_quem_pediu():
    _rodar(9)
    rl = b.resposta_de_lugar("+55 73 99876-5432", "Custa R$ 600,00. Temos vaga dia 12.")
    assert rl[0] == "mainha" and "R$ 600,00" in rl[1] and "Não marco nada" in rl[1] and rl[1].startswith("Tia,")
    assert b.resposta_de_lugar("+55 73 90000-1111", "oi") is None
