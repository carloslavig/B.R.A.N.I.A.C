# -*- coding: utf-8 -*-
"""Chaves do .env criptografadas com DPAPI (14/10/2026)."""
import os

import pytest

from braniac import segredos

pytestmark = pytest.mark.skipif(os.name != "nt", reason="DPAPI so existe no Windows")


def test_ida_e_volta():
    c = segredos.proteger("gsk_teste_123")
    assert c.startswith("dpapi:") and "gsk_teste_123" not in c
    assert segredos.revelar(c) == "gsk_teste_123"
    assert segredos.proteger(c) == c and segredos.revelar("texto puro") == "texto puro"


def test_env_em_texto_puro_vira_criptografado_e_continua_lido(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# chaves\nGROQ_API_KEY=gsk_abc\nPORTA=20128\nTELEGRAM_BOT_TOKEN=\"123:xyz\"\n", encoding="utf-8")
    vals = segredos.ler_env(env)
    assert vals == {"GROQ_API_KEY": "gsk_abc", "PORTA": "20128", "TELEGRAM_BOT_TOKEN": "123:xyz"}
    txt = env.read_text(encoding="utf-8")
    assert "gsk_abc" not in txt and "123:xyz" not in txt and "PORTA=20128" in txt and "# chaves" in txt
    assert segredos.ler_env(env) == vals          # segunda leitura abre o criptografado


def test_carregar_env_do_router_abre_as_chaves(tmp_path, monkeypatch):
    from braniac import router
    env = tmp_path / ".env"
    env.write_text("CHAVE_TESTE_SEGREDO_API_KEY=abc123\n", encoding="utf-8")
    monkeypatch.delenv("CHAVE_TESTE_SEGREDO_API_KEY", raising=False)
    router.carregar_env(env)
    assert os.environ["CHAVE_TESTE_SEGREDO_API_KEY"] == "abc123" and "abc123" not in env.read_text(encoding="utf-8")
    monkeypatch.delenv("CHAVE_TESTE_SEGREDO_API_KEY")
