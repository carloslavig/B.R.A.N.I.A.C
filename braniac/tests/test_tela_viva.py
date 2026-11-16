# -*- coding: utf-8 -*-
import pytest

from braniac import tela_viva


def test_dominio_fora_da_lista_e_recusado():
    with pytest.raises(tela_viva.TelaErro):
        tela_viva.captura("banco.exemplo.com")
    with pytest.raises(tela_viva.TelaErro):
        tela_viva.acao("banco.exemplo.com", "clique", 1, 1)


def test_whatsapp_fica_so_leitura_enquanto_o_braniac_mexe(monkeypatch):
    monkeypatch.setattr(tela_viva, "_agente_agindo", lambda: True)
    with pytest.raises(tela_viva.TelaErro, match="mexendo"):
        tela_viva.acao("web.whatsapp.com", "clique", 5, 5)


def test_campo_de_senha_nao_recebe_texto(monkeypatch):
    class Falsa:
        def cmd(self, metodo, params=None):
            return {"result": {"value": True}} if metodo == "Runtime.evaluate" else {}

        def fechar(self):
            pass

    monkeypatch.setattr(tela_viva, "_aba", lambda d: {})
    monkeypatch.setattr(tela_viva, "_Sessao", lambda aba: Falsa())
    monkeypatch.setattr(tela_viva, "_agente_agindo", lambda: False)
    with pytest.raises(tela_viva.TelaErro, match="senha"):
        tela_viva.acao("airbnb.com.br", "texto", texto="x")
