# -*- coding: utf-8 -*-
"""Documento recebido no WhatsApp: o Jarvis avisa, baixa e o Claude ajuda e devolve (caso do Amigo, 17/10/2026: o arquivo ficou sem resposta)."""
import pytest
from pathlib import Path
from braniac import atender, claude_agent, contexto, whatsapp, wpp_doc


@pytest.fixture(autouse=True)
def isolado(tmp_path, monkeypatch):
    monkeypatch.setattr(wpp_doc, "RECEBIDOS", tmp_path / "recebidos")
    monkeypatch.setitem(wpp_doc._USO, "dia", None)
    monkeypatch.setitem(wpp_doc._USO, "n", 0)


def test_nome_do_doc_e_pedido():
    assert wpp_doc.nome_do_doc("[DOC:0.6.html]") == "0.6.html"
    assert wpp_doc.nome_do_doc("[IMAGEM]") is None
    assert wpp_doc.pedido_do_contato(["[DOC:a.html]", "melhora o codigo", "[AUDIO]"]) == "melhora o codigo"


def test_tarefa_para_o_claude_tem_o_essencial(tmp_path):
    t = wpp_doc.tarefa_para_o_claude("Amigo", "0.6.html", tmp_path / "0.6.html", ["[DOC:0.6.html]", "melhora esse jogo"], ["E: oi"])
    assert "melhora esse jogo" in t and "CÓPIA" in t and "melhorado" in t and "wpp_arquivo.enviar_arquivo('Amigo'" in t and "nunca altere o original" in t


def test_baixou_avisa_a_pessoa_e_chama_o_claude(tmp_path, monkeypatch):
    monkeypatch.setattr(wpp_doc, "baixar", lambda c, a: tmp_path / a)
    avisos, tarefas = [], []
    linha = wpp_doc.tratar("Amigo", {"msgs": ["[DOC:0.6.html]", "me ajuda a melhorar"], "ctx": []}, ["[DOC:0.6.html]"], avisos.append, tarefas.append)
    assert "Recebi o arquivo 0.6.html" in avisos[0] and len(tarefas) == 1 and "me ajuda a melhorar" in tarefas[0] and linha.startswith("📄")


def test_nao_conseguiu_baixar_avisa_sem_chamar_o_claude(monkeypatch):
    def falha(c, a):
        raise wpp_doc.DocErro("o download do arquivo não terminou")
    monkeypatch.setattr(wpp_doc, "baixar", falha)
    avisos, tarefas = [], []
    linha = wpp_doc.tratar("Amigo", {"msgs": ["[DOC:x.pdf]"]}, ["[DOC:x.pdf]"], avisos.append, tarefas.append)
    assert "não consegui abri-lo" in avisos[0] and not tarefas and linha.startswith("⚠️")


def test_executavel_e_recusado_e_teto_diario(monkeypatch):
    with pytest.raises(wpp_doc.DocErro, match="executáveis"):
        wpp_doc.baixar("Fulano", "instalador.exe")
    monkeypatch.setitem(wpp_doc._USO, "dia", wpp_doc.date.today().isoformat())
    monkeypatch.setitem(wpp_doc._USO, "n", wpp_doc.MAX_POR_DIA)
    avisos, tarefas = [], []
    wpp_doc.tratar("Amigo", {"msgs": []}, ["[DOC:a.html]"], avisos.append, tarefas.append)
    assert "Dono vai olhar" in avisos[0] and not tarefas


def test_atender_trata_documento_em_vez_de_ignorar(monkeypatch, tmp_path):
    it = {"nome": "Amigo Souza", "nl": 1, "msgs": ["[DOC:0.6.html]", "melhora o código"], "ctx": [], "autores": set(), "midia": True}
    monkeypatch.setattr(atender, "coletar", lambda *a, **k: [it])
    monkeypatch.setattr(wpp_doc, "baixar", lambda c, a: tmp_path / a)
    enviados, tarefas = [], []
    monkeypatch.setattr(whatsapp, "enviar", lambda n, t: enviados.append((n, t)) or "✅ enviado")
    monkeypatch.setattr(atender, "_enviar_resposta", lambda n, t, i: enviados.append((n, t)) or "✅ enviado")
    monkeypatch.setattr(claude_agent, "executar_em_segundo_plano", lambda tarefa, cb: tarefas.append(tarefa))
    monkeypatch.setattr(atender, "decidir", lambda *a, **k: pytest.fail("documento nao passa pela decisao comum"))
    atender.atender(relatar=False)
    assert enviados and "Recebi o arquivo 0.6.html" in enviados[0][1] and len(tarefas) == 1 and "melhora o código" in tarefas[0]


def test_deteccao_no_whatsapp_so_documentos_pendentes_da_pessoa():
    js = Path(__file__).resolve().parents[2].joinpath("local-ia", "wpp_local.py").read_text(encoding="utf-8")
    assert "document-" in js and "ultimaNossa" in js and "[DOC:" in js
