# -*- coding: utf-8 -*-
"""Leads do Google Maps: so as travas (sem abrir Chrome nem acessar o Google)."""
import json
import time

import pytest

from braniac import leads_maps


def test_pedido_invalido_segredo_e_teto(tmp_path, monkeypatch):
    monkeypatch.setattr(leads_maps, "ARQ_USO", tmp_path / "uso.json")
    with pytest.raises(ValueError, match="tipo de negocio"):
        leads_maps.buscar("", "Cidade")
    with pytest.raises(ValueError, match="segredo"):
        leads_maps.buscar("padarias com senha", "Cidade, MT")
    (tmp_path / "uso.json").write_text(json.dumps({"dia": time.strftime("%Y-%m-%d"), "n": leads_maps.MAX_BUSCAS_DIA}), encoding="utf-8")
    if (leads_maps.KIT / "scripts" / "scrape.py").exists():
        with pytest.raises(ValueError, match="teto"):
            leads_maps.buscar("padarias", "Cidade, MT")


def test_kit_ausente(tmp_path, monkeypatch):
    monkeypatch.setattr(leads_maps, "ARQ_USO", tmp_path / "uso.json")
    monkeypatch.setattr(leads_maps, "KIT", tmp_path / "nao-existe")
    with pytest.raises(RuntimeError, match="kit do scraper"):
        leads_maps.buscar("padarias", "Cidade, MT")
