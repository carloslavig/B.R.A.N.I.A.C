from braniac import freelas as F


def _it(i, titulo="Build a landing page", texto="need a website"):
    return {"id": i, "fonte": "x", "titulo": titulo, "texto": texto, "url": "http://x/" + i}


def test_busca_filtra_dedup_e_ordena_por_nota(monkeypatch, tmp_path):
    monkeypatch.setattr(F, "PASTA", tmp_path)
    monkeypatch.setattr(F, "ARQ", tmp_path / "v.json")
    itens = [_it("a"), _it("b", "Nurse wanted", "hospital shift"), _it("c", "Python scraper", "scrape prices")]
    fontes = {"f": lambda: itens, "quebrada": lambda: 1 / 0}
    notas = {"a": 5, "c": 9}
    llm = lambda p, timeout=0: {"nota": notas["c" if "scraper" in p else "a"], "motivo": "m", "proposta": "p"}
    feitos, erros = F.buscar(llm=llm, fontes=fontes)
    assert [x["id"] for x in feitos] == ["c", "a"]  # "b" nem passou no filtro
    assert "quebrada" in erros
    assert F.buscar(llm=llm, fontes=fontes)[0] == []  # já visto
    assert [x["id"] for x in F.listar()] == ["c"]  # só nota >= 6


def test_tick_avisa_so_nota_alta_e_so_a_cada_6h(monkeypatch, tmp_path):
    from datetime import datetime
    monkeypatch.setattr(F, "PASTA", tmp_path)
    monkeypatch.setattr(F, "ARQ", tmp_path / "v.json")
    msgs = []
    llm = lambda p, timeout=0: {"nota": 8, "motivo": "m", "proposta": "p"}
    f = {"f": lambda: [_it("a")]}
    assert not F.tick(datetime(2026, 11, 5, 3), msgs.append, llm, f, True)  # madrugada
    assert F.tick(datetime(2026, 11, 5, 10), msgs.append, llm, f, True)
    assert len(msgs) == 1 and "id a" in msgs[0]
    assert not F.tick(datetime(2026, 11, 5, 11), msgs.append, llm, f, True)  # < 6 h


def test_nota_invalida_da_ia_vira_zero():
    assert F.triar(_it("z"), llm=lambda p, timeout=0: {"nota": "alta"})["nota"] == 0
