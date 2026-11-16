# -*- coding: utf-8 -*-
from pathlib import Path
import pytest
from braniac import atender, canal, contexto, memoria, revisao, whatsapp


def item(nome="Amigo Souza 🌝", msgs=("Eu gostaria de fazer o orçamento da cerimônia e da lua de mel",)):
    return {"nome": nome, "nl": 1, "msgs": list(msgs), "ctx": [], "autores": {nome}, "midia": False}


# ---------- o auditor: os erros que o Dono viu ----------

@pytest.mark.parametrize("texto", ["Parece trote: pediu 31 de fevereiro", "isso é zoeira", "pode ser golpe", "esse cara é mentiroso", "é um troll"])
def test_rotular_a_pessoa_e_barrado_em_resposta_e_em_nota(texto):
    for cod in ("E", "A", "P"):
        assert any("rotula" in p for p in revisao.auditar(item(), cod, texto, saidas=[])), (cod, texto)


def test_endereco_com_a_palavra_golpe_nao_e_julgamento():
    assert not any("rotula" in p for p in revisao.auditar(item(), "E", "veja https://golpe.com/x", saidas=[]))


def test_repetir_a_mesma_observacao_e_barrado():
    antes = ["Amigo, 31 de fevereiro não existe, rs. Me passa a data certinha e o horário do casamento que eu anoto tudo"]
    rep = "Opa, Amigo! Só um detalhe: 31 de fevereiro não existe, rs. Me confirma a data certinha?"
    assert any("repete" in p for p in revisao.auditar(item(), "E", rep, saidas=antes))
    quase = "Amigo, 31 de fevereiro não existe, rs. Me passa a data certinha e o horário do casamento que eu anoto"
    assert any("repete" in p for p in revisao.auditar(item(), "E", quase, saidas=antes))
    novo = "Amigo, os pacotes de casamento vão de mil a três mil reais. Me diz a cidade e os convidados."
    assert not revisao.auditar(item(), "E", novo, saidas=antes)


def test_ignorar_ou_so_avisar_um_pedido_de_cliente_e_barrado():
    for cod in ("I", "A"):
        assert any("PEDIDO" in p for p in revisao.auditar(item(), cod, "avisar o Dono", saidas=[]))
    sem_pedido = item("Rafa", ("bom dia pessoal",))
    assert revisao.auditar(sem_pedido, "I", "", saidas=[]) == []
    assert revisao.auditar(item("Asaas", ("quanto custa?",)), "I", "", saidas=[]) == []     # conta automatica: sem revisao


def test_resposta_limpa_nao_gera_problema():
    assert revisao.auditar(item(), "E", "Amigo, claro! Me diz a data, a cidade e quantos convidados.", saidas=[]) == []


def test_saidas_recentes_vem_do_banco_so_do_que_nos_dissemos():
    memoria.registrar_msg("Ana", "E", "oi, tem vaga?")
    memoria.registrar_msg("Ana", "C", "Tem sim! Qual a data?")
    assert memoria.saidas_recentes("Ana") == ["Tem sim! Qual a data?"]
    assert revisao.auditar(item("Ana", ("tem vaga?",)), "E", "Tem sim! Qual a data?") != []     # usa o banco por padrao


# ---------- a revisao: o Claude e consultado ANTES de qualquer envio ----------

def test_decisao_limpa_passa_direto_sem_incomodar_ninguem(monkeypatch):
    monkeypatch.setattr(revisao, "revisar", lambda *a, **k: pytest.fail("nao devia revisar"))
    assert revisao.decidir_com_revisao(item(), "-", ("E", "Claro, Amigo! Me passa a data e a cidade."), 5)[:2] == ("E", "Claro, Amigo! Me passa a data e a cidade.")


def test_claude_ao_vivo_e_perguntado_primeiro_e_a_revisao_dele_vale(monkeypatch):
    linhas = []
    monkeypatch.setattr(canal, "presente", lambda: True)
    monkeypatch.setattr(canal, "_postar_e_esperar",
                        lambda id_, linha, espera: linhas.append(linha) or (id_, "E", "Amigo, os pacotes vão de mil a três mil reais."))
    cod, texto, nota = revisao.decidir_com_revisao(item(), "-", ("A", "Amigo Souza parece trote"), 5)
    assert (cod, texto, nota) == ("E", "Amigo, os pacotes vão de mil a três mil reais.", "revisada")
    assert linhas[0].startswith("V|") and "PROPOSTA=A:Amigo Souza parece trote" in linhas[0] and "PROBLEMAS=" in linhas[0]
    assert "\n" not in linhas[0]


