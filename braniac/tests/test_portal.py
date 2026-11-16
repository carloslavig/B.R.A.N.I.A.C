# -*- coding: utf-8 -*-
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

from braniac import portal as p


def _req(porta, caminho, corpo=None, cookie="", host=None):
    r = urllib.request.Request(f"http://127.0.0.1:{porta}{caminho}", data=json.dumps(corpo).encode() if corpo is not None else None,
                               headers={"Cookie": cookie, "Content-Type": "application/json", "Accept": "application/json"}, method="POST" if corpo is not None else "GET")
    try:
        x = urllib.request.urlopen(r)
    except urllib.error.HTTPError as e:
        x = e
    return x.status, json.loads(x.read() or b"{}") if "json" in x.headers.get("Content-Type", "") else x.read(), x.headers.get_all("Set-Cookie") or []


def test_portal_fluxo(tmp_path, monkeypatch):
    monkeypatch.setattr(p, "DADOS", tmp_path)
    monkeypatch.setattr(p, "ARQ", tmp_path / "portal.json")
    monkeypatch.setattr(p, "LOG", tmp_path / "portal.log")
    monkeypatch.setattr(p, "OUTBOX", tmp_path / "outbox.txt")
    monkeypatch.setattr(p.time, "sleep", lambda s: None)
    p._falhas.clear(); p._falhas_g.clear()
    p.definir_senha("Dono", "260714")
    assert "260714" not in (tmp_path / "portal.json").read_text(encoding="utf-8")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), p.montar())
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    porta = srv.server_address[1]
    try:
        assert _req(porta, "/api/saude")[0] == 401                                   # sem login nada passa
        assert _req(porta, "/portal/login", {"usuario": "dono", "senha": "errada"})[0] == 401
        s, j, ck = _req(porta, "/portal/login", {"usuario": "DONO", "senha": "260714"})
        assert j == {"precisa_codigo": True}                                         # dispositivo novo pede codigo
        bdev = ck[0].split(";")[0]
        cod = (tmp_path / "outbox.txt").read_text(encoding="utf-8").split("Código: ")[1][:6]
        assert _req(porta, "/portal/login", {"usuario": "dono", "senha": "260714", "codigo": "000000" if cod != "000000" else "111111"}, bdev)[0] == 401
        s, j, ck = _req(porta, "/portal/login", {"usuario": "dono", "senha": "260714", "codigo": cod}, bdev)
        assert j == {"ok": True}
        bsess = [c for c in ck if c.startswith("bsess")][0]
        assert all(f in bsess for f in ("HttpOnly", "Secure", "SameSite=Strict"))
        cook = bdev + "; " + bsess.split(";")[0]
        lista = _req(porta, "/portal/api/dispositivos", cookie=cook)[1]
        assert len(lista) == 1 and lista[0]["atual"]
        assert _req(porta, "/api/remoto", cookie=cook)[0] == 403                    # pareamento nunca pelo portal
        _req(porta, "/portal/api/revogar", {"id": lista[0]["id"]}, cook)
        assert _req(porta, "/portal/api/dispositivos", cookie=cook)[0] == 401        # revogado derruba a sessao
        for _ in range(5):                                                           # trava por IP
            _req(porta, "/portal/login", {"usuario": "x", "senha": "y"})
        assert _req(porta, "/portal/login", {"usuario": "dono", "senha": "260714"})[0] == 429
    finally:
        srv.shutdown()
