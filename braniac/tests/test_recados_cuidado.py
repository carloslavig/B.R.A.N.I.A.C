# -*- coding: utf-8 -*-
"""Recados ao Dono (fila literal + promessa), cuidado diario (Parceira e Mae) e hora atual no contexto."""
from datetime import datetime

import pytest

from braniac import contexto, recados, rotina


@pytest.fixture(autouse=True)
def isolado(tmp_path, monkeypatch):
    monkeypatch.setattr(recados, "ARQ", tmp_path / "recados.json")
    monkeypatch.setattr(rotina, "ESTADO", tmp_path / "rotina.json")


@pytest.mark.parametrize("frase", ["Vou passar pro Dono, pode deixar.", "Anotei seu recado!", "Ele te retorna assim que puder.", "A gente avisa ele assim que possível.",
                                   "Blz vo passa pro dono", "Já informo ele, tá?", "Vou pedir pro Dono te chamar."])
def test_promessa_de_repassar_e_detectada(frase):
    assert recados.promete_repassar(frase)


@pytest.mark.parametrize("frase", ["Vou te ajudar com isso", "Oi! Aqui é o Jarvis, assistente do Dono", "Ele disse que o preço é R$ 150", "Recebi sua mensagem, já te respondo",
                                   "Já te passo o valor do combo", "A gente atende de quinta a terça", "Posso te enviar o link do site"])
def test_conversa_normal_nao_vira_recado(frase):
    assert not recados.promete_repassar(frase)


def test_recado_e_literal_sem_duplicar_e_entregue_com_nova_tentativa():
    assert recados.enfileirar("Maria", "Oi, preciso falar com o Dono sobre o orçamento do casamento, é urgente 🙏", resposta="Vou passar pra ele!")
    assert not recados.enfileirar("Maria", "Oi, preciso falar com o Dono sobre o orçamento do casamento, é urgente 🙏")      # mesma mensagem: nao repete
    assert "orçamento do casamento, é urgente" in recados.pendentes()[0]["texto"]
    assert recados.entregar(lambda d, t: "falhou", "Eu") == 0 and len(recados.pendentes()) == 1      # falhou: continua na fila
    enviados = []
    assert recados.entregar(lambda d, t: enviados.append((d, t)) or "✅ ok", "Eu") == 1 and not recados.pendentes()
    assert enviados[0][0] == "Eu" and enviados[0][1].startswith("📩 Recado de Maria:")


def test_recado_longo_e_cortado_sem_perder_o_inicio():
    recados.enfileirar("Zé", "pedido " * 300)
    assert recados.pendentes()[0]["texto"].count("pedido") < 300 and "Recado de Zé" in recados.pendentes()[0]["texto"]


def test_cuidado_diario_uma_vez_por_dia_por_pessoa_com_texto_de_fallback():
    audios, textos = [], []
    agora = datetime(2026, 10, 13, 9, 0)
    feitos = rotina.cuidado_diario(agora, lambda n, t: textos.append((n, t)) or "✅ texto", lambda n, t: audios.append((n, t)) or "✅ audio")
    assert set(feitos) == {"parceira", "mae", "pai"} and len(audios) == 3 and not textos
    assert any("Deusa" in t for _, t in audios) and any("minha tia" in t and "braço" in t for _, t in audios)
    assert rotina.cuidado_diario(agora, lambda n, t: "✅", lambda n, t: "✅") == []                       # ja fez hoje
    # audio falha -> texto
    amanha = datetime(2026, 10, 14, 9, 0)
    textos.clear()
    rotina.cuidado_diario(amanha, lambda n, t: textos.append(n) or "✅", lambda n, t: "falhou")
    assert len(textos) == 2                                                                          # Parceira e mae; o pai NUNCA recebe texto
    # antes do horario e depois das 21h nao manda
    assert rotina.cuidado_diario(datetime(2026, 10, 15, 6, 0), lambda n, t: "✅", lambda n, t: "✅") == []
    assert rotina.cuidado_diario(datetime(2026, 10, 15, 22, 0), lambda n, t: "✅", lambda n, t: "✅") == []


def test_pai_so_audio_e_tenta_de_novo_se_falhar():
    textos = []
    agora = datetime(2026, 11, 17, 9, 30)
    assert "pai" not in rotina.cuidado_diario(agora, lambda n, t: textos.append(n) or "✅", lambda n, t: "falhou")
    assert not any("Mun" in n for n in textos)
    pai = []
    assert "pai" in rotina.cuidado_diario(agora, lambda n, t: "✅", lambda n, t: pai.append(t) or "✅")
    assert "Pai" in pai[0]


def test_braco_so_ate_a_data_limite():
    audios = []
    rotina.cuidado_diario(datetime(2026, 12, 1, 9, 0), lambda n, t: "✅", lambda n, t: audios.append(t) or "✅")
    mae = [t for t in audios if "minha tia" in t][0]
    assert "braço" not in mae and "Como" in mae


def test_hora_atual_entra_no_contexto():
    assert "terça-feira, 13/10/2026, 09:05 (manhã)" in contexto.agora_texto(datetime(2026, 10, 13, 9, 5))
    assert "[agora]" in contexto.dossie_para("oi")
