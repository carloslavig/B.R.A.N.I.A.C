# -*- coding: utf-8 -*-
"""Atendimento automatico do Airbnb: regras puras e ciclo completo com navegador falso (nada e enviado de verdade)."""
import time
from datetime import datetime

import pytest

from braniac import airbnb, airbnb_vigia as av

CFG = dict(av.CFG_PADRAO)
FC = "Bem vindo(a) Ana, vale lembrar que e um quarto privativo numa casa com areas compartilhadas."
from datetime import datetime as _dt, timedelta as _td
_MES = ["jan.", "fev.", "mar.", "abr.", "mai.", "jun.", "jul.", "ago.", "set.", "out.", "nov.", "dez."]
_AMANHA = _dt.now() + _td(days=1)
PRAZO_TESTE = f"{_AMANHA.day} de {_MES[_AMANHA.month - 1]} 21:46"     # sempre FUTURO: o teste nao pode depender do dia em que roda
CARTAO_CONSULTA = f"Consulta de reserva R$ 166,03 · 3 hóspedes 8 – 9 de out. de 2026 · Quarto B Você tem até {PRAZO_TESTE} AMT para responder Responder"


def linha(id_="10", hospede="Ana", anuncio="Quarto A · casa com piscina", previa="Tem vaga sábado?", quando=None, ultima="hospede", meta="8 – 9 de out."):
    quando = quando or datetime.now().strftime("%H:%M")
    return {"id": id_, "nao_lida": True, "meta": meta, "anuncio": anuncio, "hospede": hospede, "quando": quando,
            "ultima_de": ultima, "previa": previa, "suporte_airbnb": False, "protegido": bool(airbnb.ANUNCIO_PROTEGIDO.search(anuncio))}


class AbFalso:
    def __init__(self, linhas, msgs, log, ok=True, fc=FC, ok_reserva=True):
        self.linhas, self.msgs, self.log, self.ok, self.fc, self.ok_reserva = linhas, msgs, log, ok, fc, ok_reserva

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def conversas(self, n):
        return self.linhas

    def ler(self, id_, n):
        return {"hospede": "Ana", "mensagens": self.msgs}

    def enviar(self, id_, texto):
        if self.ok:
            self.log.append(("enviar", id_, texto))
        return self.ok, "" if self.ok else "falhou"

    def resposta_rapida(self, id_, titulo):
        return self.fc

    def decidir_reserva(self, id_, acao):
        if self.ok_reserva:
            self.log.append(("reserva", id_, acao))
        return self.ok_reserva, "" if self.ok_reserva else "botao nao achado"

    def conversas_(self):
        return self.linhas


@pytest.fixture(autouse=True)
def isolado(tmp_path, monkeypatch):
    monkeypatch.setattr(av, "ARQ", tmp_path / "estado.json")
    monkeypatch.setattr(av, "LOG", tmp_path / "log.txt")
    monkeypatch.setattr(av, "DATA", tmp_path)
    monkeypatch.setattr(av.memoria, "registrar_msg", lambda *a, **k: None)
    monkeypatch.setattr(av.memoria, "registrar_decisao", lambda *a, **k: None)


MSG_JA_ATENDIDA = [{"de": "voce", "texto": "Bem vindo(a)!"}, {"de": "hospede", "texto": "Tem vaga sábado?"}]
MSG_PRIMEIRA = [{"de": "hospede", "texto": "Tem vaga sábado?"}]


def rodar(linhas, msgs, decisao=("E", "Temos sim!"), ok=True, mensagens_de=None, **kw):
    log = []
    sessao = lambda: AbFalso(linhas, msgs, log, ok, **kw)
    feito = av.ciclo(CFG, sessao=sessao, decidir=lambda it, fl: decisao, mensagens_de=mensagens_de or (lambda c, ts: []))
    return feito, log


def enviados(log):
    return [x[2] for x in log if x[0] == "enviar"]


def test_desligado_por_padrao():
    assert not av.ligado()
    av.ligar()
    assert av.ligado()
    av.desligar()
    assert not av.ligado()


def test_janela_e_idade():
    assert av.dentro_da_janela(["07:00", "22:30"], datetime(2026, 10, 7, 12, 0))
    assert not av.dentro_da_janela(["07:00", "22:30"], datetime(2026, 10, 7, 23, 0))
    agora = datetime(2026, 10, 7, 12, 0)
    assert av.idade_horas("11:00", agora) == pytest.approx(1)
    assert av.idade_horas("ontem", agora) > 24
    assert av.idade_horas("seg", agora) is None


