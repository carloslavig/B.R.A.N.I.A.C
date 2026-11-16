from braniac import memoria


def test_correcao_volta_como_contexto(monkeypatch, tmp_path):
    monkeypatch.setattr(memoria, "_con", None)
    monkeypatch.setattr(memoria, "ARQ", tmp_path / "m.db")
    assert memoria.corrigir("horario da esfiha", "abre as 18h, nao 17h")
    assert memoria.correcoes_parecidas("qual o horario da esfiha hoje?") == ["horario da esfiha -> abre as 18h, nao 17h"]
    assert memoria.correcoes_parecidas("sobre airbnb") == []
