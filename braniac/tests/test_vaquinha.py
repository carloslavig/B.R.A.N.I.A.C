import json

from braniac import vaquinha as V


def mov(desc, valor, hora="10:00"):
    return {"data": "2026-10-27", "desc": desc, "valor": valor, "hora": hora}


def test_desligada_nao_le_nada():
    chamou = []
    assert V.ciclo(lambda m: None, lambda: chamou.append(1)) is None and not chamou
    assert "ainda não foi ligada" in V.resposta()


def test_soma_so_pix_novos_e_publica(tmp_path):
    antigos = [mov("Pix antigo", 500.0, "08:00")]
    assert V.configurar("x", ler=lambda: antigos) == 1          # o que ja estava no extrato nao conta
    avisos, deploys = [], []
    movs = antigos + [mov("Pix MARIA SILVA", 50.0), mov("Pix enviado teste", -10.0, "10:05"), mov("Vendas", 20.0, "10:10")]
    total = V.ciclo(avisos.append, lambda: movs, lambda: deploys.append(1) or (True, "ok"))
    assert total == 50.0                                         # so Pix recebido novo (nao saida, nao 'Vendas')
    assert len(avisos) == 1 and "50,00" in avisos[0] and "6000" in avisos[0]
    assert json.loads((V.SITE / "total.json").read_text())["arrecadado"] == 50.0
    assert len(deploys) == 1 and V._estado()["publicado"] == 50.0
    assert V.ciclo(avisos.append, lambda: movs, lambda: deploys.append(1) or (True, "ok")) == 50.0
    assert len(avisos) == 1 and len(deploys) == 1                # nada novo: nao avisa nem republica


def test_site_publico_nao_tem_nome_de_doador(tmp_path):
    V.configurar("x", ler=lambda: [])
    V.ciclo(lambda m: None, lambda: [mov("Pix MARIA SILVA", 80.0)], lambda: (True, ""))
    assert "MARIA" not in (V.SITE / "total.json").read_text()


def test_deploy_com_falha_tenta_de_novo_e_ajuste_manual():
    V.configurar("x", ler=lambda: [])
    V.ciclo(lambda m: None, lambda: [mov("Pix A", 10.0)], lambda: (False, "erro"))
    assert V._estado().get("publicado") is None and "erro" in V._estado()["ultimo_erro"]
    assert V.ajustar(100, "pix de antes") == 110.0


def test_valor_da_resposta():
    v = V.valor_da_resposta
    assert v("R$ 350,00") == 350.0 and v("1.234,56") == 1234.56 and v("tem 350 reais") == 350.0 and v("nada ainda") == 0.0
    assert v("caiu 50 e 100") is None and v("oi") is None and v("999999") is None


def test_pergunta_a_cada_6h_e_resposta_atualiza_o_site():
    from datetime import datetime
    V.ligar_manual()
    parceira, dono, deploys = [], [], []
    assert V.tick(parceira.append, dono.append, datetime(2026, 10, 27, 8, 5)) == "perguntou" and V.aguardando()
    assert V.tick(parceira.append, dono.append, datetime(2026, 10, 27, 8, 15)) is None                    # nao pergunta de novo na mesma hora
    assert V.tick(parceira.append, dono.append, datetime(2026, 10, 27, 14, 0)) == "perguntou"
    assert len(parceira) == 2 and "recebemos" in parceira[0] and "gastamos" in parceira[0]
    r = V.registrar_valores({"recebido": 350.0, "gasto": 100.0}, "Parceira", lambda: deploys.append(1) or (True, "ok"), dono.append)
    assert "350,00" in r and "Site atualizado" in r and not V.aguardando() and "gasto R$ 100,00" in dono[0]
    assert json.loads((V.SITE / "total.json").read_text())["arrecadado"] == 350.0
    assert len(deploys) == 1 and "350,00" in dono[0]
    assert V.ciclo(lambda m: None) is None                                                              # modo Parceira: nao le banco nenhum


