import hashlib
import os

from braniac import porta_lan as p
from braniac import porta_lan_cliente as c


def _sobe(tmp_path, monkeypatch):
    monkeypatch.setattr(p, "PASTA", tmp_path / "rec")
    monkeypatch.setattr(p, "CHAVE", tmp_path / "k")
    p._erros.clear()
    p._nonces.clear()
    srv, chave = p.iniciar(1, "127.0.0.1", 0)
    c.PORTA = srv.server_address[1]
    return srv, chave


def test_envia_e_recusa(tmp_path, monkeypatch):
    srv, chave = _sobe(tmp_path, monkeypatch)
    try:
        arq = tmp_path / "a.txt"
        arq.write_bytes(b"ola braniac")
        st, r = c.pedido("127.0.0.1", chave, "POST", "/arquivo?nome=a.txt", str(arq), c._sha(str(arq)))
        assert st == 200 and (tmp_path / "rec" / r["salvo_como"]).read_bytes() == b"ola braniac"
        assert c.pedido("127.0.0.1", "0" * 64, "GET", "/ping")[0] == 401        # chave errada
        exe = tmp_path / "x.exe"
        exe.write_bytes(b"MZ")
        assert c.pedido("127.0.0.1", chave, "POST", "/arquivo?nome=x.exe", str(exe), c._sha(str(exe)))[0] == 415
        assert c.pedido("127.0.0.1", chave, "POST", "/arquivo?nome=a.txt", str(arq), "0" * 64)[0] == 400   # hash declarado nao bate o conteudo: descarta o parcial
        assert not [f for f in os.listdir(tmp_path / "rec") if f.startswith(".parcial")]
    finally:
        srv.shutdown()


def test_bloqueia_apos_erros_e_nonce(tmp_path, monkeypatch):
    srv, chave = _sobe(tmp_path, monkeypatch)
    try:
        for _ in range(5):
            c.pedido("127.0.0.1", "0" * 64, "GET", "/ping")
        assert c.pedido("127.0.0.1", chave, "GET", "/ping")[0] == 429
    finally:
        srv.shutdown()


def test_nome_seguro():
    assert p.nome_seguro("../../etc/passwd") == "passwd"
    assert p.nome_seguro("..\\..\\a b.rs") == "a b.rs"
    assert p.nome_seguro("") == "arquivo"
