from braniac import personalidade as P


def test_autonomia_e_apelido_de_proatividade(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "ARQ", tmp_path / "p.json")
    assert P.comando("aumenta a autonomia") and P.niveis()["proatividade"] == 7
