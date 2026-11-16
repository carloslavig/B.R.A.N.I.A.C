from braniac import jarvis


def test_desabafo_nao_vai_para_ferramentas(monkeypatch):
    monkeypatch.setattr(jarvis, "_acolher", lambda t: "tô aqui")
    class R:  # qualquer uso do router quebra o teste
        def __getattr__(self, n): raise AssertionError("foi pro router")
    assert jarvis.processar(R(), "Estou tendo crise de ansiedade, não estou bem", "c", origem="web") == ("tô aqui", True)
