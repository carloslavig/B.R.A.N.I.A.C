# -*- coding: utf-8 -*-
import pytest
from braniac import confirmacao, contexto, jarvis, whatsapp, voz, wpp_voz


@pytest.mark.parametrize("frase", [
    "sim", "Sim.", "pode sim", "Pode mandar", "manda aí", "manda ver", "mande", "faça", "faz", "pode fazer", "isso mesmo", "claro",
    "com certeza", "beleza", "fechou", "bora", "vai lá", "positivo", "confirmo", "uhum", "tá bom", "pode ser", "Sim, podem ver.", "manda bala", "/sim", "ok",
])
def test_frases_que_confirmam(frase):
    assert confirmacao.classificar(frase) == "sim", frase


@pytest.mark.parametrize("frase", [
    "não", "nao", "nem fudendo", "nem a pau", "tá maluco?", "ta doido", "não é pra mandar", "nao quero", "cancela", "esquece isso", "deixa quieto",
    "de jeito nenhum", "negativo", "jamais", "melhor não", "para", "pare tudo", "/nao", "não, cancela isso", "nem pensar",
])
def test_frases_que_negam(frase):
    assert confirmacao.classificar(frase) == "nao", frase


@pytest.mark.parametrize("frase", [
    "me explica melhor", "manda um áudio pra Parceira dizendo oi", "manda uma mensagem pra mainha avisando que cheguei",
    "qual é a capital da França", "o que você acha disso e do plano que a gente fez ontem à noite com a Bruna",
    "nao sei se entendi o que voce quer dizer com isso", "", "simplesmente não quero isso agora porque mudei de ideia e prefiro esperar",
])
def test_frases_que_nao_sao_confirmacao(frase):
    assert confirmacao.classificar(frase) is None, frase


def test_a_primeira_palavra_decide_quando_ha_sim_e_nao():
    assert confirmacao.classificar("não, pode mandar") == "nao"
    assert confirmacao.classificar("pode mandar, não") == "sim"


def test_jarvis_usa_o_classificador_natural():
    assert jarvis._eh_sim("manda ver") and jarvis._eh_nao("nem a pau") and not jarvis._eh_sim("nem a pau")


def test_mensagem_para_o_proprio_dono_sai_sem_confirmacao(monkeypatch):
    dono = contexto.contato("dono")
    enviados = []
    monkeypatch.setattr(jarvis, "_resolver_contato", lambda r, n, o: (dono, ""))
    monkeypatch.setattr(whatsapp, "enviar", lambda n, t: enviados.append((n, t)) or "✅ ok")
    jarvis.PENDENTE.clear()
    r = jarvis._pedir_confirmacao(None, "Dono", "Teste", "orig")
    assert enviados == [(dono, "Teste")] and not jarvis.PENDENTE and "✅" in r


def test_audio_para_o_proprio_dono_sai_sem_confirmacao(monkeypatch):
    dono = contexto.contato("dono")
    enviados = []
    monkeypatch.setattr(jarvis, "_resolver_contato", lambda r, n, o: (dono, ""))
    monkeypatch.setattr(wpp_voz, "enviar_voz", lambda n, w: enviados.append(n) or "✅ ok")
    jarvis.PENDENTE.clear()
    jarvis._pedir_confirmacao_audio(None, "Dono", "Teste", "orig")
    assert enviados == [dono] and not jarvis.PENDENTE


def test_audio_pedido_ao_dono_sai_em_audio_mesmo_com_por_escrito_salvo(monkeypatch):
    dono = contexto.contato("dono")   # bug 17/10: um "por escrito" antigo fazia o Jarvis dizer que o Eu so aceita texto
    enviados = []
    monkeypatch.setattr(jarvis, "_resolver_contato", lambda r, n, o: (dono, ""))
    monkeypatch.setattr(contexto, "preferencia", lambda c: "texto")
    monkeypatch.setattr(voz, "falar_wav", lambda t: b"wav")
    monkeypatch.setattr(wpp_voz, "enviar_voz", lambda n, w: enviados.append(n) or "✅ ok")
    assert jarvis._pedir_confirmacao_audio(None, "Dono", "Teste", "orig").startswith("✅") and enviados == [dono]


def test_para_outra_pessoa_tambem_sai_na_hora(monkeypatch):
    enviados = []
    monkeypatch.setattr(jarvis, "_resolver_contato", lambda r, n, o: ("Parceira", ""))
    monkeypatch.setattr(whatsapp, "enviar", lambda n, t: enviados.append((n, t)) or "✅ ok")
    jarvis.PENDENTE.clear()
    r = jarvis._pedir_confirmacao(None, "Parceira", "oi", "orig")
    assert enviados == [("Parceira", "oi")] and not jarvis.PENDENTE and "Confirma?" not in r


def test_dado_sensivel_continua_barrado_mesmo_sem_confirmacao(monkeypatch):
    monkeypatch.setattr(jarvis, "_resolver_contato", lambda r, n, o: ("Parceira", ""))
    monkeypatch.setattr(whatsapp, "enviar", lambda n, t: pytest.fail("pix/senha nunca sai"))
    assert "dado sensível" in jarvis._pedir_confirmacao(None, "Parceira", "me passa a senha do banco", "orig")


def test_parceira_e_sempre_deusa_parceira_nas_mensagens(monkeypatch):
    from braniac import tratamento
    assert tratamento.corrigir("Oi, Parceira! A Parceira ligou") == "Oi, Parceira! A Parceira ligou"
    assert tratamento.corrigir("Parceira, bom dia") == "Parceira, bom dia"
    assert "Parceira" in voz.limpar_para_fala("Parceira pediu isso")


def test_confirmar_falando_naturalmente_executa_o_pendente(monkeypatch):
    enviados = []
    monkeypatch.setattr(whatsapp, "enviar", lambda n, t: enviados.append((n, t)) or "✅ Mensagem enviada.")
    from braniac import power
    monkeypatch.setattr(power, "armada", lambda: True)
    import time
    jarvis.PENDENTE.clear()
    jarvis.PENDENTE.update(tipo="whatsapp", nome="Parceira", texto="oi", ate=time.time() + 60)
    resp, _ = jarvis.processar(None, "pode sim, manda ver", "c", None, origem="web")
    assert enviados == [("Parceira", "oi")]
    jarvis.PENDENTE.update(tipo="whatsapp", nome="Parceira", texto="oi", ate=time.time() + 60)
    resp, _ = jarvis.processar(None, "nem a pau", "c", None, origem="web")
    assert "Cancelado" in resp and len(enviados) == 1


def test_retratacao_nao_troca_o_nome_citado_como_erro():
    from braniac import tratamento
    assert tratamento.corrigir("peço desculpas por ter te chamado de Parceira. Você é a Parceira") == \
        "peço desculpas por ter te chamado de Parceira. Você é a Parceira"
    assert tratamento.corrigir("A Parceira ligou") == "A Parceira ligou"


def test_dois_pontos_depois_de_dizendo_nao_entra_na_mensagem(monkeypatch):
    enviados = []
    monkeypatch.setattr(jarvis, "_resolver_contato", lambda r, n, o: ("Parceira", ""))
    monkeypatch.setattr(whatsapp, "enviar", lambda n, t: enviados.append(t) or "✅ ok")
    jarvis.processar(None, "manda uma mensagem pra Parceira dizendo: já cheguei", "c", None, origem="web")
    assert enviados == ["já cheguei"]
