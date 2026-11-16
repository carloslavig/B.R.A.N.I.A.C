# -*- coding: utf-8 -*-
"""Drive como caixa de entrada: so a logica (listar/baixar trocados por falsos, sem Chrome)."""
import json

import pytest

from braniac import drive_pasta


@pytest.fixture(autouse=True)
def _isolar(tmp_path, monkeypatch):
    monkeypatch.setattr(drive_pasta, "ARQ_VISTOS", tmp_path / "vistos.json")
    monkeypatch.setattr(drive_pasta, "_fn_baixar", None)


def test_primeira_vez_so_registra_e_depois_so_o_novo(monkeypatch):
    itens = [{"id": "a" * 25, "nome": "velho.mp4", "pasta": False, "em": ""}]
    monkeypatch.setattr(drive_pasta, "_fn_listar", lambda pid: list(itens))
    assert drive_pasta.novos("PASTA") == []                       # baseline: o que ja existia nao e pedido
    itens.append({"id": "b" * 25, "nome": "meta.json", "pasta": False, "em": ""})
    assert [i["nome"] for i in drive_pasta.novos("PASTA")] == ["meta.json"]
    drive_pasta.marcar_vistos(itens)
    assert drive_pasta.novos("PASTA") == []


def test_baixar_ignora_extensao_fora_da_lista(tmp_path, monkeypatch):
    chamado = []
    monkeypatch.setattr(drive_pasta, "_fn_baixar", None)
    # sem Chrome: uteis vazio devolve sem abrir nada
    assert drive_pasta.baixar([{"id": "x" * 25, "nome": "virus.exe", "pasta": False, "em": ""}, {"id": "y" * 25, "nome": "pasta", "pasta": True, "em": ""}], tmp_path) == []
    assert chamado == []
