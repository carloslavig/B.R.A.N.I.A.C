# -*- coding: utf-8 -*-
import time
from datetime import datetime

import pytest

from braniac import assuntos, banco


@pytest.fixture(autouse=True)
def isolado(tmp_path, monkeypatch):
    monkeypatch.setattr(banco, "ARQ", tmp_path / "jarvis.db")
    monkeypatch.setattr(assuntos, "PASTA", tmp_path / "assuntos")
    monkeypatch.setattr(banco, "sincronizar", lambda forcar=False: None)
    yield


def test_detecta_o_assunto_certo_e_cria_um_banco_por_assunto():
    assuntos.iniciar()
    assert assuntos.detectar("a Layla aceitou o pedido de brócolis?")[0][0] == "loja"
    assert assuntos.detectar("saiu o edital da inspeção de saúde do exército")[0][0] == "exercito"
    assert assuntos.detectar("preciso corrigir um bug em python e fazer deploy no vercel")[0][0] == "programacao"
    assert assuntos.detectar("o servidor do braniac caiu e o jarvis não responde")[0][0] == "braniac"      # Braniac e Forja; programacao e Ada
    assert assuntos.detectar("qual a previsão do tempo") == []
    assert {a["agente"] for a in assuntos.listar()} >= {"Sultão", "Alma", "Cabo Tito", "Forja", "Ilhéu", "Cofre", "Ada"}
    assert (assuntos.PASTA / "loja.db").exists()


def test_so_hoje_expira_sozinho_as_5h_e_data_explicita_conta_da_propria_data():
    seg = datetime(2026, 10, 26, 18, 0)
    assert datetime.fromtimestamp(assuntos.validade_do_texto("Hoje não tem brócolis (só por hoje)", seg)) == datetime(2026, 10, 27, 5, 0)
    assert datetime.fromtimestamp(assuntos.validade_do_texto("Hoje (11/10/2026) NÃO há Tomate Seco; só vale hoje", seg)) == datetime(2026, 10, 12, 5, 0)
    assert assuntos.validade_do_texto("O cardápio tem 22 sabores", seg) is None
    assert assuntos.validade_do_texto("sem carne seca temporariamente", seg) is not None


def test_curador_vence_o_que_passou_do_prazo_acha_contradicao_e_refaz_a_ficha():
    assuntos.registrar("loja", "a", "Hoje não temos brócolis especial nem tomate seco com rúcula na loja", agora=datetime(2026, 10, 11, 12, 0))
    assuntos.registrar("loja", "b", "Brócolis especial e tomate seco com rúcula estão disponíveis na loja agora", agora=datetime(2026, 10, 25, 18, 0))
    assuntos.registrar("loja", "c", "O cardápio salgado da loja tem 22 sabores")
    r = assuntos.curar(agora=datetime(2026, 10, 26, 9, 0))
    assert r["vencidos"] == 0       # 'Hoje não temos' sem 'só hoje' nao tem prazo: vira CONTRADICAO para o Dono decidir, nunca some sozinho
    assert r["contradicoes"] and "Sultão" == r["contradicoes"][0][0]
    assuntos.registrar("loja", "d", "Hoje não tem pantaneira (só por hoje)", agora=datetime(2026, 10, 25, 20, 0))
    assert assuntos.curar(agora=datetime(2026, 10, 26, 9, 0))["vencidos"] == 1
    ctx = assuntos.contexto_para("a Layla aceita brócolis especial?")
    assert "AGENTE Sultão" in ctx and "pantaneira" not in ctx.lower()      # o fato vencido nao volta ao contexto


def test_banco_principal_espelha_e_consulta_os_bancos_dos_assuntos():
    banco.gravar_fato("loja", "sabor", "Carne seca com cream cheese está disponível na loja Loja", "publico", "teste")
    banco.gravar_fato("negocio", "vencido", "Hoje (01/10/2026) a loja Loja está fechada; só vale hoje", "publico", "teste")
    corpo, _ = banco.consultar("carne seca cream cheese loja", "online")
    assert "cream cheese" in corpo.lower()
    assert "fechada" not in banco.consultar("loja Loja fechada", "online")[0]            # fato com validade vencida some da consulta
    p = banco.pacote("a loja Loja tem carne seca?", "online")
    assert "AGENTE Sultão" in p


def test_busca_do_banco_casa_plural_e_acento():
    """12/11: 'vídeo ... parceiro' nao achava 'VIDEOS DO PARCEIRO' e o Jarvis disse 'nao tenho registrado'."""
    banco.gravar_fato("link", "videos-parceiro", "VIDEOS DO PARCEIRO: gabarito de Feira da Mata, video 139", "publico", "teste")
    corpo, _ = banco.consultar("Como tá o vídeo de Salvador no padrão do Parceiro?", "online")
    assert corpo.startswith("[link] VIDEOS DO PARCEIRO")


def test_assunto_novo_proposto_pela_ia_local_ganha_banco_e_agente_com_limite_diario():
    assuntos.iniciar()
    ia = lambda prompt: {"novo": {"nome": "Academia", "palavras": ["treino", "academia", "musculacao", "serie"]}}
    id1 = assuntos.classificar_com_ia("quero montar meu treino de musculação", ia)
    assert id1 == "academia" and (assuntos.PASTA / "academia.db").exists()
    assert assuntos.detectar("hoje tem treino de academia")[0][0] == "academia"
    for n in ("Jardim", "Carro", "Viagem"):
        assuntos.criar_assunto(n, [n.lower(), "a1", "a2"])
    assert assuntos.criar_assunto("Extra demais", ["x", "y", "z"]) is None            # no maximo 3 novos por dia
    ruim = lambda prompt: {"assunto": "inexistente"}
    assert assuntos.classificar_com_ia("qualquer coisa", ruim) is None


def test_lista_de_agentes_para_o_jarvis_e_toda_ia_nao_inventar():
    longo = assuntos.resumo_agentes()
    for nome in ("Sultão", "Alma", "Cabo Tito", "Forja", "Ada", "Ilhéu", "Cofre"):
        assert nome in longo
    assert "AGENTES DO BRANIAC" in assuntos.resumo_agentes(curto=True)
    assert "AGENTES DO BRANIAC" in banco.pacote("oi", "online")                 # toda IA recebe a lista no prompt
    from braniac import jarvis
    assert "listar_agentes" in {f["function"]["name"] for f in jarvis.ferramentas_para("faz uma lista dos agentes e manda pra Parceira")}
