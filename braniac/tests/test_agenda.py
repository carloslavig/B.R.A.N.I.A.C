# -*- coding: utf-8 -*-
"""Agenda do Dono (14/10/2026): datas em portugues, repeticoes, conflitos, livres, lembretes e ferramenta do Jarvis."""
from datetime import date, datetime

from braniac import agenda

AGORA = datetime(2026, 10, 14, 10, 0)   # quarta-feira


def test_interpreta_datas_em_portugues():
    q = agenda.interpretar_quando
    assert q("amanhã 14h", AGORA) == (date(2026, 10, 15), (14, 0))
    assert q("15/10 9:30", AGORA) == (date(2026, 10, 15), (9, 30))
    assert q("segunda 10h", AGORA) == (date(2026, 10, 19), (10, 0))
    assert q("hoje às 8 da noite", AGORA) == (date(2026, 10, 14), (20, 0))
    assert q("2026-10-20 07:15", AGORA) == (date(2026, 10, 20), (7, 15))
    assert q("9h", AGORA) == (date(2026, 10, 15), (9, 0))          # ja passou hoje -> amanha
    assert q("quarta 9h", AGORA) == (date(2026, 10, 21), (9, 0))   # mesma semana ja passou -> proxima
    assert q("", AGORA) == (None, None)


def test_adicionar_listar_concluir_remover():
    r = agenda.adicionar("Dentista", "amanhã 14h", 60, agora=AGORA)
    assert r.startswith("📅 Anotado: Dentista") and "amanhã" in r
    agenda.adicionar("Comprar ração", agora=AGORA)                     # tarefa sem data
    txt = agenda.listar("amanhã", agora=AGORA)
    assert "14:00–15:00 Dentista" in txt and "Comprar ração" in txt
    assert agenda.concluir("ração", agora=AGORA).startswith("✅")
    assert "Comprar ração" not in agenda.listar("amanhã", agora=AGORA)
    assert agenda.remover("dentista").startswith("🗑️")
    assert "Dentista" not in agenda.listar("amanhã", agora=AGORA)
    assert "(dia livre)" in agenda.listar("amanhã", agora=AGORA)


def test_rotina_dias_uteis_e_conflito():
    agenda.adicionar("Academia", "hoje 7h", 60, "dias_uteis", agora=AGORA)
    assert agenda.ocorrencias(date(2026, 10, 16))          # sexta
    assert not agenda.ocorrencias(date(2026, 10, 17))      # sabado
    r = agenda.adicionar("Call", "sexta 7:30", 30, agora=AGORA)
    assert "Bate com: Academia" in r


def test_concluir_rotina_vale_so_para_o_dia():
    agenda.adicionar("Remédio", "hoje 21h", 5, "diario", agora=AGORA)
    agenda.concluir("remédio", "hoje", agora=AGORA)
    assert "✅" in agenda.listar("hoje", agora=AGORA) and "▫️" in agenda.listar("amanhã", agora=AGORA)


def test_livres_respeita_compromissos():
    agenda.adicionar("Reunião", "hoje 13h", 120, agora=AGORA)
    l = agenda.livres("hoje", agora=AGORA)
    assert (600, 780) in l and (900, 1320) in l           # 10:00-13:00 e 15:00-22:00


def test_lembrete_sai_uma_vez_antes_do_horario():
    agenda.adicionar("Buscar Filho", "hoje 11h", 30, lembrar=15, agora=AGORA)
    enviados = []
    env = lambda t: enviados.append(t) or "✅ ok"
    assert agenda.lembretes(datetime(2026, 10, 14, 10, 40), env) == []        # cedo demais
    assert agenda.lembretes(datetime(2026, 10, 14, 10, 50), env) == ["Buscar Filho"]
    assert agenda.lembretes(datetime(2026, 10, 14, 10, 55), env) == []        # nao repete
    assert "daqui a 10 min" in enviados[0]


def test_lembrete_que_falhou_tenta_de_novo():
    agenda.adicionar("Ligar pro banco", "hoje 11h", 15, agora=AGORA)
    assert agenda.lembretes(datetime(2026, 10, 14, 10, 50), lambda t: "falhou") == []
    assert agenda.lembretes(datetime(2026, 10, 14, 11, 0), lambda t: "✅") == ["Ligar pro banco"]


