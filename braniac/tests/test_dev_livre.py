# -*- coding: utf-8 -*-
"""Jarvis programa sozinho (sem Claude): so mexe dentro de braniac/, nunca em data/, .env nem arquivos protegidos."""
import pytest
from braniac import dev_livre, automelhoria


@pytest.fixture
def raiz(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "a.py").write_text("x = 1\ny = 1\nx = 1\n", encoding="utf-8")
    monkeypatch.setattr(dev_livre, "BRANIAC", tmp_path)
    return tmp_path


def test_so_mexe_dentro_de_braniac(raiz):
    for ruim in ("../fora.py", "data/jarvis.db", ".env", "braniac/data/x"):
        with pytest.raises(ValueError):
            dev_livre.executor("ler_arquivo", {"caminho": ruim})
    with pytest.raises(ValueError):
        dev_livre.executor("criar_arquivo", {"caminho": "automelhoria.py", "conteudo": "x"})


def test_substituir_exige_trecho_unico(raiz):
    assert "2 vez" in dev_livre.executor("substituir_trecho", {"caminho": "a.py", "antigo": "x = 1", "novo": "x = 2"})
    assert dev_livre.executor("substituir_trecho", {"caminho": "a.py", "antigo": "y = 1", "novo": "y = 2"}) == "ok"
    assert "y = 2" in (raiz / "a.py").read_text(encoding="utf-8")
    assert "a.py:2" in dev_livre.executor("buscar_codigo", {"texto": "y = 2"})


def test_sem_claude_usa_ia_gratis(monkeypatch):
    monkeypatch.setenv("BRANIAC_SEM_CLAUDE", "1")
    monkeypatch.setattr(dev_livre, "rodar", lambda p, t=0: (0, "feito pela IA gratis"))
    assert automelhoria._rodar_claude_padrao("pedido") == (0, "feito pela IA gratis")
