import json
import time

import pytest

from braniac import clareza as c

LAYLA = "Ué, Layla falou isso por onde?"
OCARA = "Você sabe o que é o projeto Ocarã?"


@pytest.fixture(autouse=True)
def isolado(tmp_path, monkeypatch):
    monkeypatch.setattr(c, "DATA", tmp_path)
    monkeypatch.setattr(c, "LOG", tmp_path / "clareza.jsonl")


def test_reescreve_so_mensagem_curta_que_depende_de_contexto():
    assert c.precisa_reescrever(LAYLA)                 # caso real de 06/11: "isso" sem contexto
    assert c.precisa_reescrever("e o preço?")
    assert not c.precisa_reescrever("A Layla disse que o estoque acabou, anota isso")      # afirmacao/pedido: nao reescreve
    assert not c.precisa_reescrever("qual o saldo da conta?")
    assert not c.precisa_reescrever("/auto off")


def test_reescrever_devolve_pergunta_completa_ou_ambiguo():
    ctx = "Dono: a Layla disse que o estoque acabou\nJarvis: entendi"
    assert c.reescrever(LAYLA, ctx, lambda s, t: "Onde a Layla disse que o estoque acabou?").startswith("Onde a Layla")
    assert c.reescrever(LAYLA, ctx, lambda s, t: "AMBIGUO") == "AMBIGUO"
    assert c.reescrever(LAYLA, ctx, lambda s, t: "linha 1\nlinha 2") is None            # lixo: segue sem reescrita
    assert c.reescrever(LAYLA, ctx, lambda s, t: 1 / 0) is None
    assert c.reescrever(LAYLA, ctx, lambda s, t: "IGUAL") is None


def test_nota_de_contexto_usa_historico_da_conversa():
    class Store:
        def historico(self, conv, n):
            return [{"role": "user", "content": "a Layla disse que o estoque acabou"}, {"role": "assistant", "content": "entendi, vou anotar isso"}]

    class R:
        store = Store()

        def responder_neutro(self, sistema, texto):
            return "Onde a Layla disse que o estoque acabou?"

    assert "COM O CONTEXTO RESOLVIDO" in c.nota_de_contexto(R(), LAYLA, LAYLA, "x")
    assert c.nota_de_contexto(R(), "qual o saldo da conta?", "qual o saldo da conta?", "x") == ""      # completa: nao gasta IA


def test_sem_registro_nao_chuta_e_so_vale_para_projeto_ou_cliente():
    r = c.sem_registro(OCARA, tem_fato=lambda n: False)        # caso real de 04/11: ele inventou que era assistente da Loja
    assert "Ocarã" in r and "Não tenho" in r
    assert c.sem_registro(OCARA, tem_fato=lambda n: True) is None
    assert c.sem_registro("o que é Pix copia e cola?", tem_fato=lambda n: False) is None     # conhecimento geral nao entra


def test_resposta_fora_do_assunto_e_refeita_uma_vez():
    p = "Qual o preço da landing page para a esfiharia do Marcos?"
    assert c.fora_do_assunto(p, "Bom dia! Hoje o tempo está ótimo em Cidade, aproveite o dia lá fora.")
    assert not c.fora_do_assunto(p, "A landing page custa R$ 150 na promoção.")
    assert not c.fora_do_assunto(p, "Qual esfiharia você quer dizer, a do Marcos?")        # pergunta de volta nunca e 'fora'
    chamadas = []
    r = c.conferir(("Bom dia! Hoje o tempo está ótimo em Cidade, aproveite.", True), p,
                   lambda dica: chamadas.append(dica) or ("A landing page custa R$ 150.", True))
    assert r[0].startswith("A landing") and len(chamadas) == 1 and p in chamadas[0]
    boa = ("A landing page custa R$ 150.", True)
    assert c.conferir(boa, p, lambda d: 1 / 0) is boa


def test_polir_filtra_antes_de_mandar_a_terceiro():
    assert c.polir("Fulano", "Pronto! Usei o Claude pra conferir. O valor é R$ 150.", "quanto custa?") == "Pronto! O valor é R$ 150."
    assert c.polir("Fulano", "Sou o Braniac, o sistema do Dono.", "oi") is None                    # so tinha vazamento
    assert c.polir("Fulano", "De nada, fico à disposição!", "valeu, obrigado") is None               # agradecimento: sem resposta
    assert c.polir("Fulano", "O valor é R$ 150 para a primeira página.", "quanto custa?", ["O valor é R$ 150 para a primeira página."]) is None
    longo = ". ".join(f"Frase número {i} bem comprida para encher espaço" for i in range(1, 12)) + "."
    assert len(c.polir("Fulano", longo, "e o prazo?")) <= 320
    assert c.polir("Fulano", longo, "me explica em detalhes como funciona") == longo
    assert c.polir("Eu", "Usei o Claude e o Braniac.", "oi") == "Usei o Claude e o Braniac."      # Dono passa direto


def test_classifica_os_erros_reais(monkeypatch):
    from braniac import banco
    monkeypatch.setattr(banco, "quem_e", lambda t: None)
    ocara = "Sim, Senhor. O projeto Ocarã é um assistente virtual para a Loja."
    assert "inventou" in c.classificar(OCARA, ocara)
    assert c.classificar("oi", "Sou o Jarvis, assistente de IA do Dono, e posso ajudar.") == ["reapresentou"]
    assert c.classificar("qual o prazo da página?", "ok") == ["outro"]


def test_resumo_conta_marcados_claudinho_e_travas(tmp_path):
    agora = time.time()
    (tmp_path / "erros_jarvis.jsonl").write_text(json.dumps({"ts": agora, "pedido": "oi", "resposta_errada": "x", "tipos": ["exagerou"]}) + "\n" +
                                                 json.dumps({"ts": agora - 30 * 86400, "pedido": "a", "resposta_errada": "b", "tipos": ["velho"]}) + "\n", encoding="utf-8")
    (tmp_path / "claudinho").mkdir()
    (tmp_path / "claudinho" / "achados.jsonl").write_text(json.dumps({"ts": agora, "tipo": "repetiu"}) + "\n", encoding="utf-8")
    c._evento("ambiguo", "x")
    r = c.resumo()
    assert r["marcados"] == {"exagerou": 1} and r["claudinho"] == {"repetiu": 1} and r["travas"] == {"ambiguo": 1}
