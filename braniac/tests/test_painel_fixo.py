# -*- coding: utf-8 -*-
"""Painel da esteira com endereço fixo (16/11/2026): o Jarvis não manda link novo sozinho; o porteiro do E: exige login."""
import base64
import importlib.util
import json
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from braniac import painel_rede

PORTEIRO = Path(r"E:\painel-esteira\porteiro.py")


def test_endereco_fixo_vence_o_provisorio(monkeypatch, tmp_path):
    fixo = tmp_path / "endereco.txt"
    monkeypatch.setattr(painel_rede, "ENDERECO_FIXO", fixo)
    monkeypatch.setattr(painel_rede, "url_publica", lambda: "https://x.trycloudflare.com")
    assert "provisório" in painel_rede.endereco()
    fixo.write_text("\ufeffhttps://pc.tail1.ts.net/\n", encoding="utf-8")   # o PowerShell 5.1 grava com BOM
    txt = painel_rede.endereco()
    assert "https://pc.tail1.ts.net/parceiro" in txt and "https://pc.tail1.ts.net:8443/" in txt


def test_tunel_nao_avisa_o_dono():
    fonte = Path(painel_rede.__file__).read_text(encoding="utf-8")
    assert "_avisar_dono" not in fonte and "outbox" not in fonte
    import re
    from braniac import portal       # 16/11: o portal velho mandava "Braniac remoto: link de acesso ..." a cada queda do Cloudflare
    tunel = re.search(r"def tunel\(.*?(?=\ndef )", Path(portal.__file__).read_text(encoding="utf-8"), re.S).group(0)
    assert "_avisar" not in tunel and "link de acesso" not in tunel


def test_com_fixo_nao_sobe_tunel(monkeypatch, tmp_path):
    (tmp_path / "e.txt").write_text("https://pc.ts.net/", encoding="utf-8")
    monkeypatch.setattr(painel_rede, "ENDERECO_FIXO", tmp_path / "e.txt")
    monkeypatch.setattr(painel_rede, "_matar_tuneis_velhos", lambda: None)
    monkeypatch.setattr(painel_rede, "servir", lambda *a, **k: None)
    subiu = []
    monkeypatch.setattr(painel_rede, "vigiar_tunel", lambda *a: subiu.append(1))
    painel_rede.iniciar(0)
    assert not subiu


@pytest.mark.skipif(not PORTEIRO.exists(), reason="porteiro fica no E: deste PC")
def test_porteiro_401_sem_senha_200_com_senha(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("porteiro", PORTEIRO)
    p = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(p)

    class Painel(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.send_header("Content-Type", "text/html"); self.end_headers(); self.wfile.write(b"painel ok")
        def log_message(self, *a):
            pass

    falso = ThreadingHTTPServer(("127.0.0.1", 0), Painel)
    threading.Thread(target=falso.serve_forever, daemon=True).start()
    senha = tmp_path / "senha.json"
    senha.write_text(json.dumps({"usuarios": {"dono": p.gerar_hash("senha-de-teste-123", voltas=1000),
                                              "parceiro": p.gerar_hash("outra-senha-456", voltas=1000)}}), encoding="utf-8")
    monkeypatch.setattr(p, "_erros", {})
    monkeypatch.setattr(p, "SENHA", senha)
    monkeypatch.setattr(p, "LOG", tmp_path / "acessos.log")
    monkeypatch.setattr(p, "PAINEL", f"http://127.0.0.1:{falso.server_port}")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), p.Porteiro)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}/"

    def pedir(usuario_senha=None):
        req = urllib.request.Request(url)
        if usuario_senha:
            req.add_header("Authorization", "Basic " + base64.b64encode(usuario_senha.encode()).decode())
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    assert pedir()[0] == 401
    assert pedir("dono:errada")[0] == 401
    assert pedir("dono:senha-de-teste-123") == (200, b"painel ok")
    assert pedir("Parceiro:outra-senha-456") == (200, b"painel ok")          # 2o usuário; maiúscula no nome não importa
    assert pedir("parceiro:senha-de-teste-123")[0] == 401                    # senha de um não abre o outro
    for _ in range(5):
        pedir("dono:errada")
    assert pedir("dono:senha-de-teste-123")[0] == 429      # bloqueio por excesso de tentativas
    assert "senha-de-teste" not in (tmp_path / "acessos.log").read_text(encoding="utf-8")
    srv.shutdown(); falso.shutdown()
