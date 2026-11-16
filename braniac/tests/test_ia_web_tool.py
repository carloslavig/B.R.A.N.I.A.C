# -*- coding: utf-8 -*-
import pytest
from braniac import ia_web, jarvis, power


def test_consulta_devolve_a_resposta_da_ia(monkeypatch):
    chamadas = []
    monkeypatch.setattr(ia_web, "perguntar", lambda ia, p, *a, **k: chamadas.append((ia, p)) or "Canberra")
    assert jarvis._consultar_ia_web("Grok", "Qual a capital da Austrália?") == "Canberra"
    assert chamadas == [("grok", "Qual a capital da Austrália?")]


def test_ia_desconhecida_e_pergunta_vazia():
    assert "desconhecida" in jarvis._consultar_ia_web("bard", "oi")
    assert jarvis._consultar_ia_web("gemini", "  ") == "pergunta vazia"


def test_dado_sensivel_nunca_vai_para_a_nuvem(monkeypatch):
    monkeypatch.setattr(ia_web, "perguntar", lambda *a, **k: pytest.fail("nao pode ir para a IA online"))
    assert "barrada" in jarvis._consultar_ia_web("chatgpt", "minha senha do banco é 1234, o que faço?")


def test_erro_da_aba_vira_aviso_e_nao_excecao(monkeypatch):
    def falha(*a, **k):
        raise ia_web.IAWebErro("captcha/verificacao: precisa do Dono")
    monkeypatch.setattr(ia_web, "perguntar", falha)
    r = jarvis._consultar_ia_web("gemini", "ideia de promoção")
    assert "nao consegui falar com gemini" in r and "captcha" in r


def test_pelo_whatsapp_so_com_autonomia_armada(monkeypatch):
    monkeypatch.setattr(power, "armada", lambda: False)
    monkeypatch.setattr(ia_web, "perguntar", lambda *a, **k: pytest.fail("bloqueado pela trava"))
    ex = jarvis._Executor(router=None, conv="c", original="o", notificar=None, origem="whatsapp")
    assert "bloqueado" in ex("consultar_ia_web", {"ia": "grok", "pergunta": "verifique isso"})
    assert any("Autonomia remota" in x for x in ex.saida_direta)


def test_ferramenta_esta_na_lista_do_jarvis():
    assert "consultar_ia_web" in [f["function"]["name"] for f in jarvis.FERRAMENTAS]


@pytest.mark.parametrize("frase,ia", [
    ("Jarvis, pergunta pro Grok qual é a capital do Canadá e me diz o que ele respondeu.", "grok"),
    ("pergunta pro GPT quais combos de esfiha vendem mais no inverno", "chatgpt"),
    ("entra em contato com o chat gpt e pergunta quanto tempo leva para assar esfiha aberta", "chatgpt"),
    ("pede pro gemini ideias de nome para uma promoção de esfiha", "gemini"),
])
def test_pergunta_a_ia_nao_vira_mensagem_de_whatsapp(monkeypatch, frase, ia):
    chamadas = []
    monkeypatch.setattr(ia_web, "perguntar", lambda i, p, *a, **k: chamadas.append((i, p)) or "resposta ok")
    monkeypatch.setattr(jarvis, "_pedir_confirmacao", lambda *a, **k: pytest.fail("nao e mensagem de WhatsApp"))
    resp, da_ia = jarvis.processar(None, frase, "c", None, origem="web")
    assert chamadas and chamadas[0][0] == ia and "resposta ok" in resp and da_ia is False
    assert "e me diz" not in chamadas[0][1].lower()


def test_pergunta_vaga_pede_a_pergunta_completa(monkeypatch):
    monkeypatch.setattr(ia_web, "perguntar", lambda *a, **k: pytest.fail("sem pergunta nao consulta"))
    resp, _ = jarvis.processar(None, "entra em contato com o gpt e pergunta uma coisa", "c", None, origem="web")
    assert "pergunta completa" in resp


def test_mensagem_a_contato_comum_continua_funcionando(monkeypatch):
    pedidos = []
    monkeypatch.setattr(jarvis, "_pedir_confirmacao", lambda r, n, t, o: pedidos.append((n, t)) or "confirma?")
    jarvis.processar(None, "avisa a Parceira que o cardápio já foi atualizado", "c", None, origem="web")
    assert pedidos and pedidos[0][0].lower().startswith("parceira")


@pytest.mark.parametrize("frase", [
    "Jarvis, o que você sabe sobre mim?",
    "quem sou eu na sua opinião, me descreve",
    "quais são os meus projetos mais importantes?",
])
def test_pergunta_pessoal_do_dono_vai_ao_chatgpt(monkeypatch, frase):
    chamadas = []
    monkeypatch.setattr(ia_web, "perguntar", lambda i, p, *a, **k: chamadas.append((i, p)) or "Você é o Dono, estuda engenharia de software.")
    resp, da_ia = jarvis.processar(None, frase, "c", None, origem="web")
    assert chamadas and chamadas[0][0] == "chatgpt" and "sobre mim" in chamadas[0][1] and "engenharia" in resp and da_ia is False


def test_pergunta_pessoal_pelo_whatsapp_exige_autonomia(monkeypatch):
    monkeypatch.setattr(power, "armada", lambda: False)
    monkeypatch.setattr(ia_web, "perguntar", lambda *a, **k: pytest.fail("bloqueado"))
    resp, _ = jarvis.processar(None, "o que você sabe sobre mim?", "c", None, origem="whatsapp")
    assert "Autonomia remota" in resp


def test_mandar_recado_que_cita_mim_nao_vira_pergunta_pessoal(monkeypatch):
    monkeypatch.setattr(ia_web, "perguntar", lambda *a, **k: pytest.fail("nao e pergunta pessoal"))
    pedidos = []
    monkeypatch.setattr(jarvis, "_pedir_confirmacao", lambda r, n, t, o: pedidos.append(n) or "confirma?")
    jarvis.processar(None, "avisa a Parceira que ela pode falar de mim com a Bruna", "c", None, origem="web")
    assert pedidos
