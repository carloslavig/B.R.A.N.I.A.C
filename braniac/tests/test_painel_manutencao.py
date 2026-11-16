# -*- coding: utf-8 -*-
"""Botao de panico, painel dos bracos, historico de acoes e manutencao da madrugada (08/10/2026)."""
import json
from datetime import datetime
from braniac import airbnb_vigia, manutencao, painel, power, rotina, store, vigia


def test_panico_desarma_autonomia_e_desliga_atendimentos(monkeypatch):
    monkeypatch.setattr(airbnb_vigia, "desligar", lambda: None)
    monkeypatch.setattr(airbnb_vigia, "resumo", lambda: {"ligado": True})
    power.armar(60)
    power.set_atendimento_auto(True)
    r = painel.panico("telegram")
    assert not power.armada() and not power.atendimento_auto()
    assert "autonomia remota desarmada" in r["feito"] and "atendimento automático do WhatsApp desligado" in r["feito"]
    assert "PANICO (telegram)" in (store.DATA / "painel.log").read_text(encoding="utf-8")


def test_panico_nunca_arma_nada(monkeypatch):
    monkeypatch.setattr(airbnb_vigia, "desligar", lambda: None)
    monkeypatch.setattr(airbnb_vigia, "resumo", lambda: {"ligado": False})
    r = painel.panico()
    assert not power.armada() and not power.atendimento_auto() and "já estava desligado" in r["texto"]


def test_panico_pelo_jarvis_vale_de_qualquer_canal(monkeypatch):
    from braniac import jarvis
    monkeypatch.setattr(airbnb_vigia, "desligar", lambda: None)
    monkeypatch.setattr(airbnb_vigia, "resumo", lambda: {"ligado": False})
    power.armar(60)
    resp, da_ia = jarvis.processar(None, "/panico", "x", origem="telegram")
    assert "Pânico" in resp and not da_ia and not power.armada()


def test_bracos_mostra_estado_de_cada_braco():
    power.armar(30)
    b = {x["nome"]: x for x in painel.bracos({"atendimento_auto": {"ligado": False}, "airbnb_auto": {"ligado": True},
                                               "escuta_voz": {"estado": "dormindo"}, "email": {"logado": False}})}
    assert b["Autonomia remota"]["ok"] and "ARMADA" in b["Autonomia remota"]["detalhe"]
    assert not b["Atendimento WhatsApp"]["ok"] and b["Airbnb"]["ok"] and b["Microfone (voz)"]["ok"]
    assert b["Manutenção da madrugada"]["detalhe"] == "ainda não rodou"
    power.armar(0)


def test_historico_junta_os_logs_do_mais_novo_ao_mais_antigo():
    (store.DATA / "vigia.log").write_text("2026-10-08 10:00:00 | atendendo: ['X']\nlinha torta\n", encoding="utf-8")
    (store.DATA / "dono.log").write_text("2026-10-08 11:00:00 | respondido(texto)\n", encoding="utf-8")
    h = painel.historico()
    assert [x["braco"] for x in h] == ["Dono", "WhatsApp"] and h[0]["texto"] == "respondido(texto)"


SAIDA_PYTEST = "FAILED braniac/tests/test_a.py::test_x - AssertionError\n1 failed, 10 passed in 3.2s\n"


def _rodar_falso(saida_pytest=SAIDA_PYTEST, cod=1, pip="[]"):
    def rodar(cmd, timeout):
        if "pytest" in cmd:
            return cod, saida_pytest
        return 0, pip
    return rodar


def test_manutencao_relata_testes_dependencias_e_modelos_sem_instalar_nada():
    registros, chamados = [], []
    pip = json.dumps([{"name": "edge-tts", "version": "6.0", "latest_version": "7.0"}, {"name": "pacote-qualquer", "version": "1", "latest_version": "2"}])

    def rodar(cmd, timeout):
        chamados.append(cmd)
        return _rodar_falso(pip=pip)(cmd, timeout)
    res = manutencao.rodar_manutencao(rodar, tags=[], registrar=registros.append)
    assert res["passaram"] == 10 and res["falharam"] == 1 and not res["testes_ok"]
    assert res["falhas"] == ["braniac/tests/test_a.py::test_x"]
    assert res["dependencias"] == [("edge-tts", "6.0", "7.0")]          # so os pacotes que o Jarvis usa
    assert "NÃO apliquei" in registros[0]
    assert not any("install" in c for c in chamados)                     # nunca instala nada sozinha
    assert manutencao.ultimo()["dia"] == datetime.now().strftime("%Y-%m-%d")


def test_manutencao_avisa_falha_nova_desde_ontem():
    manutencao.rodar_manutencao(_rodar_falso(), tags=[], registrar=lambda t: None)
    nova = "FAILED braniac/tests/test_a.py::test_x\nFAILED braniac/tests/test_b.py::test_novo - X\n2 failed, 9 passed\n"
    reg = []
    res = manutencao.rodar_manutencao(_rodar_falso(nova), tags=[], registrar=reg.append)
    assert res["novas_falhas"] == ["braniac/tests/test_b.py::test_novo"] and "NOVA" in reg[0] and "test_novo" in reg[0]


def test_manutencao_tudo_ok():
    reg = []
    res = manutencao.rodar_manutencao(_rodar_falso("12 passed in 2s\n", cod=0), tags=[], registrar=reg.append)
    assert res["testes_ok"] and "12 ok / 0 com falha" in reg[0]


def test_tick_so_roda_de_madrugada_e_uma_vez_por_dia():
    disparos = []
    assert not manutencao.tick(datetime(2026, 10, 9, 14, 0), iniciar=lambda: disparos.append(1))
    assert manutencao.tick(datetime(2026, 10, 9, 3, 10), iniciar=lambda: disparos.append(1))
    (store.DATA / "manutencao.json").write_text(json.dumps({"dia": "2026-10-09"}), encoding="utf-8")
    assert not manutencao.tick(datetime(2026, 10, 9, 3, 20), iniciar=lambda: disparos.append(1))
    assert disparos == [1]


def test_resultado_da_manutencao_entra_no_bom_dia(monkeypatch):
    monkeypatch.setattr(rotina, "RELATORIO", store.DATA / "relatorio_noturno.md")
    manutencao.rodar_manutencao(_rodar_falso("5 passed\n", cod=0), tags=[])     # registrar padrao = rotina.registrar
    monkeypatch.setattr(rotina, "resumo_emails", lambda: "")
    assert "Manutenção da madrugada" in rotina.bom_dia()


def test_autonomia_ate_72h_e_indefinida_e_desarma(tmp_path, monkeypatch):
    monkeypatch.setattr(power, "ARQ", tmp_path / "power.json", raising=False)
    power.armar(36 * 60)
    assert power.armada() and 36 * 60 - 2 <= power.armada_restante_min() <= 36 * 60 and not power.armada_indefinida()
    power.armar(10 ** 6)                                   # acima do maximo: limita em 72 h
    assert power.armada_restante_min() <= 72 * 60
    power.armar(power.INDEFINIDA)
    assert power.armada() and power.armada_indefinida() and power.armada_restante_min() > 72 * 60
    power.armar(0)
    assert not power.armada() and not power.armada_indefinida()