def test_valores_recebido_e_gasto():
    v = V.valores_da_resposta
    assert v("recebemos R$ 350 e gastamos R$ 100") == {"recebido": 350.0, "gasto": 100.0, "saldo": None}
    assert v("gastamos 80, recebemos 1.200,50") == {"recebido": 1200.5, "gasto": 80.0, "saldo": None}
    assert v("350 e 100") == {"recebido": 350.0, "gasto": 100.0, "saldo": None} and v("oi") == {} and v("1 2 3") == {}


def test_resposta_parcial_pergunta_o_que_falta():
    V.ligar_manual()
    dono, deploys = [], []
    r = V.registrar_valores({"recebido": 350.0, "gasto": None}, "Parceira", lambda: deploys.append(1) or (True, ""), dono.append)
    assert "quanto já gastamos" in r and V.aguardando()
    r2 = V.registrar_valores({"recebido": 100.0, "gasto": None}, "Parceira", lambda: (True, ""), dono.append)      # so um numero: e o gasto
    assert "gasto R$ 100,00" in dono[-1] and not V.aguardando() and "Anotado" in r2
    assert json.loads((V.SITE / "total.json").read_text())["arrecadado"] == 350.0 and "gasto" not in (V.SITE / "total.json").read_text()   # gasto nao vai para o site


def test_saldo_na_conta_vira_recebido_mais_gasto():
    v = V.valores_da_resposta
    assert v("temos R$ 500 na conta")["saldo"] == 500.0 and v("temos R$ 500 na conta")["recebido"] is None
    assert v("saldo 420 e gastamos 80") == {"recebido": None, "gasto": 80.0, "saldo": 420.0}
    V.ligar_manual()
    dono = []
    r = V.registrar_valores({"recebido": None, "gasto": 100.0, "saldo": None} | {"recebido": 700.0}, "Parceira", lambda: (True, ""), dono.append)      # base: recebido 700, gasto 100
    r = V.registrar_valores({"saldo": 650.0}, "Parceira", lambda: (True, ""), dono.append)                                                           # saldo 650 -> recebido 750
    assert json.loads((V.SITE / "total.json").read_text())["arrecadado"] == 750.0 and "saldo R$ 650,00" in dono[-1] and "Anotado" in r


def test_recebemos_explicito_nao_vira_gasto_e_total_nao_diminui_sozinho():
    V.ligar_manual()
    dono = []
    V.registrar_valores({"recebido": 1374.0, "gasto": None}, "Parceira", lambda: (True, ""), dono.append)            # falta o gasto
    r = V.registrar_valores(V.valores_da_resposta("Recebemos 500"), "Parceira", lambda: (True, ""), dono.append, rotulado=V.tem_rotulo("Recebemos 500"))
    assert V._estado().get("gasto") is None and V._estado()["arrecadado"] == 1374.0       # 'Recebemos' NAO e gasto e o total nao foi sobrescrito
    assert "a mais" in r and V.confirmando() and "nada foi alterado" in dono[-1]
    assert V.resolver_confirmacao("a mais", lambda: (True, ""), dono.append) and V._estado()["arrecadado"] == 1874.0 and not V.confirmando()


def test_numero_solto_apos_perguntar_gasto_ainda_e_gasto_e_total_pode_substituir():
    V.ligar_manual()
    V.registrar_valores({"recebido": 1000.0, "gasto": None}, "Parceira", lambda: (True, ""), lambda m: None)
    assert V.tem_rotulo("500") is False
    V.registrar_valores(V.valores_da_resposta("500"), "Parceira", lambda: (True, ""), lambda m: None, rotulado=False)
    assert V._estado()["gasto"] == 500.0 and V._estado()["arrecadado"] == 1000.0
    V.registrar_valores({"recebido": 400.0, "gasto": None}, "Parceira", lambda: (True, ""), lambda m: None, rotulado=True)
    assert V.resolver_confirmacao("o total mesmo", lambda: (True, ""), lambda m: None) and V._estado()["arrecadado"] == 400.0
    assert V.resolver_confirmacao("oi", None, None) is None
