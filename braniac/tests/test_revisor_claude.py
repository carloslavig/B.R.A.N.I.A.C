# -*- coding: utf-8 -*-
from braniac import revisor_claude as R, exercito


def test_aprova_e_reprova():
    ok = R.revisar("que horas é a IS?", "Amanhã às 8h.", perguntar=lambda p: '{"aprovado": true, "motivo": "direto", "corrigida": ""}')
    assert ok["ok"] is True
    no = R.revisar("que horas é a IS?", "Falei com Alma...", perguntar=lambda p: 'ok {"aprovado": false, "motivo": "assunto errado", "corrigida": "Amanhã às 8h."} fim')
    assert no["ok"] is False and no["corrigida"] == "Amanhã às 8h."


def test_sem_revisor_nao_aprova():
    assert R.revisar("a", "b", perguntar=lambda p: None)["ok"] is None
    assert R.revisar("a", "b", perguntar=lambda p: "lixo sem json")["ok"] is None


def test_transcricao_ruim_cai_no_cabo_tito():
    assert exercito.eh_pergunta("Jarvis, que horas é a expressão de saúde amanhã?")
