# -*- coding: utf-8 -*-
from braniac import conselho, contexto


def test_pedido_e_tema():
    assert conselho.pediu("Jarvis, use o conselho de IAs para decidir o preço da landing page")
    assert conselho.pediu("chama o conselho de IAs do braniac sobre cardápio novo")
    assert not conselho.pediu("pergunta pro grok que dia é hoje")
    assert "preço da landing" in conselho.tema_de("Jarvis, use o conselho de IAs para decidir o preço da landing page")


def test_citar_o_conselho_nao_dispara():
    assert not conselho.pediu("O conselho de IAs do Braniac sugeriu estas melhorias para você")
    assert not conselho.pediu("manda uma mensagem pra Loja dizendo: use o conselho de IAs do Braniac")


def test_quem_pode():
    assert conselho.pode_convocar("Loja Esphiraria") and conselho.pode_convocar("Parceira") and conselho.pode_convocar("Eu") is not None
    assert not conselho.pode_convocar("Amigo")


def test_reunir_junta_respostas_e_tolera_falha():
    def consultar(ia, p):
        return "nao consegui falar com grok agora" if ia == "grok" else f"opinião do {ia}"
    r = conselho.reunir("qual o melhor preço para a promoção de esfihas", consultar, lambda p: "faça X")
    assert "Conselho de IAs do Braniac" in r and "opinião do chatgpt" in r and "opinião do gemini" in r
    assert "não responderam: grok" in r and "Síntese: faça X" in r


def test_reunir_barrado_cancela():
    assert conselho.reunir("tema longo e valido aqui", lambda ia, p: "pergunta barrada: dado sensivel").startswith("Conselho cancelado")


def test_encerramento_da_layla():
    assert contexto.encerramento("Ok, obrigada! 👍") and contexto.encerramento("Entendido") and contexto.encerramento("beleza, valeu")
    assert not contexto.encerramento("Ok, e o pedido do João?") and not contexto.encerramento("Preciso de ajuda com o cardápio")


def test_resumo_whatsapp_vem_do_banco_local():
    from braniac import jarvis, memoria
    memoria.registrar_msg("Pessoa Teste", "E", "oi, tudo bem?")
    memoria.registrar_msg("Pessoa Teste", "C", "tudo sim!")
    r, da_ia = jarvis.processar(None, "me faz um resumo do que rolou no whatsapp hoje", "qualquer")
    assert not da_ia and "Pessoa Teste" in r and "tudo sim" in r


def test_conversa_unica_entre_pc_e_whatsapp():
    assert jarvis_conv() == "jarvis"


def jarvis_conv():
    from braniac import jarvis
    return jarvis.CONV_UNICA


# ---------- banco unificado ----------

def _banco_isolado(tmp_path, monkeypatch):
    from braniac import banco
    monkeypatch.setattr(banco, "ARQ", tmp_path / "jarvis.db")
    monkeypatch.setattr(banco, "_ultimo_sync", 1e18)      # sem sincronizar com as fontes reais
    from braniac import assuntos
    monkeypatch.setattr(assuntos, "PASTA", tmp_path / "assuntos")   # os bancos dos assuntos tambem isolados
    return banco


def test_banco_online_nunca_ve_camada_local(tmp_path, monkeypatch):
    banco = _banco_isolado(tmp_path, monkeypatch)
    banco.gravar_fato("regra", "tratamento", "Parceira e sempre Parceira", "publico")
    banco.gravar_fato("pessoa", "x", "Fulano disse que vai pagar o pix amanha", "local")
    banco.registrar_evento("whatsapp", "Fulano", "E", "mensagem privada do Fulano sobre Parceira", "local")
    online, usou_online = banco.consultar("Parceira Fulano", "online")
    assert "Parceira" in online and "Fulano disse" not in online and "privada" not in online and not usou_online
    local, usou_local = banco.consultar("Parceira Fulano", "local")
    assert "privada" in local and "Fulano disse" in local and usou_local


def test_banco_sem_registro_manda_nao_inventar(tmp_path, monkeypatch):
    banco = _banco_isolado(tmp_path, monkeypatch)
    texto, _ = banco.consultar("assunto inexistente zzz", "local")
    assert "nao invente" in texto.lower()


def test_pacote_traz_instrucao_para_toda_ia(tmp_path, monkeypatch):
    banco = _banco_isolado(tmp_path, monkeypatch)
    assert "FONTE UNICA DA VERDADE" in banco.pacote("oi", "online") and "FONTE UNICA DA VERDADE" in banco.pacote("oi", "local")


def test_ferramenta_com_dado_local_marca_para_nao_ir_a_ia_online(tmp_path, monkeypatch):
    banco = _banco_isolado(tmp_path, monkeypatch)
    banco.registrar_evento("whatsapp", "Beltrano", "E", "quero o orcamento da landing page", "local")
    banco.definir_tipo("local")
    banco.ferramenta("Beltrano orcamento")
    assert banco.usou_local()
    banco.limpar_marca()
    banco.definir_tipo("online")
    assert "orcamento" not in banco.ferramenta("Beltrano orcamento")
    assert not banco.usou_local()


def test_pergunta_sobre_contato_vem_do_banco(tmp_path, monkeypatch):
    from braniac import jarvis
    banco = _banco_isolado(tmp_path, monkeypatch)
    banco.registrar_evento("whatsapp", "Loja", "E", "Layla perguntou como foi o pedido", "local")
    r, da_ia = jarvis.processar(None, "o que a Loja me perguntou por último?", "x")
    assert not da_ia and "como foi o pedido" in r


def test_reuniao_do_chatgpt_abre_dentro_do_projeto(monkeypatch):
    from braniac import ia_web, jarvis
    visto = {}
    monkeypatch.setattr(ia_web, "perguntar", lambda ia, p, *a, **k: visto.update(ia=ia, k=k) or "ok")
    assert jarvis.consultar_reuniao("chatgpt", "tema") == "ok" and visto["k"].get("reuniao") is True
    assert "reunioes-das-ias/project" in ia_web.SITES["chatgpt"]["projeto"]
