from braniac import barramento as B, delegacao as D


def test_so_consulta_quando_e_pergunta_e_nao_acao():
    assert D.eh_consulta("como está a vaquinha?") and D.eh_consulta("quanto falta pra meta")
    assert not D.eh_consulta("me manda o link do site da vaquinha") and not D.eh_consulta("manda mensagem pra Parceira") and not D.eh_consulta("/ligar")


def test_escolhe_o_agente_certo():
    assert D.escolher("como está a vaquinha?") == ["Vaquinha"]
    assert D.escolher("como está a progressão de ganhos pra bater a meta de 1600?")[0] == "Cofre" and "Vaquinha" not in D.escolher("como está a progressão de ganhos pra bater a meta de 1600?")
    assert D.escolher("o que eu tenho na agenda hoje?") == ["Compasso"]
    assert D.escolher("como está o exame do exército?")[0] == "Cabo Tito"


def test_jarvis_pergunta_agente_responde_e_fica_no_barramento():
    r = D.atender("como está a vaquinha?")
    assert r["agentes"] == ["Vaquinha"] and r["local_only"] and "Falei com Vaquinha" in r["texto"]
    h = [(m["de"], m["para"], m["tipo"]) for m in B.historico(5)]
    assert h[-2:] == [("Jarvis", "Vaquinha", "pedido"), ("Vaquinha", "Jarvis", "resposta")]
    assert "ele quer saber" in B.historico(5)[-2]["texto"]


def test_todo_agente_responde_com_dados_ou_diz_que_nao_tem():
    for nome in D.AGENTES:
        r = D.consultar(nome, "como está isso?")
        assert r["texto"] and r["resumo"], nome


def test_consulta_rapida_devolve_dados_do_agente(monkeypatch):
    monkeypatch.setitem(D.AGENTES, "Teste", ("x", True, lambda p: ("dados ok", "resumo ok")))
    r = D.consultar("Teste", "como está?")
    assert r["texto"] == "dados ok" and r["resumo"] == "resumo ok" and r["local_only"]


def test_agente_que_demora_vira_aviso_sem_travar(monkeypatch):
    import threading, time
    solta = threading.Event()
    monkeypatch.setitem(D.AGENTES, "Lerdo", ("x", True, lambda p: (solta.wait(5), ("tarde", "tarde"))[1]))
    monkeypatch.setattr(D, "TEMPO_AGENTE", 0.2)
    t0 = time.time()
    r = D.consultar("Lerdo", "como está?")
    solta.set()
    assert time.time() - t0 < 2 and r["texto"] == "O agente Lerdo demorou para responder agora; tente de novo em instantes." and r["resumo"] == "demorou"


def test_aviso_de_agente_passa_pelo_jarvis():
    enviados = []
    D.via_jarvis("Correio", enviados.append)("chegou e-mail")
    assert enviados == ["chegou e-mail"] and B.historico(3)[-1]["tipo"] == "alerta" and B.historico(3)[-1]["para"] == "Jarvis"


def test_opiniao_e_reconhecida_e_acha_o_nome():
    assert D.eh_opiniao("Jarvis, o que você acha de Layla?") and D.eh_opiniao("vale a pena o site da Cliente?")
    assert not D.eh_opiniao("o que tem na agenda hoje?") and not D.eh_opiniao("manda o que você acha pra Parceira")
    assert D._entidade("Jarvis, o que você acha de Layla?") == "Layla" and D._entidade("o que você acha disso?") is None


def test_opiniao_sem_agente_varre_o_banco_inteiro_e_sem_registro_pede_escalada(monkeypatch):
    from braniac import banco
    monkeypatch.setattr(D, "escolher", lambda *a, **k: [])
    monkeypatch.setattr(banco, "consultar", lambda *a, **k: ("[dossie] Layla é a assistente virtual da loja", True))
    r = D.atender("o que você acha de Layla?")
    assert r["agentes"] == ["Banco"] and "assistente virtual" in r["texto"] and not r["vazio"]
    monkeypatch.setattr(banco, "consultar", lambda *a, **k: ("", False))
    assert D.atender("o que você acha de Zorbax?")["vazio"]
    assert D.atender("o que você acha disso?") is None      # sem nome proprio: segue para a IA com as ferramentas
