# -*- coding: utf-8 -*-
"""Funil dos avisos automaticos ao Dono (16/11/2026): urgente na hora, resto no resumo, repetido some, madrugada segura, teto."""
from datetime import datetime

from braniac import funil, vigia

DIA = datetime(2026, 11, 16, 10, 0)


def test_comum_vai_para_fila_e_repetido_substitui():
    assert funil.passar("🌡 o notebook está esquentando: 98 °C", agora=DIA) == "fila"
    assert funil.passar("🌡 o notebook está esquentando: 99 °C", agora=DIA) == "fila"
    fila = funil._ler()["fila"]
    assert len(fila) == 1 and "99" in fila[0]["texto"]


def test_urgente_sai_na_hora_e_nao_repete():
    assert funil.passar("Hóspede Elias com problema na chave", agora=DIA) == "agora"
    assert funil.passar("Hóspede Elias com problema na chave", agora=DIA) == "repetido"


def test_madrugada_e_teto_seguram_urgente_mas_nao_critico():
    noite = datetime(2026, 11, 16, 2, 0)
    assert funil.passar("Reserva nova no Airbnb", agora=noite) == "fila"
    assert funil.passar("Crise: ligar CVV 188", agora=noite) == "agora"
    funil.CFG.write_text('{"teto_dia": 0}', encoding="utf-8")
    assert funil.passar("Lead quer fechar a landing page", agora=DIA) == "fila"


def test_resumo_so_na_hora_certa_uma_vez_e_limpa_fila():
    funil.passar("Cofre: saldo diminuiu R$ 34,98", agora=DIA)
    funil.passar("Candidaturas da manhã: 0 enviadas", agora=DIA)
    env, aud = [], []
    e = lambda n, t: env.append((n, t)) or "✅ ok"
    a = lambda n, t: aud.append(t) or "✅ ok"
    assert funil.tick(datetime(2026, 11, 16, 10, 5), e, a, nome="Eu") == 0     # 10h nao e hora de resumo
    assert funil.tick(datetime(2026, 11, 16, 13, 1), e, a, nome="Eu") == 2
    assert funil.tick(datetime(2026, 11, 16, 13, 11), e, a, nome="Eu") == 0    # um resumo por hora
    assert len(env) == 1 and "saldo" in env[0][1] and "Candidaturas" in env[0][1] and "2 avisos" in aud[0]
    assert funil._ler()["fila"] == []


def test_envolver_so_filtra_o_dono():
    env = []
    f = funil.envolver(lambda n, t: env.append(n) or "✅ ok", dono="Eu")
    assert f("Eu", "Fornalha: pauta do dia pronta").startswith("✅") and env == []
    f("Parceira", "Fornalha: pauta do dia pronta")
    assert env == ["Parceira"]


def test_outbox_resumo_nao_sai_na_hora(tmp_path, monkeypatch):
    out = tmp_path / "outbox_dono.txt"
    out.write_text("[resumo] Vídeo 1003 parado\n---\nRecado normal\n", encoding="utf-8")
    monkeypatch.setattr(vigia, "OUTBOX", out)
    env = []
    assert vigia.enviar_outbox(lambda d, m: env.append(m) or "✅ ok") == 2
    assert len(env) == 1 and "Recado normal" in env[0]
    assert "1003" in funil._ler()["fila"][0]["texto"]


def test_outbox_nao_perde_bloco_gravado_durante_a_entrega(tmp_path, monkeypatch):
    out = tmp_path / "outbox_dono.txt"
    out.write_text("Recado A\n", encoding="utf-8")
    monkeypatch.setattr(vigia, "OUTBOX", out)
    def enviar(d, m):
        with out.open("a", encoding="utf-8") as f:     # outro processo grava no meio da entrega
            f.write("\n---\nRecado B")
        return "✅ ok"
    assert vigia.enviar_outbox(enviar) == 1
    assert out.read_text(encoding="utf-8").strip() == "Recado B"
