# -*- coding: utf-8 -*-
"""Artes da Loja: validacao das legendas do conselho e leitura do formato devolvido pelos chats (sem '###')."""
from braniac import artes_loja as a


def test_legenda_barra_preco_horario_e_telefone_inventados():
    assert a.validar_legenda("Segunda em Dobro: 2 esfihas por R$ 21,90! Peça no site.")
    assert not a.validar_legenda("Promoção por R$ 19,90 hoje!")
    assert not a.validar_legenda("Aberto das 18h às 23h30")
    assert not a.validar_legenda("Chama no 66 99999 9999")
    assert not a.validar_legenda("x" * 800) and not a.validar_legenda("")


def test_parser_do_conselho_aceita_ids_sozinhos_na_linha_e_descarta_invalidas():
    bruto = "feed1\n\nEscrita\n\nChocolate cremoso! 🍓\n\n#esfiha\n\nfeed5\nPor R$ 12,34 hoje\nreel\nVídeo lindo!\n"
    legs = a.pedir_legendas(a.CONCEITOS, lambda ia, q, timeout_s=0: bruto)
    assert set(legs) == {"feed1", "reel"} and legs["feed1"].startswith("Chocolate")


def test_conceitos_so_usam_fotos_e_precos_conhecidos():
    import re
    for _, _, foto, tit, sub, _ in a.CONCEITOS:
        assert foto.startswith("DSC_")
        for v in re.findall(r"R\$\s*(\d+[.,]\d{2})", tit + " " + sub):
            assert v in a.PRECOS_OK
