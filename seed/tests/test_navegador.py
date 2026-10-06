# -*- coding: utf-8 -*-
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from braniac_seed import navegador, perfil


@pytest.fixture(autouse=True)
def casa(tmp_path, monkeypatch):
    monkeypatch.setenv("BRANIAC_HOME", str(tmp_path))


def test_usa_o_navegador_padrao_do_windows_quando_for_chromium():
    instal = {"chrome": "c.exe", "edge": "e.exe", "brave": "b.exe"}
    assert navegador.escolhido(instal, padrao="brave", preferido="auto") == "brave"
    assert navegador.escolhido(instal, padrao="chrome", preferido="auto") == "chrome"


def test_padrao_firefox_ou_desconhecido_cai_no_chrome_e_depois_no_edge():
    assert navegador.escolhido({"chrome": "c", "edge": "e"}, padrao=None, preferido="auto") == "chrome"
    assert navegador.escolhido({"edge": "e"}, padrao=None, preferido="auto") == "edge"


def test_escolha_da_pessoa_vale_mais_que_o_padrao():
    assert navegador.escolhido({"chrome": "c", "edge": "e"}, padrao="chrome", preferido="edge") == "edge"


def test_escolha_de_navegador_que_nao_existe_e_ignorada():
    assert navegador.escolhido({"chrome": "c"}, padrao=None, preferido="brave") == "chrome"


def test_sem_nenhum_navegador_compativel_da_erro_claro():
    with pytest.raises(navegador.NavegadorErro):
        navegador.escolhido({}, padrao=None, preferido="auto")


def test_cada_navegador_tem_perfil_proprio(monkeypatch):
    monkeypatch.setattr(navegador, "instalados", lambda: {"chrome": "c", "edge": "e"})
    perfil.atualizar(navegador="chrome")
    a = navegador.perfil_dir()
    perfil.atualizar(navegador="edge")
    b = navegador.perfil_dir()
    assert a != b and a.name == "navegador-chrome" and b.name == "navegador-edge"


def test_trocar_valida_e_grava(monkeypatch):
    monkeypatch.setattr(navegador, "instalados", lambda: {"chrome": "c", "edge": "e"})
    monkeypatch.setattr(navegador, "rodando", lambda: False)
    navegador.trocar("edge")
    assert perfil.carregar()["navegador"] == "edge"
    with pytest.raises(navegador.NavegadorErro):
        navegador.trocar("brave")


def test_info_mostra_o_que_esta_em_uso(monkeypatch):
    monkeypatch.setattr(navegador, "instalados", lambda: {"chrome": "c", "edge": "e"})
    monkeypatch.setattr(navegador, "padrao_do_windows", lambda: "chrome")
    i = navegador.info()
    assert i["usado"] == "chrome" and i["instalados"]["edge"] == "Microsoft Edge" and i["padrao_windows"] == "chrome"
