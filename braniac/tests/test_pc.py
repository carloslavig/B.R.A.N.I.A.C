

def test_notebook_tela_travas_e_ciclo(monkeypatch):
    from braniac import tela
    monkeypatch.setattr(tela, "janela_ativa", lambda: "Bloco de Notas")
    monkeypatch.setattr(tela, "foto", lambda: b"x")
    feito = []
    monkeypatch.setattr(tela, "_executar", lambda a: feito.append(a["acao"]))
    passos = iter([{"acao": "clicar", "x": 1, "y": 1}, {"acao": "fim", "resultado": "ok"}])
    assert tela.tarefa("abre algo", decidir=lambda *a: next(passos), pausa=0) == "ok" and feito == ["clicar"]
    assert "senha" in tela.tarefa("digita a senha do banco").lower()
    monkeypatch.setattr(tela, "janela_ativa", lambda: "Nubank - Google Chrome")
    assert tela.tarefa("olha o saldo", decidir=lambda *a: {"acao": "fim"}, pausa=0).startswith("Parei")
    with __import__("pytest").raises(ValueError):
        tela.tecla("alt+f4")
