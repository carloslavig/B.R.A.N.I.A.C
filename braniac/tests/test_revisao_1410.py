# -*- coding: utf-8 -*-
"""Revisao de 14/10: recado do Dono pra familia sem autonomia armada, queda do Chrome do agente, escuta sem gravar conversa da casa."""
import json
from braniac import escuta, jarvis, vigia


def test_familia_passa_sem_autonomia(monkeypatch):
    monkeypatch.setattr(jarvis.power, "armada", lambda: False)
    for nome in ("minha mãe", "Mãe", "Parceira", "parceira", "Irmao", "pai"):
        assert jarvis._gate_envio("whatsapp", "enviar mensagens", nome) is None, nome


def test_outros_contatos_continuam_travados(monkeypatch):
    monkeypatch.setattr(jarvis.power, "armada", lambda: False)
    for nome in ("Amigo Souza", "Loja", "Bruna", ""):
        assert jarvis._gate_envio("whatsapp", "enviar mensagens", nome), nome


def test_recado_da_carteira_e_pra_mae():
    t = "Jarvis, fala pra minha mãe que José Carvalho esqueceu a carteira na suite Suite C"
    m = jarvis.INTENCAO_ENVIO.match(t) or jarvis.INTENCAO_AVISO.match(t)
    assert m and jarvis._eh_familia(m["nome"].strip())


def test_ferramenta_de_envio_pra_familia_nao_e_bloqueada(monkeypatch):
    monkeypatch.setattr(jarvis.power, "armada", lambda: False)
    monkeypatch.setattr(jarvis, "_pedir_confirmacao_audio", lambda *a: "✅ áudio enviado")
    ex = jarvis._Executor(None, "c", "o", None, origem="whatsapp")
    if ex is None:
        return
    assert ex("whatsapp_enviar_audio", {"nome": "mãe", "texto": "oi"}) == "✅ áudio enviado"
    assert not ex.saida_direta


def test_queda_do_chrome_loga_pouco_e_reabre_1x_por_hora():
    q, reaberturas = vigia._Queda(), []
    erro = ConnectionRefusedError(10061, "recusada")
    logs = [q.registrar(erro, agora=1000 + 60 * i, reabrir=lambda: reaberturas.append(1)) for i in range(120)]
    assert sum(logs) == 2 and len(reaberturas) == 2      # 2 h fora do ar: 2 linhas de log, 2 tentativas de reabrir
    assert q.voltou() and not q.voltou()


def test_escuta_nao_grava_conversa_da_casa(monkeypatch):
    linhas = []
    monkeypatch.setattr(escuta, "_log", linhas.append)
    monkeypatch.setattr(escuta, "DEPURAR", True)
    e = escuta.Escuta.__new__(escuta.Escuta)
    if False:
        return
    e.estado = "dormindo"
    e.tratar_frase("vamos esvaziar a mala e vender o resto")
    assert not any("mala" in x for x in linhas)


def test_falha_ao_reabrir_nao_derruba_o_vigia(monkeypatch):
    monkeypatch.setattr(vigia, "_log", lambda *a: None)
    q = vigia._Queda()
    def explode():
        raise OSError("bat sumiu")
    assert q.registrar(ConnectionRefusedError(), agora=5000, reabrir=explode) is True
    q.voltou()
    chamadas = []
    q.registrar(ConnectionRefusedError(), agora=5100, reabrir=lambda: chamadas.append(1))
    assert chamadas == [1]       # depois de voltar, nova queda tenta reabrir na hora


def test_nome_curto_nao_casa_pedaco_de_outro_contato():
    from braniac import whatsapp
    lista = ["Parceira Lima 🤍", "Eu", "Amigo Souza 🌝", "Loja"]
    assert whatsapp.resolver_nome("Eu", lista) == ["Eu"]               # 14/10: 'Eu' caia em 'dEUsa Parceira'
    assert whatsapp.resolver_nome("Eu", ["Parceira Lima 🤍"]) == []
    assert whatsapp.resolver_nome("Souza", lista) == ["Amigo Souza 🌝"]
    assert whatsapp.resolver_nome("esfiha", lista) == ["Loja"]


