from braniac import airbnb_base as b


def test_slug_e_tipo():
    assert b.slug("Quarto A · casa com piscina") == "cacau"
    assert b.tipo("Casa Casa · 3 quartos") == "casa"
    assert b.tipo("Apartamento completo - Perto da praia") == "apto"
    assert b.slug("Pousada qualquer") is None


def test_ler_respostas():
    fa, rh = b.ler_respostas([(1, "cacau: wifi é X"), (2, "Elvira: Rua A, 10"), (3, "info casa: outros espaços"), (4, "oi"), (5, "Zé: não aberto")], {"elvira"})
    assert ("cacau", "wifi é X") in fa and ("casa:info-casa", "outros espaços") in fa
    assert rh == [("elvira", "Rua A, 10")]


def test_link_do_braniac_publico_liberado_e_privado_barrado():
    from braniac import atender
    assert atender.validar_resposta("Aqui: https://github.com/carloslavig/B.R.A.N.I.A.C")[0]
    assert not atender.validar_resposta("Aqui: https://github.com/carloslavig/braniac-fonte")[0]
