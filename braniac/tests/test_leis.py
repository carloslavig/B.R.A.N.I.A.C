# -*- coding: utf-8 -*-
"""Consulta de leis (acervo legalize-br): so [\w-] vira nome de arquivo, busca nao quebra com aspas/pontuacao."""
from braniac import leis


def test_ler_so_aceita_id_seguro():
    assert leis.ler("../../.env") == "id invalido"
    assert leis.ler("nao-existe-123") == "norma nao encontrada"


def test_buscar_sem_indice_ou_sem_termo_nao_quebra(tmp_path, monkeypatch):
    monkeypatch.setattr(leis, "DB", tmp_path / "x.db")
    assert "indice" in leis.buscar("lei")
    (tmp_path / "x.db").write_bytes(b"")
    assert "Diga" in leis.buscar('"%$#')


def test_indexa_e_busca_um_arquivo(tmp_path, monkeypatch):
    (tmp_path / "br").mkdir()
    (tmp_path / "br" / "123.md").write_text("---\ntitulo: Decreto no 1, de 1 de Janeiro de 2000\nrango: Decreto\nfecha_publicacion: 2000-01-01\nextra:\n  ementa: Dispoe sobre feijao\n---\n\nArt. 1o Feijao e arroz.\n", encoding="utf-8")
    monkeypatch.setattr(leis, "PASTA", tmp_path / "br")
    monkeypatch.setattr(leis, "DB", tmp_path / "l.db")
    leis.indexar()
    assert "[123] Decreto 2000-01-01" in leis.buscar('feijao "arroz"')
    assert "Art. 1o" in leis.ler("123")


def test_planalto_acha_a_primeira_url_valida_e_ignora_pagina_de_erro(monkeypatch):
    class R:
        def __init__(self, t): self.t = t
        def read(self): return self.t.encode("latin-1")
    visitadas = []

    def falso(req, timeout=0):
        visitadas.append(req.full_url)
        if len(visitadas) == 1:
            return R("<html><body>Ocorreu um erro! O conteúdo não foi encontrado.</body></html>")   # erro do Planalto vem com HTTP 200
        return R("<style>x{}</style><p>DECRETO Nº 703. Revogado pelo Decreto nº 13.110.</p>" + "texto " * 100)
    monkeypatch.setattr(leis.urllib.request, "urlopen", falso)
    r = leis.planalto("decreto", "703", 1992)
    assert len(visitadas) == 2 and "Revogado pelo Decreto nº 13.110" in r and "x{}" not in r
    assert "Use tipo" in leis.planalto("portaria", "1", 2020)