def test_413_tenta_de_novo_enxuto_no_mesmo_provedor(tmp_path, monkeypatch):
    from braniac import router as R
    from braniac.store import Store
    monkeypatch.setenv("CHAVE_TESTE_413", "x")
    from braniac.providers import ProviderError
    tamanhos = []

    def groq(p, msgs, chave, timeout, tools):
        tamanho = len(str(msgs)) + len(str(tools))
        tamanhos.append(tamanho)
        if len(tamanhos) == 1:
            raise ProviderError("413 Request too large", 0)
        return {"content": "ok enxuto"}
    cfg = {"cadeia": [{"nome": "groq", "api": "openai", "tipo": "online", "chave_env": "CHAVE_TESTE_413"}], "system": "S" * 2000}
    r = R.Router(cfg=cfg, store=Store(tmp_path / "t.db"), chamadores={}, chamadores_tools={"openai": groq}, checar_pausa=False)
    tools = [{"type": "function", "function": {"name": f"f{i}", "description": "Faz algo. " + "detalhe " * 60,
                                               "parameters": {"type": "object", "properties": {"x": {"type": "string", "description": "y" * 200}}}}}
             for i in range(20)]
    msgs = [{"role": "system", "content": "S" * 15000}] + [{"role": "user", "content": "oi " * 200}] * 10
    m, nome = r._passo_com_ferramentas(msgs, tools, False, "oi")
    assert m["content"] == "ok enxuto" and len(tamanhos) == 2 and tamanhos[1] < tamanhos[0] / 2
    enx = R._ferramentas_enxutas(tools)
    assert [t["function"]["name"] for t in enx] == [t["function"]["name"] for t in tools]   # nenhuma ferramenta some
    assert enx[0]["function"]["description"] == "Faz algo."


def test_fala_nao_duplica_quando_agente_cai_e_reserva_responde(tmp_path):
    from braniac import router as R
    from braniac.store import Store
    r = R.Router(cfg={"cadeia": [], "system": "s"}, store=Store(tmp_path / "t.db"), chamadores={}, chamadores_tools={}, checar_pausa=False)
    r._add_fala("c", "oi")
    r._add_fala("c", "oi")
    assert [m["content"] for m in r.store.historico("c", 10)] == ["oi"]


class _AbaFalsa:
    """Imita o Chrome do agente: lista de conversas, abrir e o nome no topo do chat."""
    def __init__(self, conversas, topo=None):
        self.conversas, self.topo, self.digitado, self.aberta = conversas, topo, [], None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def js(self, codigo):
        import json
        if "#main header" in codigo:
            return self.topo if self.topo is not None else (self.aberta or "")
        if "contenteditable" in codigo:
            return True
        return json.dumps([{"nome": n} for n in self.conversas])

    def cmd(self, metodo, params=None):
        if metodo == "Input.insertText":
            self.digitado.append(params["text"])


def _wpp_falso(aba):
    import types
    W = types.SimpleNamespace(JS_LISTA="lista", WA=lambda: aba)
    W.abrir = lambda w, nome: setattr(aba, "aberta", nome.split(" 🤍")[0]) or True
    return W


def test_trava_bloqueia_quando_o_chat_aberto_nao_e_o_pedido(monkeypatch):
    from braniac import whatsapp
    aba = _AbaFalsa(["Eu", "Parceira Lima 🤍"], topo="Parceira Lima")   # clicou na conversa errada
    monkeypatch.setattr(whatsapp, "_wpp", lambda: _wpp_falso(aba))
    monkeypatch.setattr(whatsapp.time, "sleep", lambda s: None)
    r = whatsapp.enviar("Eu", "resumo pro Dono")
    assert r.startswith("🔒 Não enviei") and aba.digitado == []


def test_trava_libera_o_contato_certo_com_emoji_e_apelido(monkeypatch):
    from braniac import whatsapp
    aba = _AbaFalsa(["Eu", "Parceira Lima 🤍"])
    monkeypatch.setattr(whatsapp, "_wpp", lambda: _wpp_falso(aba))
    monkeypatch.setattr(whatsapp.time, "sleep", lambda s: None)
    assert whatsapp.enviar("Parceira Lima 🤍", "oi").startswith("✅") and aba.digitado == ["oi"]
    assert whatsapp.destino_confere("parceira", "Parceira Lima")
    assert whatsapp.destino_confere("Eu", "Eu")
    assert not whatsapp.destino_confere("Eu", "Parceira Lima")
    assert not whatsapp.destino_confere("Amigo Pereira", "Amigo Souza")
    assert not whatsapp.destino_confere("mae", "")                    # nao conseguiu ler o topo: nao envia