def test_resumo_falado_para_o_bom_dia():
    agenda.adicionar("Dentista", "hoje 14h", agora=AGORA)
    agenda.adicionar("Pagar conta de luz", agora=AGORA)
    f = agenda.resumo_falado(AGORA)
    assert "às 14 horas, Dentista" in f and "1 tarefa sem data" in f


def test_ferramenta_do_jarvis():
    from braniac import jarvis
    assert any(f["function"]["name"] == "agenda" for f in jarvis.FERRAMENTAS)
    r = agenda.ferramenta({"acao": "adicionar", "titulo": "Estudar inglês", "quando": "amanhã 19h", "repetir": "diario"}, AGORA)
    assert "todo dia" in r
    assert "Estudar inglês" in agenda.ferramenta({"acao": "organizar", "dia": "amanhã"}, AGORA)
    ex = jarvis._Executor(None, "c", "x", None, origem="whatsapp")
    assert "Estudar inglês" in ex("agenda", {"acao": "listar", "dia": "2026-10-15"})


def test_rotina_tick_manda_lembrete_ao_dono(monkeypatch):
    from braniac import rotina
    agenda.adicionar("Consulta", "hoje 11h", agora=AGORA)
    monkeypatch.setattr(rotina, "entregar_bom_dia", lambda *a: True)
    monkeypatch.setattr(rotina, "cuidado_diario", lambda *a, **k: [])
    enviados = []
    rotina.tick(datetime(2026, 10, 14, 10, 50), enviar=lambda n, t: enviados.append((n, t)) or "✅", audio=lambda n, t: "✅")
    assert any("⏰ Lembrete: Consulta" in t for _, t in enviados)


def test_ver_agenda_sem_gastar_ia():
    from braniac import jarvis
    agenda.adicionar("Dentista", "amanhã 14h")

    class SemIA:
        def responder_agente(self, *a, **k):
            raise AssertionError("nao devia chamar IA")
    r, da_ia = jarvis.processar(SemIA(), "o que eu tenho na agenda amanhã?", "c", origem="whatsapp")
    assert "Dentista" in r and not da_ia
    assert "Dentista" in jarvis.processar(SemIA(), "mostra minha agenda da semana", "c", origem="whatsapp")[0]


def test_ia_cai_depois_de_usar_ferramenta_mostra_o_que_foi_feito():
    from braniac import jarvis
    from braniac.router import TodosFalharam

    class CaiNoMeio:
        def responder_agente(self, conv, texto, tools, executor, **k):
            executor("agenda", {"acao": "adicionar", "titulo": "Ligar pro banco", "quando": "amanhã 9h"})
            raise TodosFalharam("todas as IAs com ferramenta falharam")

        def responder(self, *a, **k):
            raise AssertionError("nao devia cair na reserva sem ferramentas")
    r, _ = jarvis.processar(CaiNoMeio(), "me lembra amanhã às 9h de ligar pro banco", "c", origem="whatsapp")
    assert r.startswith("📅 Anotado: Ligar pro banco")


def test_data_em_outros_campos_e_mes_por_extenso():
    r = agenda.ferramenta({"acao": "adicionar", "titulo": "Contador", "data": "2026-10-16", "hora": "15:00"}, AGORA)
    assert "16/10" in r and "15:00" in r
    assert agenda.interpretar_quando("16 de outubro 15h", AGORA) == (date(2026, 10, 16), (15, 0))
    assert agenda.interpretar_quando("2 de janeiro", AGORA) == (date(2027, 1, 2), None)


def test_alma_envia_lembrete_da_agenda_e_audio_cedo():
    from braniac import compasso as A
    agenda.adicionar("Consulta", "hoje 11h", agora=AGORA)
    env = []
    A.tick(datetime(2026, 10, 14, 10, 50), enviar=lambda n, t: env.append((n, t)) or "✅")
    assert any("⏰ Lembrete: Consulta" in t for _, t in env)
    assert "audio_contato" in A.ACOES and A.HORA_MIN_POR_ACAO["audio_contato"] == 6
    ok = {"id": "x", "titulo": "t", "acao": "audio_contato", "para": "irmao", "horario": "06:00", "dias": [], "textos": ["Bom dia, Irmao"]}
    assert A.validar(ok)
    import pytest
    with pytest.raises(A.RotinaErro):
        A.validar({**ok, "acao": "perguntar_contato"})      # texto escrito continua so a partir das 8h
    with pytest.raises(A.RotinaErro):
        A.validar({**ok, "horario": "05:30"})
