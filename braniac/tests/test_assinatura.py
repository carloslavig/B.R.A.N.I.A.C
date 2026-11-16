# -*- coding: utf-8 -*-
from braniac import assinatura


def test_deusa_e_mestres_supremos_por_padrao():
    for p in ("Quem é a sua deusa?", "quem são seus mestres supremos", "Quem te criou?", "qual é a sua assinatura"):
        r = assinatura.responder(p)
        assert r and "Parceira" in r and "Dono" in r and "Claudinho" in r
    assert assinatura.responder("quem é o criador do instagram") is None
    assert assinatura.responder("quem é a parceira pra você") is None     # pergunta sobre a pessoa: segue o fluxo normal
