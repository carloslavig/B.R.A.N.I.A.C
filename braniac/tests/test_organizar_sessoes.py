# -*- coding: utf-8 -*-
import pytest
from braniac import b2, organizar_sessoes as o


@pytest.fixture(autouse=True)
def isolado(tmp_path, monkeypatch):
    monkeypatch.setattr(b2, "DB", tmp_path / "b2.db")


def test_move_de_geral_para_o_assunto_sem_tocar_o_resto():
    a = b2.acao({"acao": "criar_conversa", "titulo": "a esteira ta funcionando?"})["novo"]
    b = b2.acao({"acao": "criar_conversa", "titulo": "Quem é você"})["novo"]
    assert len(o.organizar(aplicar=False)) == 1
    o.organizar()
    e = b2.estado()
    nomes = {p["id"]: p["nome"] for p in e["projetos"]}
    proj = {c["id"]: nomes[c["projeto"]] for c in e["conversas"]}
    assert proj[a] == "🎬 Parceiro / Vídeos" and proj[b] == "Geral"
    assert o.organizar() == []
