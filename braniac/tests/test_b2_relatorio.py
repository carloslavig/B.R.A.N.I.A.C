# -*- coding: utf-8 -*-
"""Teste da funcao relatorio() do b2.py com monkeypatch em b2.DATA."""
import pytest
from braniac import b2


def test_relatorio_vazio(tmp_path, monkeypatch):
    """relatorio() devolve 'Nada registrado ainda.' quando o arquivo nao existe."""
    data_falso = tmp_path / "data"
    monkeypatch.setattr(b2, "DATA", data_falso)
    import importlib
    importlib.reload(b2)
    assert b2.relatorio() == "Nada registrado ainda."


def test_relatorio_arquivo_vazio(tmp_path, monkeypatch):
    """relatorio() devolve 'Nada registrado ainda.' quando o arquivo existe mas esta vazio."""
    data_falso = tmp_path / "data"
    relatorio = data_falso / "relatorio_noturno.md"
    relatorio.write_text("", encoding="utf-8")
    monkeypatch.setattr(b2, "DATA", data_falso)
    import importlib
    importlib.reload(b2)
    assert b2.relatorio() == "Nada registrado ainda."


def test_relatorio_com_conteudo(tmp_path, monkeypatch):
    """relatorio() devolve o conteudo do arquivo quando existe e tem texto."""
    data_falso = tmp_path / "data"
    relatorio = data_falso / "relatorio_noturno.md"
    relatorio.write_text("- 24/10 03:15 · Tarefa concluida\n- 24/10 04:00 · Backup feito", encoding="utf-8")
    monkeypatch.setattr(b2, "DATA", data_falso)
    import importlib
    importlib.reload(b2)
    texto = b2.relatorio()
    assert "Tarefa concluida" in texto
    assert "Backup feito" in texto