def test_valor_em_reais_e_barrado():
    assert not av.validar_airbnb("A diária é R$ 250 por noite")[0]
    assert not av.validar_airbnb("fica 250 reais")[0]
    assert av.validar_airbnb("Temos vaga sim, qual o período?")[0]


def test_responde_hospede_pendente_uma_unica_vez():
    feito, log = rodar([linha()], MSG_JA_ATENDIDA)
    assert enviados(log) == ["Temos sim!"] and feito["enviados"] == ["Ana (Airbnb)"]
    feito2, log2 = rodar([linha()], MSG_JA_ATENDIDA)
    assert not log2 and not feito2["candidatos"]


def test_quarto_sem_mensagem_nossa_recebe_firstcontact_antes_da_resposta():
    feito, log = rodar([linha()], MSG_PRIMEIRA)
    assert enviados(log) == [FC, "Temos sim!"]
    feito2, log2 = rodar([linha(previa="E o pet?")], MSG_PRIMEIRA)      # nova mensagem: firstcontact NAO se repete
    assert FC not in enviados(log2)


def test_firstcontact_so_em_quartos():
    for anuncio in ("Casa Casa · 3 quartos", "Studio Studio · 500m", "Apartamento completo - Perto da praia e de tudo"):
        feito, log = rodar([linha(anuncio=anuncio)], MSG_PRIMEIRA)
        assert FC not in enviados(log), anuncio


def test_nao_responde_se_a_ultima_e_nossa_ou_conversa_antiga_ou_encerramento():
    feito, log = rodar([linha(ultima="voce")], MSG_JA_ATENDIDA)
    assert not log and not feito["candidatos"]
    feito, log = rodar([linha(quando="seg")], MSG_JA_ATENDIDA)
    assert not log
    feito, log = rodar([linha(id_="11", previa="Ok, obrigado!")], MSG_JA_ATENDIDA)
    assert not log and not feito["candidatos"]


def test_resposta_com_link_ou_valor_e_barrada_e_avisa_o_dono():
    feito, log = rodar([linha()], MSG_JA_ATENDIDA, ("E", "Diária R$ 300, veja https://x.com"))
    assert enviados(log) == [] and "segurei" in feito["avisos"][0]


def test_aviso_e_pergunta_vao_para_o_dono_sem_enviar_ao_hospede():
    feito, log = rodar([linha()], MSG_JA_ATENDIDA, ("P", "Posso dar desconto?"))
    assert enviados(log) == [] and "desconto" in feito["avisos"][0]


def test_falha_no_envio_avisa_e_tenta_de_novo():
    feito, log = rodar([linha()], MSG_JA_ATENDIDA, ok=False)
    assert not log and any("não consegui" in a for a in feito["avisos"])
    feito2, log2 = rodar([linha()], MSG_JA_ATENDIDA)
    assert enviados(log2)


def test_limite_por_conversa_por_hora():
    est = {"envios": [["10", time.time()], ["10", time.time()]]}
    assert not av.limite_ok(est, "10", time.time(), CFG)
    assert av.limite_ok(est, "99", time.time(), CFG)


# ---------- reservas ----------

MSGS_CONSULTA = MSG_JA_ATENDIDA + [{"de": "sistema", "texto": CARTAO_CONSULTA}]


def test_consulta_dentro_do_padrao_NAO_e_preaprovada_sem_ok_humano():
    feito, log = rodar([linha()], MSGS_CONSULTA, ("E", "Temos sim!"))
    assert not any(x[0] == "reserva" for x in log) and enviados(log) == ["Temos sim!"]
    assert len(feito["perguntas"]) == 1


def test_pedido_de_reserva_pendente_NAO_e_aceito_sem_ok_humano():
    msgs = MSG_JA_ATENDIDA + [{"de": "sistema", "texto": f"Reserva pendente R$440.01 para 3 hóspedes 7 – 11 de out. Você tem até {_AMANHA.day} de {_MES[_AMANHA.month - 1]} para responder"}]
    feito, log = rodar([linha(meta="7 – 11 de out.")], msgs)
    assert not any(x[0] == "reserva" for x in log) and len(feito["perguntas"]) == 1


@pytest.mark.parametrize("l,cartao,motivo", [
    (dict(anuncio="Casa Casa · 3 quartos"), CARTAO_CONSULTA, "quarto/studio"),
    (dict(anuncio="Apartamento completo - Perto da praia e de tudo"), CARTAO_CONSULTA, "Amiga"),
    (dict(), CARTAO_CONSULTA.replace("3 hóspedes", "6 hóspedes"), "6 hóspedes"),
    (dict(meta="1 – 20 de out."), CARTAO_CONSULTA, "19 noites"),
    (dict(meta="Check-in hoje"), CARTAO_CONSULTA.replace("8 – 9 de out. de 2026", ""), "?"),
])
def test_fora_do_padrao_consulta_a_familia_e_nao_age(l, cartao, motivo):
    msgs = MSG_JA_ATENDIDA + [{"de": "sistema", "texto": cartao}]
    feito, log = rodar([linha(**l)], msgs)
    assert not any(x[0] == "reserva" for x in log)
    assert len(feito["perguntas"]) == 1 and motivo in feito["perguntas"][0][2]


