# -*- coding: utf-8 -*-
"""Animacoes prontas (claude-animation-skills, MIT): so a validacao, sem renderizar."""
import pytest

from braniac import animacoes


def test_animacao_desconhecida_ou_spec_invalida(tmp_path, monkeypatch):
    monkeypatch.setattr(animacoes, "ARQ_USO", tmp_path / "uso.json")
    with pytest.raises(ValueError, match="desconhecida"):
        animacoes.gerar("zach-d-films", {})              # exige o Claude
    with pytest.raises(ValueError, match="objeto"):
        animacoes.gerar("graph", [1, 2])
    with pytest.raises(ValueError, match="segredo"):
        animacoes.gerar("graph", {"label": "minha senha 123", "values": [1, 2]})


def test_teto_diario(tmp_path, monkeypatch):
    import json
    import time
    monkeypatch.setattr(animacoes, "ARQ_USO", tmp_path / "uso.json")
    (tmp_path / "uso.json").write_text(json.dumps({"dia": time.strftime("%Y-%m-%d"), "n": animacoes.MAX_DIA}), encoding="utf-8")
    if (animacoes.SKILLS / "graph" / "build.py").exists() and (animacoes.RAIZ / "kit" / "node_modules").exists():
        with pytest.raises(ValueError, match="teto"):
            animacoes.gerar("graph", {"label": "x", "values": [1, 2]})


def test_disponiveis():
    assert animacoes.disponiveis() == ["breakdown", "graph", "map-route", "minimalistic-graphics"]
