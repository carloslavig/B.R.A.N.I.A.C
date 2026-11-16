from braniac import b2, delegacao


def test_conversa_nova_nasce_sem_modulos_e_filtra(tmp_path, monkeypatch):
    monkeypatch.setattr(b2, "DB", tmp_path / "b2.db", raising=False)
    j = b2.acao({"acao": "criar_conversa", "projeto": 1, "modulos": []})
    cid = j["novo"]
    assert b2.modulos_da_conversa(cid) == []
    b2.acao({"acao": "modulos", "id": cid, "modulos": ["Vaquinha", "Inexistente"]})
    assert b2.modulos_da_conversa(cid) == ["Vaquinha"]
    delegacao.LIMITE.perm = {"Vaquinha"}
    try:
        assert "Cofre" not in delegacao.escolher("qual o saldo da conta?")
    finally:
        delegacao.LIMITE.perm = None