def test_hospede_que_fala_de_festa_vai_para_a_familia():
    msgs = [{"de": "voce", "texto": "oi"}, {"de": "hospede", "texto": "Vamos fazer uma festa de aniversário?"}, {"de": "sistema", "texto": CARTAO_CONSULTA}]
    feito, log = rodar([linha()], msgs)
    assert feito["perguntas"] and not any(x[0] == "reserva" for x in log)


def test_decisao_da_familia_executa_a_acao_e_nao_pergunta_de_novo():
    msgs = [{"de": "voce", "texto": "oi"}, {"de": "hospede", "texto": "festa?"}, {"de": "sistema", "texto": CARTAO_CONSULTA}]
    feito, log = rodar([linha(previa="festa?")], msgs)
    assert feito["perguntas"]
    resp = lambda contato, ts: [(ts + 1, "sim Ana")] if contato == "mainha" else []
    # segunda rodada, outra mensagem no preview para reler a conversa
    feito2, log2 = rodar([linha(previa="festa?", ultima="voce")], msgs, mensagens_de=resp)
    assert ("reserva", "10", "preaprovar") in log2 and not feito2["perguntas"]
    assert any("a pedido de Mãe" in a for a in feito2["avisos"])


def test_ler_decisao():
    m = lambda *x: [x]
    assert av.ler_decisao("Ana Souza", False, [("Dono", 1, "sim")]) == ("sim", "Dono")
    assert av.ler_decisao("Ana Souza", False, [("Dono", 1, "sim"), ("Parceira", 2, "não")]) == ("nao", "Parceira")
    assert av.ler_decisao("Ana Souza", True, [("Dono", 1, "sim")]) == (None, None)       # varias abertas: precisa do nome
    assert av.ler_decisao("Ana Souza", True, [("Dono", 1, "sim ana")]) == ("sim", "Dono")
    assert av.ler_decisao("Ana", False, [("Dono", 1, "bom dia, tudo bem?")]) == (None, None)
    assert av.ler_decisao("Ana", False, [("Dono", 1, "sim " + "x" * 100)]) == (None, None)


def test_recusa_da_familia_vira_aviso_e_nada_e_feito():
    msgs = [{"de": "voce", "texto": "oi"}, {"de": "hospede", "texto": "festa?"}, {"de": "sistema", "texto": CARTAO_CONSULTA}]
    rodar([linha(previa="festa?")], msgs)
    feito, log = rodar([linha(previa="festa?", ultima="voce")], msgs, mensagens_de=lambda c, ts: [(ts + 1, "não")] if c == "Dono(dono)" else [])
    assert not any(x[0] == "reserva" for x in log) and any("RECUSAR" in a for a in feito["avisos"])


def test_reembolso_e_multa_sao_barrados():
    assert not av.validar_airbnb("Já solicitei o reembolso pelo Airbnb.")[0]
    assert not av.validar_airbnb("Vamos cancelar sem multa.")[0]


def test_prazo_vencido_nao_gera_acao():
    antigo = CARTAO_CONSULTA.replace(PRAZO_TESTE, "1 de jan. 10:00")
    feito, log = rodar([linha()], MSG_JA_ATENDIDA + [{"de": "sistema", "texto": antigo}])
    assert not any(x[0] == "reserva" for x in log) and not feito["perguntas"]
    assert airbnb.prazo_vencido(antigo, datetime(2026, 10, 7)) and not airbnb.prazo_vencido(CARTAO_CONSULTA, datetime(2026, 10, 7, 12))


# ---------- ferramentas manuais ----------

def test_ferramentas_manuais():
    log = []
    sessao = lambda: AbFalso([linha(hospede="Ana Souza")], MSG_PRIMEIRA, log)
    assert "Ana Souza" in av.pendentes_texto(sessao)
    assert "Tem vaga" in av.conversa_texto("ana", sessao)
    assert "não achei" in av.conversa_texto("zé", sessao).lower()
    assert av.responder_manual("ana", "Oi Ana, tudo certo!", sessao).startswith("✅") and log[0][2] == "Oi Ana, tudo certo!"
    assert "Não enviei" in av.responder_manual("ana", "veja https://x.com", sessao) and len(log) == 1
