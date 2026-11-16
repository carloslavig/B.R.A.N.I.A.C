# -*- coding: utf-8 -*-
"""Elo P2P v2: o painel do par so serve GET relativo (sem ../), e o predio no Sauraki some quando o ping para de responder."""
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from braniac import par_webrtc, rede_jarvis


def test_painel_local_recusa_caminhos_perigosos(tmp_path):
    p = par_webrtc.Par(tmp_path, "loja", lambda d, t: "", "http://127.0.0.1:9")
    for ruim in ("../x", "/a/../b", "//evil.com", "http://evil.com/", "x"):
        assert p._painel_local(ruim)[0] == 404
    assert p._painel_local("/ok")[0] == 502          # caminho valido, mas nada escutando na porta


def test_predio_aparece_so_com_ping_recente(tmp_path, monkeypatch):
    monkeypatch.setattr(rede_jarvis, "DATA", tmp_path)
    monkeypatch.setattr(rede_jarvis, "_P", None)
    assert rede_jarvis.predios() == []                # sem par
    rede_jarvis.par().parear("ABCD-EFGH-IJKL-MNOP", "loja")
    rede_jarvis._VIVO.update(ok=True, ts=time.time())
    assert rede_jarvis.predios()[0]["nome"] == "Braniac Loja"
    rede_jarvis._VIVO.update(ok=True, ts=time.time() - 500)
    assert rede_jarvis.predios() == []                # ping velho = predio some
    rede_jarvis._VIVO.update(ok=False, ts=time.time())
    assert rede_jarvis.predios() == []
