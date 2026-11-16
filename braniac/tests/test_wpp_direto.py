from braniac import wpp_direto as W


def test_jid_so_para_nome_conhecido(tmp_path, monkeypatch):
    monkeypatch.setattr(W, "CONTATOS", tmp_path / "c.json")
    monkeypatch.setattr(W, "novas", lambda d=0: [{"seq": 3, "de": "5566999@s.whatsapp.net", "nome": "Deusa  Parceira", "minha": False}])
    assert W.aprender() == 3
    assert W.jid_de("parceira") == "5566999@s.whatsapp.net"
    assert W.jid_de("parceira") is None            # parcial nao vale: cai no Chrome, que confere o titulo


def test_parado_sem_sidecar(monkeypatch):
    monkeypatch.setattr(W, "PORTA", 1)
    monkeypatch.setattr(W, "BASE", "http://127.0.0.1:1")
    assert W.status()["estado"] == "parado" and not W.conectado()
