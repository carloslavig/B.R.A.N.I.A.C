# -*- coding: utf-8 -*-
"""Zelo: explica em audio, ao pai do Dono, so a mensagem que chegou agora."""
from braniac import guia_pai


def test_reconhece_o_contato_do_pai_nas_duas_grafias():
    assert guia_pai.eh_pai("Munzés") and guia_pai.eh_pai("Pai") and not guia_pai.eh_pai("mainha")


def test_so_texto_de_agora_audio_e_midia_ficam_de_fora():
    assert guia_pai.mensagens_de_agora(["🎙 oi Jarvis", "[IMAGEM não compreendida]", "Estou em frente ao cimento", "🖼 foto de uma rua"]) == \
        ["Estou em frente ao cimento", "foto de uma rua"]


def test_explica_no_jeito_pedido():
    r = guia_pai.explicar(["Estou em frente ao cimento, na Antônio Dono Magalhães"],
                          lambda t: "que está em frente ao cimento, na Antônio Dono Magalhães.")
    assert r == "Ótimo, Pai. A pessoa que te mandou mensagem falou que está em frente ao cimento, na Antônio Dono Magalhães."


def test_sem_ia_le_a_mensagem_como_veio():
    def cai(t):
        raise RuntimeError("sem IA")
    assert guia_pai.explicar(["Chego às 9h"], cai).endswith("escreveu assim: Chego às 9h")


def test_tratar_envia_audio_e_sem_texto_deixa_para_o_jarvis(monkeypatch):
    monkeypatch.setattr(guia_pai.memoria, "registrar_msg", lambda *a, **k: None)
    enviados = []
    linha = guia_pai.tratar("Munzés", {"msgs": ["Chego às 9h"]}, enviar=lambda n, t: enviados.append((n, t)) or "✅ ok", resumir=lambda t: "que chega às 9h.")
    assert linha.startswith("✓") and enviados == [("Munzés", "Ótimo, Pai. A pessoa que te mandou mensagem falou que chega às 9h.")]
    assert guia_pai.tratar("Munzés", {"msgs": ["🎙 bom dia"]}, enviar=lambda n, t: pytest_fail()) is None


def pytest_fail():
    raise AssertionError("nao deveria enviar")
