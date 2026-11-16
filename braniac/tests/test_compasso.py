# -*- coding: utf-8 -*-
from datetime import datetime
import pytest
from braniac import compasso as A


@pytest.fixture(autouse=True)
def dados(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "PASTA", tmp_path / "compasso")
    monkeypatch.setattr(A, "ARQ", tmp_path / "compasso" / "rotinas.json")
    monkeypatch.setattr(A, "PEDIDOS", tmp_path / "compasso" / "pedidos.jsonl")
    monkeypatch.setattr(A, "_contar", lambda t: None)      # nao escreve na sala nem no relatorio reais


def braco(ativa=True):
    return A.criar("braco-tia-mae", "Perguntar do braço da Mãe", "perguntar_contato", "10:00", ["Oh minha tia, como tá o braço hoje?"],
                   para="Mãe", ativa=ativa)


def test_rotina_nasce_desativada_e_nao_roda_ate_o_dono_ativar():
    A.criar("x", "teste", "lembrar_dono", "10:00", ["beber água"])
    envios = []
    assert A.tick(datetime(2026, 10, 11, 10, 5), lambda n, t: envios.append(t) or "✅") == [] and not envios
    A.ativar("x")
    A.tick(datetime(2026, 10, 11, 10, 5), lambda n, t: envios.append((n, t)) or "✅ ok")
    assert envios and "beber água" in envios[0][1]


def test_roda_uma_vez_por_dia_no_horario_e_manda_para_o_contato_certo(monkeypatch):
    from braniac import contexto
    monkeypatch.setattr(contexto, "contato", lambda c: {"mae": "mainha"}.get(c))
    braco()
    envios = []
    env = lambda n, t: envios.append((n, t)) or "✅ ok"
    A.tick(datetime(2026, 10, 11, 9, 59), env)
    assert not envios                                                  # antes da hora
    A.tick(datetime(2026, 10, 11, 10, 1), env)
    A.tick(datetime(2026, 10, 11, 10, 11), env)
    assert envios == [("mainha", "Oh minha tia, como tá o braço hoje?")]  # uma vez so
    A.tick(datetime(2026, 10, 12, 10, 1), env)
    assert len(envios) == 2                                            # no dia seguinte de novo


def test_falha_de_envio_tenta_de_novo_no_maximo_3_vezes():
    braco()
    n = []
    for m in range(5):
        A.tick(datetime(2026, 10, 11, 10, m * 10), lambda a, b: n.append(1) or "❌ WhatsApp fechado")
    assert len(n) == 3


def test_protocolo_recusa_acao_contato_horario_e_texto_proibidos():
    with pytest.raises(A.RotinaErro):
        A.criar("a", "t", "delegar_ao_claude", "10:00", ["x"])           # acao fora da lista branca
    with pytest.raises(A.RotinaErro):
        A.criar("b", "t", "perguntar_contato", "10:00", ["oi"], para="Loja")   # nao e familia
    with pytest.raises(A.RotinaErro):
        A.criar("c", "t", "lembrar_dono", "03:00", ["oi"])             # madrugada
    with pytest.raises(A.RotinaErro):
        A.criar("d", "t", "perguntar_contato", "10:00", ["me manda a senha do banco"], para="Irmao")


def test_rotina_adulterada_no_arquivo_e_recusada_na_hora_de_executar():
    braco()
    d = A._ler()
    d["rotinas"][0]["para"] = "Cliente Qualquer"
    A._gravar(d)
    envios = []
    p = A.tick(datetime(2026, 10, 11, 10, 1), lambda n, t: envios.append(t) or "✅")
    assert not envios and p[0]["status"] == "recusado"


def test_teto_diario_segura_execucoes():
    for i in range(A.TETO_DIARIO + 2):
        A.criar(f"r{i}", "t", "lembrar_dono", "10:00", ["oi"], ativa=True)
    envios = []
    A.tick(datetime(2026, 10, 11, 10, 1), lambda n, t: envios.append(t) or "✅ ok")
    assert len(envios) == A.TETO_DIARIO


def test_verificar_youtube_so_le_o_status_e_manda_ao_dono(monkeypatch):
    from braniac.cortes import comandos
    monkeypatch.setattr(comandos, "status", lambda: "Vigia dos cortes: LIGADO")
    A.criar("yt", "Canal", "verificar_youtube", "19:00", ativa=True)
    envios = []
    A.tick(datetime(2026, 10, 11, 19, 5), lambda n, t: envios.append((n, t)) or "✅ ok")
    assert "Vigia dos cortes" in envios[0][1]