def test_testes_nao_alcancam_o_whatsapp_real():
    import socket
    s = socket.socket()
    try:
        assert s.connect_ex(("127.0.0.1", 9222)) != 0
    finally:
        s.close()


def test_ferramentas_por_assunto():
    from braniac import jarvis
    nomes = lambda t, h=(): {f["function"]["name"] for f in jarvis.ferramentas_para(t, h)}
    assert jarvis.NUCLEO <= nomes("bom dia")
    assert "agenda" in nomes("me lembra amanhã às 9h de ligar pro banco") and "airbnb_reserva" not in nomes("me lembra amanhã às 9h")
    assert "airbnb_reserva" in nomes("aceita a reserva do hóspede João")
    assert "spotify" in nomes("toca um rock aí")
    assert "email" in nomes("chegou alguma vaga no email?")
    assert "agenda" in nomes("sim, pode marcar", [{"role": "assistant", "content": "Quer que eu anote na agenda sexta às 15h?"}])   # continua o assunto
    assert len(jarvis.ferramentas_para("bom dia")) < len(jarvis.FERRAMENTAS) / 3


def _router_falso(tmp_path, monkeypatch, passos, fechar="Resposta final com o que eu tenho."):
    from braniac import router as R
    from braniac.store import Store
    monkeypatch.setenv("CHAVE_TESTE_AG", "x")
    seq = iter(passos)
    cfg = {"cadeia": [{"nome": "x", "api": "openai", "tipo": "online", "chave_env": "CHAVE_TESTE_AG"}], "system": "s"}
    return R.Router(cfg=cfg, store=Store(tmp_path / "t.db"), chamadores={"openai": lambda *a: fechar},
                    chamadores_tools={"openai": lambda *a: next(seq)}, checar_pausa=False)


def test_agente_sem_passos_responde_em_vez_de_mandar_pro_claude(tmp_path, monkeypatch):
    chamada = lambda i: {"content": None, "tool_calls": [{"id": str(i), "function": {"name": "f", "arguments": json.dumps({"i": i})}}]}
    r = _router_falso(tmp_path, monkeypatch, [chamada(i) for i in range(6)])
    final, _ = r.responder_agente("c", "oi", [], lambda n, a: "ok")
    assert final == "Resposta final com o que eu tenho." and "Claude" not in final


def test_ferramenta_repetida_nao_roda_de_novo(tmp_path, monkeypatch):
    mesma = {"content": None, "tool_calls": [{"id": "1", "function": {"name": "f", "arguments": "{}"}}]}
    r = _router_falso(tmp_path, monkeypatch, [mesma, mesma, {"content": "pronto"}])
    execs = []
    final, _ = r.responder_agente("c", "oi", [], lambda n, a: execs.append(n) or "res")
    assert final == "pronto" and execs == ["f"]


def test_ver_imagem_do_contato_vai_direto_sem_ia(monkeypatch):
    from braniac import contexto, wpp_img
    monkeypatch.setattr(jarvis.power, "armada", lambda: True)
    contexto.registrar_contato("irmao", "Irmao")
    assert jarvis._imagem_de("Mande ele ver o que Irmao mandou em foto") == "Irmao"
    assert jarvis._imagem_de("olha a foto bonita do pôr do sol") is None
    visto = []
    monkeypatch.setattr(wpp_img, "ver_ultima_imagem", lambda n: visto.append(n) or ("texto do e-mail", None))

    class SemIA:
        def responder_agente(self, *a, **k):
            raise AssertionError("nao devia chamar IA")
    r, da_ia = jarvis.processar(SemIA(), "olha a imagem que o Irmao mandou", "c", origem="whatsapp")
    assert r == "🖼 Irmao: texto do e-mail" and visto == ["Irmao"] and not da_ia


def test_voz_eleven_e_primeira_escolha():
    from pathlib import Path
    from braniac import voz
    assert voz.VOZ_ELEVEN == "2CECaLAGTS5NRGxgbcxr"
    import inspect
    fonte = inspect.getsource(voz._falar_wav_motores)
    assert "_eleven_wav" in fonte and fonte.index("_eleven_wav") < fonte.index("_gemini_wav")   # 1a escolha
    try:
        voz._eleven_wav("oi")                      # sem chave: levanta e a cadeia antiga continua valendo
    except Exception as e:
        assert "ELEVENLABS_API_KEY" in str(e) or "HTTP" in str(e)
