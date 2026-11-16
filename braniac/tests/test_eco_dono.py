# -*- coding: utf-8 -*-
"""16/11/2026: o Jarvis respondeu ao proprio resumo de avisos no chat do Dono (o chat lido voltou a partir do 1o aviso)."""
from braniac import whatsapp


def test_eco_do_resumo_e_fala_curta_do_dono(monkeypatch, tmp_path):
    monkeypatch.setattr(whatsapp, "_arq_env", lambda: tmp_path / "enviados_recentes.json")
    whatsapp._lembrar_envio("📋 Resumo do Jarvis\n\n• ⚠️ A porta 5432 (PostgreSQL, processo postgres) está aberta para a rede, não só para este PC.\n\n"
                            "• Dono, o notebook está esquentando. Pode fazer uma pausa.")
    assert whatsapp.foi_nosso("A porta 5432 (PostgreSQL, processo postgres) está aberta para a rede, não só para este PC.")
    whatsapp._lembrar_envio("Pronto, senhor.")
    assert whatsapp.foi_nosso("Pronto, senhor.")                       # envio curto que volta inteiro continua sendo eco
    for fala in ("Pode fazer", "ok", "Aprove", "pausa"):              # fala curta do Dono nunca vira eco
        assert not whatsapp.foi_nosso(fala)
    assert not whatsapp.foi_nosso("Faz mais 10 vídeos e me fala as cidades que vai fazer")


def test_confirmacao_curta_liga_na_ultima_proposta():
    from braniac import dono
    hist = [("E", "Faz mais 10 vídeos"), ("C", "Já têm roteiro Araci e Aramari; faltam 4 cidades para fechar os 10. Quer que eu escolha?")]
    for fala in ("Pode fazer", "aprove", "Sim.", "pode sim, Jarvis", "Bora!"):
        assert "Araci e Aramari" in dono.nota_confirmacao(fala, hist), fala
    for fala in ("Pode fazer um jogo pra mim?", "A esteira está parada?", "sim, mas troca Araci por Cidade"):
        assert dono.nota_confirmacao(fala, hist) == "", fala
    assert dono.nota_confirmacao("pode fazer", []) == ""


def test_promessa_vazia_refaz_com_a_ferramenta():
    from braniac import clareza
    assert clareza.so_promessa("Vou dar uma olhada na esteira agora e já te digo se está parada.")
    assert clareza.so_promessa("Ainda não tenho a situação confirmada. Vou checar e já te falo.")
    assert not clareza.so_promessa("A esteira está parada: 50 de 76 prontos, todos no site.")
    assert not clareza.so_promessa("Tô vendo isso, senhor, já te falo.")       # aviso de falha da IA (dono.ESTOU_VENDO) fica como está
    dicas = []
    r = clareza.conferir(("Vou verificar e já te aviso.", True), "A esteira está parada?", lambda d: (dicas.append(d), ("Parada: 50/76.", True))[1])
    assert r == ("Parada: 50/76.", True) and "PROMETEU" in dicas[0]
