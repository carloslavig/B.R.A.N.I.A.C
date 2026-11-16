from braniac import financeiro as F


def test_eh_pergunta():
    for t in ("quanto tem na conta do Dono?", "qual o saldo", "como ta a meta financeira", "me manda o extrato", "quanto falta pra meta?"):
        assert F.eh_pergunta(t), t
    for t in ("bom dia", "vou buscar o pai"):
        assert not F.eh_pergunta(t), t


def test_resposta_sem_leitura_e_com_leitura():
    assert "Ainda não consegui" in F.resposta()
    from datetime import datetime
    F.verificar(lambda m: None, datetime(2026, 11, 5, 10, 0), lambda h: (300.0, [{"data": "2026-11-05", "desc": "Pix X", "valor": 50.0, "hora": "09:00"}]))
    r = F.resposta()
    assert "R$ 300,00" in r and "Pix X" in r and "faltam" in r


def test_perguntas_do_dono():
    for t in ("jarvis, relatorio financeiro", "relatório financeiro", "como está a meta desse mês?", "como ta a meta", "qual meu saldo?", "quanto falta pra bater a meta?",
              "já bati a meta?", "como anda minha grana", "jarvis, quanto tem na minha conta?", "me fala o saldo da infinitepay", "situação financeira", "quanto já entrou hoje na conta",
              "falta quanto pra 1600", "meta do mês"):
        assert F.eh_pergunta(t), t
    for t in ("gera uma imagem no meta ai", "bom dia jarvis", "relatório do atendimento", "me lembra de pagar a conta de luz amanhã"):
        assert not F.eh_pergunta(t), t


def test_mudanca_no_saldo_avisa_o_jarvis_com_efeito_na_meta():
    from datetime import datetime
    enviados = []
    h = datetime(2026, 11, 3, 10, 0)
    F.verificar(enviados.append, h, lambda d: (500.0, []))
    n0 = len(enviados)                                                                 # 1a leitura: sem aviso de mudanca
    F.ESTADO.write_text(F.ESTADO.read_text().replace('"ts"', '"x"'))
    F.verificar(enviados.append, h, lambda d: (380.0, [{"data": "2026-11-03", "desc": "Pix MERCADO", "valor": -120.0, "hora": "09:50"}]))
    msg = [m for m in enviados[n0:] if "Mudança na conta" in m]
    assert msg and "diminuiu" in msg[0] and "R$ 120,00" in msg[0] and "MERCADO" in msg[0] and "faltam" in msg[0] and "aumentou" in msg[0]
