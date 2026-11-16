# -*- coding: utf-8 -*-
from braniac import faxina_abas as f


def test_fecha_so_a_parada_e_nao_essencial():
    v = {}
    abas = [{"id": "w", "url": "https://web.whatsapp.com/"}, {"id": "g", "url": "https://gemini.google.com/app"},
            {"id": "t", "url": "https://www.tiktok.com/foryou"}]
    assert f.escolher(abas, v, 0) == []                 # primeira vez: so anota
    abas[2]["url"] = "https://www.tiktok.com/upload"    # navegou: relogio zera
    assert f.escolher(abas, v, 3000) == []
    assert f.escolher(abas, v, 3700) == ["g"]           # gemini parado ha mais de 1h; whatsapp nunca; tiktok ainda nao
    assert "g" not in v and "w" in v
    assert f.escolher(abas[:1] + abas[2:], v, 6700) == ["t"]


def test_desligavel(monkeypatch):
    monkeypatch.setenv("BRANIAC_FAXINA_ABAS", "0")
    assert f.tick() == 0
