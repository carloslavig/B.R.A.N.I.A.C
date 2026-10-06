# -*- coding: utf-8 -*-
import http.client, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from braniac_seed import servidor


@pytest.fixture()
def srv(tmp_path, monkeypatch):
    monkeypatch.setenv("BRANIAC_HOME", str(tmp_path))
    s, porta = servidor.servir(porta=servidor.porta_livre(9100), bloquear=False)
    yield porta
    s.shutdown()


def req(porta, metodo, caminho, corpo=None):
    c = http.client.HTTPConnection("127.0.0.1", porta, timeout=10)
    c.request(metodo, caminho, json.dumps(corpo).encode() if corpo is not None else None, {"Content-Type": "application/json"})
    r = c.getresponse()
    dados = r.read()
    c.close()
    return r.status, json.loads(dados)


def test_erro_da_tela_vai_para_o_diario_local(srv, tmp_path):
    req(srv, "POST", "/api/log", {"msg": "falhou ao avançar", "etapa": "consentimento"})
    assert "falhou ao avançar" in (tmp_path / "instalacao.log").read_text(encoding="utf-8")


def test_erro_de_api_fica_registrado_e_a_tela_recebe_o_motivo(srv, tmp_path):
    st, r = req(srv, "POST", "/api/consentimento", {"modo": "invalido"})
    assert st == 400 and "erro" in r and "instalacao.log" in [p.name for p in tmp_path.iterdir()]


def test_consentimento_em_qualquer_modo_libera_o_continuar(srv):
    for modo in ("nenhum", "granular", "total"):
        assert req(srv, "POST", "/api/consentimento", {"modo": modo})[0] == 200
        assert req(srv, "GET", "/api/estado")[1]["perfil"]["consentimento_acesso_pc"] == modo


def test_falha_ao_ler_o_estado_devolve_erro_legivel_e_registra(srv, tmp_path, monkeypatch):
    monkeypatch.setattr(servidor, "estado_geral", lambda: (_ for _ in ()).throw(RuntimeError("quebrou")))
    st, r = req(srv, "GET", "/api/estado")
    assert st == 500 and "quebrou" in r["erro"]
    assert "quebrou" in (tmp_path / "instalacao.log").read_text(encoding="utf-8")
