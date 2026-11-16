# -*- coding: utf-8 -*-
import pytest
from braniac import guarda as G


@pytest.fixture(autouse=True)
def dados(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "ARQ", tmp_path / "guarda.json")
    monkeypatch.setattr(G, "DATA", tmp_path)


def foto(**kw):
    base = {"ip": "1.1.1.1", "portas": {"5040": "svchost", "5432": "postgres"}, "firewall_desligado": [], "rdp_ligado": False,
            "defender": {"tempo_real": True, "assinatura_dias": 1}, "falhas_login_1h": 0}
    base.update(kw)
    return base


T0 = 1_800_000_000.0


def roda(est, t=0.0):
    env = []
    G.verificar(env.append, coletor=lambda: est, agora=T0 + t)
    return env


def test_primeira_leitura_memoriza_mas_avisa_porta_de_risco():
    env = roda(foto())
    assert len(env) == 1 and "5432" in env[0] and "PostgreSQL" in env[0] and "Não mexi em nada" in env[0]   # risco avisa; nada de 'nova porta' no baseline


def test_alerta_nao_repete_dentro_de_12h_e_repete_depois():
    assert len(roda(foto(), 1000)) == 1
    assert roda(foto(), 2000) == []
    assert len(roda(foto(), 1000 + 13 * 3600)) == 1


def test_ip_mudou_avisa_so_na_mudanca():
    roda(foto(portas={}), 1000)
    env = roda(foto(ip="2.2.2.2", portas={}), 2000)
    assert any("IP público mudou: 1.1.1.1 → 2.2.2.2" in e for e in env)
    assert roda(foto(ip="2.2.2.2", portas={}), 3000) == []


def test_porta_nova_depois_do_baseline_avisa():
    roda(foto(portas={"5040": "svchost"}), 1000)
    env = roda(foto(portas={"5040": "svchost", "8080": "node"}), 2000)
    assert any("Nova porta aberta" in e and "8080" in e for e in env)


def test_firewall_rdp_defender_e_forca_bruta_sao_alertas():
    est = foto(portas={}, firewall_desligado=["Public"], rdp_ligado=True, defender={"tempo_real": False, "assinatura_dias": 20}, falhas_login_1h=25)
    texto = " | ".join(roda(est))
    for trecho in ("Firewall do Windows está DESLIGADO", "RDP", "tempo real do Windows Defender", "20 dias", "25 tentativas de login"):
        assert trecho in texto


def test_pc_saudavel_nao_gera_alerta_e_resumo_diz_ok():
    assert roda(foto(portas={"5040": "svchost"})) == []
    r = G.resumo()
    assert "firewall OK" in r and "antivírus OK" in r and "IP 1.1.1.1" in r


def test_coletor_que_falha_nao_derruba():
    assert roda({"ip": None, "portas": None, "firewall_desligado": None, "rdp_ligado": None, "defender": None, "falhas_login_1h": None}) == []
