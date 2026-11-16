# -*- coding: utf-8 -*-
"""Leitura do Airbnb (textos reais da caixa de entrada e das conversas) e protecao do anuncio do Amiga."""
from braniac import airbnb


def test_linha_enviada_por_nos():
    l = airbnb.parse_linha("2692213014", "Lidas. 8 – 9 de out.. Quarto B · casa com piscina, 500m da praia. Graciely. A última mensagem 22:50 enviada é: Você: Convite enviado.")
    assert l["hospede"] == "Graciely" and l["anuncio"].startswith("Quarto B") and l["ultima_de"] == "voce" and not l["nao_lida"]
    assert l["previa"] == "Convite enviado" and l["quando"] == "22:50" and not airbnb.pendente_de_resposta(l)


def test_linha_do_hospede_e_nao_lida():
    l = airbnb.parse_linha("2682241976", "Não lidas. Check-in hoje. Quarto A · casa com piscina, 500m da praia. João Vitor. A última mensagem 15:18 enviada é: João Vitor: A caminho, chegando em breve.")
    assert l["nao_lida"] and l["ultima_de"] == "hospede" and l["meta"] == "Check-in hoje" and airbnb.pendente_de_resposta(l)


def test_datas_com_ponto_nao_quebram_o_anuncio_nem_o_hospede():
    l = airbnb.parse_linha("1", "Lidas. 31 de dez. de 2026 – 3 de jan. de 2027. Casa Casa · 3 quartos e piscina. Jeovana. A última mensagem 21:39 enviada é: Jeovana: Ok. Obrigado.")
    assert l["hospede"] == "Jeovana" and l["anuncio"].startswith("Casa Princesinha") and "2027" in l["meta"] and l["ultima_de"] == "hospede"


def test_conversa_do_suporte_do_airbnb_nao_pede_resposta():
    l = airbnb.parse_linha("2", "Lidas. Encerrado. Marcio. Atendimento ao Cliente Airbnb. A última mensagem 16:59 enviada é: Como nos saímos?.")
    assert l["suporte_airbnb"] and not airbnb.pendente_de_resposta(l)


def test_anuncio_do_rocha_amiga_e_marcado_como_protegido():
    l = airbnb.parse_linha("3", "Lidas. Apartamento completo - Perto da praia e de tudo. Paulo. A última mensagem 10:00 enviada é: Paulo: Oi.")
    assert l["protegido"] and airbnb.ANUNCIO_PROTEGIDO.search("Arleo AP")


def test_mensagens_quem_escreveu_pela_cor_e_cabecalho_em_ordem_visual():
    itens = [  # fora de ordem de proposito: o 'y' manda
        {"txt": "Jeovana · Responsável pela reserva\n21:39\nOk. Obrigado", "escuro": False, "y": 900},
        {"txt": "15:18\nBoa tarde, estadia mínima pra esse período é 5 dias\nLida por Jeovana", "escuro": True, "y": 300},
        {"txt": "Jeovana · Responsável pela reserva\n13:12\nBoa tarde! Gostaria de saber mais", "escuro": False, "y": 100},
        {"txt": "Consulta de reserva\nR$ 3.138,17 · 16 hóspedes\nVocê tem até 7 de out. para responder\nResponder", "escuro": False, "y": 200},
        {"txt": "Mae · Anfitriã(o)\n16:17\nSó se você quiser esticar", "escuro": False, "y": 500},
        {"txt": "Domingo tem vaga", "escuro": False, "y": 560},
    ]
    ms = airbnb.parse_mensagens(itens)
    assert [(m["de"]) for m in ms] == ["hospede", "sistema", "voce", "anfitriao", "anfitriao", "hospede"]
    assert ms[0]["texto"].startswith("Boa tarde! Gostaria") and ms[2]["texto"] == "Boa tarde, estadia mínima pra esse período é 5 dias"   # 'Lida por' removido
    assert ms[1]["nome"] == "Airbnb" and ms[3]["nome"] == "Mae" and ms[4]["texto"] == "Domingo tem vaga"


def test_cartao_confirmado_com_cabecalho_do_hospede_e_sistema():
    ms = airbnb.parse_mensagens([{"txt": "Adislan · Responsável pela reserva\nConfirmado Quarto A · 11 – 12 de out. de 2026 · R$ 175,83", "escuro": False, "y": 1}])
    assert ms[0]["de"] == "sistema"


class AbFalso(airbnb.AB):
    """AB sem navegador: devolve respostas prontas para o JS."""
    def __init__(self, respostas):
        super().__init__()
        self.respostas, self.enviados, self.nav = respostas, [], []

    def js(self, expr):
        for chave, val in self.respostas.items():
            if chave in expr:
                return val(expr) if callable(val) else val
        return None

    def cmd(self, metodo, params=None):
        if metodo == "Input.insertText":
            self.enviados.append(params["text"])
        return {}

    def ir(self, url):
        self.nav.append(url)

    def abrir(self, thread_id):
        return True


def test_enviar_recusa_texto_vazio_longo_e_confirma_quando_a_mensagem_aparece(monkeypatch):
    monkeypatch.setattr(airbnb.time, "sleep", lambda s: None)
    contagem = iter([5, 5, 6])
    ab = AbFalso({"innerText||'').trim():null": "Oi, tudo bem?", "MessageOuter]').length": lambda e: next(contagem),
                  "#message_input')||document": True, "messaging_compose_bar_send_button": True})
    assert ab.enviar("123", "   ") == (False, "texto vazio")
    assert ab.enviar("123", "x" * 901)[0] is False
    ok, motivo = ab.enviar("123", "Oi,   tudo bem?")
    assert ok and ab.enviados == ["Oi, tudo bem?"]


def test_enviar_nao_envia_se_o_texto_nao_entrou_na_caixa(monkeypatch):
    monkeypatch.setattr(airbnb.time, "sleep", lambda s: None)
    ab = AbFalso({"innerText||'').trim():null": "", "MessageOuter]').length": 5, "#message_input')||document": True, "messaging_compose_bar_send_button": True})
    ok, motivo = ab.enviar("123", "Olá")
    assert not ok and "nada foi enviado" in motivo
