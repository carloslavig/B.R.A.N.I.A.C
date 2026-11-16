from braniac import jarvis


def test_numero_solto():
    assert jarvis._numero_solto("11900000001")
    assert jarvis._numero_solto("+55 (11) 90000-0002")
    assert not jarvis._numero_solto("me lembra às 15")
    assert not jarvis._numero_solto("123")
    assert not jarvis._numero_solto("liga pro 11900000001")