def test_sem_claude_ao_vivo_um_revisor_de_fundo_refaz(monkeypatch):
    monkeypatch.setattr(canal, "presente", lambda: False)
    monkeypatch.setattr(contexto, "decidir_claude", lambda linha, timeout=150, memoria_txt="": ("x", "E", "Amigo, claro! Me passa a data."))
    assert revisao.decidir_com_revisao(item(), "-", ("A", "parece trote"), 5)[:3] == ("E", "Amigo, claro! Me passa a data.", "revisada")


def test_sem_nenhum_revisor_o_jarvis_segura_em_vez_de_enviar(monkeypatch):
    monkeypatch.setattr(canal, "presente", lambda: False)
    monkeypatch.setattr(contexto, "decidir_claude", lambda *a, **k: None)
    cod, texto, nota = revisao.decidir_com_revisao(item(), "-", ("E", "Esse pedido é uma zoeira, rs"), 5)
    # autonomia total: nao pergunta ao Dono; manda uma resposta neutra e segura (nunca a proposta barrada)
    assert (cod, texto, nota) == ("E", revisao.NEUTRA, "neutra") and "zoeira" not in texto
    memoria.registrar_msg(item()["nome"], "C", revisao.NEUTRA)
    assert revisao.decidir_com_revisao(item(), "-", ("E", "Esse pedido é uma zoeira, rs"), 5)[:3] == ("I", "", "autoignorada")   # nao repete a neutra


def test_se_a_revisao_ainda_tem_problema_tambem_segura(monkeypatch):
    monkeypatch.setattr(canal, "presente", lambda: True)
    monkeypatch.setattr(canal, "_postar_e_esperar", lambda id_, linha, espera: (id_, "E", "Isso me parece trote mesmo."))
    assert revisao.decidir_com_revisao(item(), "-", ("E", "É zoeira"), 5)[:3] == ("E", revisao.NEUTRA, "neutra")


# ---------- no atendimento: nada barrado chega a sair ----------

@pytest.fixture
def envios(monkeypatch):
    saidas = []
    monkeypatch.setattr(whatsapp, "enviar", lambda n, x: saidas.append(x) or "✅ ok")
    monkeypatch.setattr(atender.time, "sleep", lambda s: None)
    return saidas


def test_o_caso_do_souza_nota_de_trote_vira_resposta_educada(monkeypatch, envios):
    monkeypatch.setattr(atender, "coletar", lambda *a, **k: [item()])
    monkeypatch.setattr(atender, "decidir", lambda it, fl, esp=0: ("A", "Amigo Souza parece trote: pediu 31 de fevereiro"))
    monkeypatch.setattr(canal, "presente", lambda: True)
    monkeypatch.setattr(canal, "_postar_e_esperar", lambda id_, linha, esp: (id_, "E", "Amigo, os pacotes vão de mil a três mil reais. Me diz a cidade e os convidados."))
    atender.atender(espaco_s=(0, 0), relatar=False)
    assert envios and "pacotes" in envios[0] and "trote" not in " ".join(envios).lower()
    assert any(d == "E" for d, _ in [("E", 1)]) and memoria.resumo()["decisoes"] == 1        # a decisao gravada e a REVISADA


def test_resposta_que_repete_e_segurada_sem_revisor_e_nada_e_enviado(monkeypatch, envios):
    memoria.registrar_msg("Amigo Souza 🌝", "C", "Amigo, 31 de fevereiro não existe, rs. Me passa a data certinha e o horário do casamento")
    monkeypatch.setattr(atender, "coletar", lambda *a, **k: [item()])
    monkeypatch.setattr(atender, "decidir", lambda it, fl, esp=0: ("E", "Opa, Amigo! Só um detalhe: 31 de fevereiro não existe, rs. Me passa a data certinha e o horário do casamento"))
    monkeypatch.setattr(canal, "presente", lambda: False)
    rel = atender.atender(espaco_s=(0, 0), relatar=False)
    assert envios == [] and "Revisão pendente" not in rel and "Eu" not in rel   # barrado e calado sozinho: ninguem recebe de novo a piada e o Dono nao e incomodado


def test_auditoria_fica_registrada_em_log(monkeypatch):
    monkeypatch.setattr(revisao, "LOG", Path(memoria.ARQ).parent / "revisoes.log")
    monkeypatch.setattr(canal, "presente", lambda: False)
    monkeypatch.setattr(contexto, "decidir_claude", lambda *a, **k: None)
    revisao.decidir_com_revisao(item(), "-", ("E", "é zoeira"), 5)
    assert "NEUTRA" in revisao.LOG.read_text(encoding="utf-8")


def test_protocolo_documenta_a_revisao_e_o_respeito():
    doc = (Path(revisao.__file__).parent / "PROTOCOLO.md").read_text(encoding="utf-8")
    assert "Revisao de decisao" in doc and "NUNCA chame ninguem de trote" in doc
