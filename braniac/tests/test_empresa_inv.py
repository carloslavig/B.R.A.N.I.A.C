from braniac import empresa_inv as q


def test_fluxo_paper_e_vetos(tmp_path, monkeypatch):
    monkeypatch.setattr(q, "CARTEIRA_JSON", tmp_path / "c.json")
    monkeypatch.setattr(q, "PROPOSTAS_JSON", tmp_path / "p.json")
    assert "vetada" in q.propor("swing", "AAPL", 100, 95, 112)           # sem capital
    q.depositar("swing", 10000)
    assert "vetada" in q.propor("swing", "AAPL", 100, 105, 112)          # stop acima da entrada
    assert "vetada" in q.propor("swing", "AAPL", 100, 95, 102)           # retorno/risco baixo
    assert "Aguardando" in q.propor("swing", "AAPL", 100, 95, 112)
    assert "PAPEL" in q.aprovar("Q004")
    assert q.carteira()["swing"]["posicoes"][0]["qtd"] == 10             # 0,5% de 10k / 5 por unidade
    assert "+" in q.fechar("Q004", 110)
    assert q.carteira()["swing"]["capital"] == 10100


def test_circuit_breaker(tmp_path, monkeypatch):
    monkeypatch.setattr(q, "CARTEIRA_JSON", tmp_path / "c.json")
    monkeypatch.setattr(q, "PROPOSTAS_JSON", tmp_path / "p.json")
    q.depositar("daytrade", 10000)
    c = q.carteira()
    c["daytrade"]["fechadas"].append({"pnl": -400, "fechada_em": "2000-01-01T00:00:00", "ts_fechada": __import__("time").time()})
    q._gravar(q.CARTEIRA_JSON, c)
    assert "circuit breaker" in q.propor("daytrade", "SPY", 100, 99, 103)
