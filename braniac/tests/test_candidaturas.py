from braniac import candidaturas as C


def test_fila_triagem_e_relato(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "ARQ", tmp_path / "c.json")
    assert C.receber("Correio", "Convite para entrevista", "Acme")["status"] == "aguardando_voce"
    v = C.receber("Garimpeiro", "Support Engineer", "Foo", "https://x.y/1")
    assert v["status"] == "triagem" and v["remota"] is True
    assert C.receber("Garimpeiro", "Support Engineer", "Foo", "https://x.y/1") is None    # nao duplica
    r = C.relato()
    assert "2 vaga" in r and "precisa de você" in r and "não me inscrevo sozinho" in r
    assert C.relato() == ""                                                                  # so relata o que e novo
