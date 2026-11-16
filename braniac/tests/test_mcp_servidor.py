from braniac import barramento as B, mcp_servidor as M


def test_so_agentes_sem_dado_pessoal_respondem():
    assert M.agentes_publicos() == ["Ada", "Forja", "Sultão"]
    assert "Forja" in M.listar_agentes_publicos() and "Cofre" not in M.listar_agentes_publicos()


def test_agente_pessoal_e_recusado_e_nao_levanta_dados():
    for nome in ("Cofre", "Vaquinha", "Alma", "Ilhéu", "Compasso", "Cabo Tito", "Correio"):
        r = M.consultar_agente(nome, "quanto tenho de saldo?")
        assert "dados pessoais" in r and "R$" not in r, nome
    assert "desconhecido" in M.consultar_agente("Fulano", "oi")


def test_consulta_valida_passa_pelo_barramento():
    r = M.consultar_agente("Forja", "como está o braniac?")
    assert "Manutenção" in r or "testes" in r
    h = [(m["de"], m["para"], m["tipo"]) for m in B.historico(4)]
    assert h[-2:] == [("Jarvis", "Forja", "pedido"), ("Forja", "Jarvis", "resposta")]
    assert M.consultar_agente("Forja", "") == "Faltou a pergunta."
