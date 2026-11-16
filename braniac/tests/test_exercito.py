# -*- coding: utf-8 -*-
from datetime import date

from braniac import delegacao, exercito


def test_pergunta_do_exercito_vai_para_o_cabo_tito():
    for q in ("Me manda a lista de exames que o exército pede pra minha vaga", "quando é o EAF?", "qual o prazo do exército?"):
        assert exercito.eh_pergunta(q) and delegacao.escolher(q) == ["Cabo Tito"]
    assert not exercito.eh_pergunta("como está a vaquinha dos exames do exército?")


def test_resposta_tem_exames_datas_e_eaf():
    exames = exercito.resposta("lista de exames", date(2026, 10, 29))[0]
    assert "Hemograma" in exames and "Ressonância" in exames and "MAPA" in exames
    datas = exercito.resposta("qual o prazo?", date(2026, 10, 29))[0]
    assert "09/11/2026 08:00" in datas and "Faltam 11 dia" in datas
    assert "1.800 m" in exercito.resposta("quais os mínimos do EAF?")[0]
    assert "1.800 m" not in exercito.resposta("quando é o EAF?", date(2026, 10, 29))[0]
    assert len(exercito.resposta("onde é a inspeção?", date(2026, 11, 8))[0]) < 120


def test_lembrete_logo_apos_marcar_nao_duplica(tmp_path, monkeypatch):
    from datetime import datetime
    from braniac import agenda
    monkeypatch.setattr(agenda, "ARQ", tmp_path / "agenda.json")
    agora = datetime(2026, 10, 29, 8, 0)
    agenda.adicionar("Reunião", "amanhã 7:00", duracao=15, lembrar=0, agora=agora)
    agenda.adicionar("Reunião de trabalho", "amanhã 7:00", duracao=15, lembrar=15, agora=agora)
    itens = agenda._ler()
    assert len(itens) == 1 and itens[0]["lembrar"] == 15


def test_elogio_so_agradece():
    from braniac import contexto
    assert contexto.elogio("Você é muito bom!") and contexto.elogio("Show")
    assert not contexto.elogio("muito bom, como funciona?") and not contexto.elogio("Quero um orçamento, muito bom o site")
