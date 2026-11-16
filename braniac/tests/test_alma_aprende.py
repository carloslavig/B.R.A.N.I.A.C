# -*- coding: utf-8 -*-
import time

import pytest

from braniac import alma_aprende as A


@pytest.fixture(autouse=True)
def isolado(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "PASTA", tmp_path)
    monkeypatch.setattr(A, "BANCO", tmp_path / "perfil.db")
    monkeypatch.setattr(A, "CONSENT", tmp_path / "c.json")
    monkeypatch.setattr(A, "ESTADO", tmp_path / "h.json")
    monkeypatch.setattr(A, "DIARIO", tmp_path / "diario.jsonl")


def test_nb_sem_dados_nao_forca_tema_e_com_dados_acerta():
    assert A.tema_nb("preciso pagar o aluguel")[0] == "indefinido"
    treino = [("trabalho", ["cliente", "pagou", "projeto"])] * 12 + [("familia", ["filho", "escola", "jantar"])] * 12
    assert A.tema_nb("o cliente do projeto", treino)[0] == "trabalho"
    assert A.tema_nb("zzz yyy", treino)[0] == "indefinido"           # nenhuma palavra conhecida -> confianca baixa


def test_contexto_e_etiqueta():
    assert A.contexto("fechei com o cliente") == "trabalho" and A.contexto("jantar com meu filho") == "casa" and A.contexto("ok") == "neutro"


def test_sinais_guardam_so_numeros_e_ignoram_segredo_e_crise():
    assert A.registrar_sinais("oi tudo bem!", time.time())
    assert not A.registrar_sinais("minha senha é 123", time.time())
    assert not A.registrar_sinais("quero morrer", time.time())
    assert A.sabe()["sinais"] == 1


def test_humor_sem_linha_de_base_nao_alerta_e_pausa_desliga():
    A.registrar_sinais("oi")
    assert A.estado_humor()["alerta"] is False and A.dica_tom() == ""
    A.definir_consentimento(pausado=True)
    assert not A.registrar_sinais("oi de novo") and A.estado_humor()["estado"] == "pausado"


def test_humor_alerta_com_tres_sinais_em_duas_janelas():
    agora = time.time()
    h = int(time.strftime("%H", time.localtime(agora)))
    with A._db() as c:
        for i in range(60):    # linha de base: 20 dias, mensagens curtas e calmas na mesma faixa
            ts = agora - (7 + i % 20) * 86400 + (i % 3) * 60
            c.execute("INSERT INTO sinais VALUES(?,?,?,?,?,?,?,?,?)", (ts, h, 0, 5 + i % 3, 0, 0, 0, 0, 300 + i % 5))
        for ts in (agora - 100, agora - 200, agora - 3 * 3600 - 100, agora - 3 * 3600 - 200):   # duas janelas fora do normal
            c.execute("INSERT INTO sinais VALUES(?,?,?,?,?,?,?,?,?)", (ts, h, 0, 40, 6, 4, 5, 4, 5))
    assert A.estado_humor(agora)["alerta"] is True


def test_exemplos_parecidos_e_apagar():
    assert A.registrar_exemplo("o cliente pediu desconto", "vou ver o que dá pra fazer", "trabalho")
    assert not A.registrar_exemplo("manda o pix", "ok")
    assert A.parecidos("cliente pedindo desconto")[0]["resposta"].startswith("vou ver")
    A.apagar("tudo")
    assert A.sabe()["exemplos"] == 0


def test_rotular_rejeita_tema_invalido():
    A.enfileirar_rotulo("fiquei pensando na reforma do quintal")
    i = A.pendentes_rotulo()[0]["id"]
    assert not A.rotular(i, "xyz") and A.rotular(i, "familia") and not A.pendentes_rotulo()
