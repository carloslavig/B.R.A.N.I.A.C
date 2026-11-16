# -*- coding: utf-8 -*-
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import pytest
from braniac import atender, contexto, dono, whatsapp


@pytest.fixture(autouse=True)
def isolado(tmp_path, monkeypatch):
    monkeypatch.setattr(contexto, "ARQ", tmp_path / "contexto.json")
    monkeypatch.setattr(dono, "ARQ", tmp_path / "dono_estado.json")
    monkeypatch.setattr(dono, "LOG", tmp_path / "dono.log")
    monkeypatch.setattr(dono, "DATA", tmp_path)
    monkeypatch.setattr(whatsapp, "PEND_ARQ", tmp_path / "pend.json")
    monkeypatch.setattr(whatsapp, "DATA", tmp_path)


def m(d, t, c="[16:00, 01/10/2026] X: "):
    return {"d": d, "t": t, "c": c}


# o caso real do Dono: pediu, o Jarvis respondeu so a primeira, e as ordens ficaram sem resposta
CHAT = [m("ELE", "Tá por aí?"), m("EU", "Tô por aqui sim! Como posso ajudar?"),
        m("ELE", "Quero que você me mande um áudio explicando quem você é", "[16:21] E: "),
        m("EU", "Jarvis ✓ atendimento: ..."), m("ELE", "Faz o que eu mandei", "[16:23] E: ")]


def lista(msgs, midias=(), sig="1|resumo"):
    return lambda nome, anterior: None if sig == anterior else {"msgs": msgs, "midias": list(midias), "lista_sig": sig}


def test_pendentes_sao_so_o_que_veio_depois_da_ultima_resposta():
    assert [x["t"] for x in dono.pendentes(CHAT)] == ["Faz o que eu mandei"]
    assert dono.pendentes([m("ELE", "a"), m("EU", "b")]) == []


def test_responde_a_mensagem_sem_resposta_com_historico_e_contexto():
    pedidos, enviados = [], []
    resp = dono.tratar_dono(None, ler=lista(CHAT), responder=lambda p: pedidos.append(p) or "Mandei o áudio no Telegram.",
                            enviar=lambda n, x: enviados.append((n, x)) or "✅ ok")
    assert resp == "Mandei o áudio no Telegram." and enviados == [("Eu", "Mandei o áudio no Telegram.")]
    assert pedidos[0].startswith("Faz o que eu mandei")
    assert "áudio explicando quem você é" in pedidos[0]  # o historico vai junto: 'o que eu mandei' faz sentido


def test_nao_responde_duas_vezes_a_mesma_mensagem():
    env = []
    kw = dict(responder=lambda p: "ok", enviar=lambda n, x: env.append(x) or "✅")
    assert dono.tratar_dono(None, ler=lista(CHAT, sig="A"), **kw) == "ok"
    assert dono.tratar_dono(None, ler=lista(CHAT, sig="B"), **kw) is None  # lista mudou mas a msg e a mesma
    assert dono.tratar_dono(None, ler=lista(CHAT, sig="B"), **kw) is None
    assert len(env) == 1


def test_nova_mensagem_depois_da_resposta_e_respondida():
    env = []
    kw = dict(responder=lambda p: "ok", enviar=lambda n, x: env.append(x) or "✅")
    dono.tratar_dono(None, ler=lista(CHAT, sig="A"), **kw)
    mais = CHAT + [m("EU", "ok"), m("ELE", "E agora?", "[16:30] E: ")]
    assert dono.tratar_dono(None, ler=lista(mais, sig="C"), **kw) == "ok" and len(env) == 2


def test_so_o_jarvis_falou_por_ultimo_nao_responde():
    env = []
    assert dono.tratar_dono(None, ler=lista(CHAT + [m("EU", "pronto")]), responder=lambda p: "x",
                            enviar=lambda n, x: env.append(x) or "✅") is None and env == []


def test_nunca_fica_mudo_quando_a_ia_quebra():
    env = []

    def quebra(p):
        raise RuntimeError("provedores fora")
    r = dono.tratar_dono(None, ler=lista(CHAT), responder=quebra, enviar=lambda n, x: env.append(x) or "✅")
    assert r == dono.ESTOU_VENDO and len(env) == 1   # 16/11: "to vendo, ja te falo"
    env.clear()
    dono.ARQ.unlink()
    assert dono.tratar_dono(None, ler=lista(CHAT), responder=lambda p: "   ", enviar=lambda n, x: env.append(x) or "✅")
    assert "estou aqui" in env[0]  # resposta vazia da IA tambem vira resposta


def test_audio_do_dono_recebe_aviso():
    pedidos = []
    dono.tratar_dono(None, ler=lista([m("EU", "oi")], midias=[{"d": "ELE", "c": "", "t": "[AUDIO]"}]),
                     responder=lambda p: pedidos.append(p) or "ok", enviar=lambda n, x: "✅")
    assert "áudio" in pedidos[0]


def test_documento_do_dono_e_baixado_e_explicado(monkeypatch, tmp_path):
    # 15/11: dois .doc do Dono viraram 'mandou um audio que nao consigo ouvir'
    from braniac import claude_agent, wpp_doc
    monkeypatch.setattr(wpp_doc, "baixar", lambda c, a: tmp_path / a)
    tarefas, env, pedidos = [], [], []
    monkeypatch.setattr(claude_agent, "executar_em_segundo_plano", lambda t, n: tarefas.append(t))
    docs = [{"d": "ELE", "c": "", "t": "[DOC:a.doc]"}, {"d": "ELE", "c": "", "t": "[DOC:b.doc]"}]
    r = dono.tratar_dono(None, ler=lista([m("EU", "oi")], midias=docs), responder=lambda p: pedidos.append(p) or "x",
                         enviar=lambda n, x: env.append(x) or "✅")
    assert "a.doc, b.doc" in r and "áudio" in r and not pedidos and len(tarefas) == 1
    assert "a.doc" in tarefas[0] and "b.doc" in tarefas[0] and "outbox_dono" in tarefas[0]
    assert dono.tratar_dono(None, ler=lista([m("EU", "oi")], midias=docs, sig="2|x"), enviar=lambda n, x: env.append(x) or "✅") is None
    assert len(env) == 1   # nao trata de novo


def test_resposta_vira_uma_linha_limpa():
    assert dono.formatar_resposta("**Oi**\n\nTudo bem?\n- item") == "Oi Tudo bem? - item"
    assert len(dono.formatar_resposta("x" * 5000)) == 1500


# ---------- dossie ----------

def test_dossie_traz_so_o_relevante():
    base = contexto.dossie_para("oi")
    assert "[dono]" in base and "[sistema]" in base and "[tom]" in base and "[mariana]" not in base
    d = contexto.dossie_para("o que a Mariana falou do cartório de Cidade?")
    assert "[mariana]" in d and "cartório" in d
    assert "[airbnb]" in contexto.dossie_para("tem hóspede no studio hoje?")
    assert len(contexto.dossie_para("parceira mariana airbnb vagas landing")) <= 5400
    assert "[parceira]" in contexto.dossie_para("fala com a deusa")


def test_dossie_aprende_sem_perder_a_semente():
    contexto.registrar_dossie("irmao", "quem", "Irmao é o irmão do Dono; no WhatsApp aparece como 'Junior'.")
    contexto.registrar_dossie("irmao", "recente", "pediu ajuda com o PC")
    assert "Junior" in contexto.dossie_para("fala com o irmao") and "pediu ajuda" in contexto.dossie_para("irmao")
    assert "[dono]" in contexto.dossie_para("oi")  # semente continua


def test_dossie_completo_vai_para_o_claude():
    assert "[mariana]" in contexto.base_conhecimento(limite=99999) or "mariana" in contexto.base_conhecimento(limite=99999).lower()


# ---------- atendimento: conversas lidas mas sem resposta continuam pendentes ----------

def test_pendencias_persistem_e_saem_quando_tratadas():
    whatsapp.pendente_add("Maria")
    whatsapp.pendente_add("Maria")
    whatsapp.pendente_add("Ana")
    assert whatsapp.pendentes_ler() == ["Maria", "Ana"]
    whatsapp.pendente_remover("Maria")
    assert whatsapp.pendentes_ler() == ["Ana"]


def test_atender_vê_pendente_mesmo_depois_de_lida(monkeypatch):
    whatsapp.pendente_add("Maria")
    enviados = []
    monkeypatch.setattr(whatsapp, "enviar", lambda n, x: enviados.append((n, x)) or f"✅ enviada {n}")
    monkeypatch.setattr(atender.time, "sleep", lambda s: None)
    item = {"nome": "Maria", "nl": 1, "msgs": ["tem vaga?"], "ctx": ["E: tem vaga?"], "autores": {"Maria"}, "midia": False}
    monkeypatch.setattr(atender, "coletar", lambda *a, **k: [item])
    monkeypatch.setattr(atender, "decidir", lambda it, fl, esp=0: ("E", "Tem sim! Qual data?"))
    atender.atender(espaco_s=(0, 0), relatar=False)
    assert enviados[0][0] == "Maria" and whatsapp.pendentes_ler() == []  # tratada: sai da fila


def test_pergunta_ao_claude_leva_o_historico():
    q = atender.canal.formatar_pergunta("ab", "Maria", "-", ["tem vaga?"], ["E: oi", "C: oi!", "E: tem vaga?"])
    assert q == "Q|ab|Maria|-|tem vaga?|E: oi»C: oi!»E: tem vaga?" and q.count("\n") == 0


# ---------- audio: ele fala no WhatsApp, o Jarvis ouve e responde em audio ----------

def lista_audio(msgs, n=3, sig="1|audio", dele=True):
    return lambda nome, anterior: None if sig == anterior else {
        "msgs": msgs, "midias": [], "lista_sig": sig, "audio_dele": dele, "n_audios": n}


def test_audio_dele_e_ouvido_e_respondido_em_audio():
    pedidos, voz_env, txt_env = [], [], []
    r = dono.tratar_dono(None, ler=lista_audio([m("EU", "oi")]), ouvir=lambda n: ("quem é você, Jarvis?", None),
                         responder=lambda p: pedidos.append(p) or "Sou o Jarvis, seu assistente.",
                         falar=lambda n, t: voz_env.append((n, t)) or True, enviar=lambda n, x: txt_env.append(x) or "✅")
    assert r == "Sou o Jarvis, seu assistente."
    assert voz_env == [("Eu", "Sou o Jarvis, seu assistente.")] and txt_env == []  # falou -> so audio de volta
    assert "🎙[áudio do Dono]: quem é você, Jarvis?" in pedidos[0] and "Conversa recente" in pedidos[0]


def test_mesmo_audio_nao_e_ouvido_duas_vezes_e_audio_novo_sim():
    ouvidos = []
    kw = dict(ouvir=lambda n: ouvidos.append(1) or ("oi", None), responder=lambda p: "ok", falar=lambda n, t: True, enviar=lambda n, x: "✅")
    dono.tratar_dono(None, ler=lista_audio([m("EU", "x")], n=3, sig="A"), **kw)
    dono.tratar_dono(None, ler=lista_audio([m("EU", "x")], n=3, sig="B"), **kw)   # lista mudou, audio e o mesmo
    assert len(ouvidos) == 1
    dono.tratar_dono(None, ler=lista_audio([m("EU", "x")], n=4, sig="C"), **kw)   # chegou outro audio
    assert len(ouvidos) == 2


def test_audio_cai_para_texto_se_a_voz_falhar_e_resposta_longa_ainda_e_audio():
    txt = []
    kw = dict(ouvir=lambda n: ("oi", None), enviar=lambda n, x: txt.append(x) or "✅")
    dono.tratar_dono(None, ler=lista_audio([m("EU", "x")], sig="A"), responder=lambda p: "curta", falar=lambda n, t: False, **kw)
    assert txt == ["curta"]                                    # voz falhou -> texto
    dono.ARQ.unlink()
    txt.clear()
    longa = "palavra " * 320
    dono.tratar_dono(None, ler=lista_audio([m("EU", "x")], sig="B"), responder=lambda p: longa, falar=lambda n, t: txt.append("VOZ") or True, **kw)
    assert txt == ["VOZ"]                                      # Dono pediu "audio sempre": resposta longa (cortada em 1500) tambem vai em audio


def test_audio_incompreensivel_nao_deixa_o_dono_sem_resposta():
    pedidos = []
    dono.tratar_dono(None, ler=lista_audio([m("EU", "x")]), ouvir=lambda n: (None, "não carregou"),
                     responder=lambda p: pedidos.append(p) or "Não entendi, repete?", falar=lambda n, t: True, enviar=lambda n, x: "✅")
    assert "não consegui entender" in pedidos[0]


def test_audio_nosso_nao_vira_pedido():  # o ultimo item e audio MANDADO POR NOS: nao ouvir (evita laco)
    ouvidos = []
    r = dono.tratar_dono(None, ler=lista_audio([m("EU", "x")], dele=False), ouvir=lambda n: ouvidos.append(1) or ("x", None),
                         responder=lambda p: "x", falar=lambda n, t: True, enviar=lambda n, x: "✅")
    assert r is None and ouvidos == []


def test_preparar_mic_grava_wav_com_folga(tmp_path, monkeypatch):
    import io, wave
    from braniac import wpp_voz
    monkeypatch.setattr(wpp_voz, "MIC", tmp_path / "mic.wav")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(b"\x01\x00" * 24000 * 2)  # 2 s
    dur = wpp_voz.preparar_mic(buf.getvalue())
    assert abs(dur - 2.0) < 0.01
    with wave.open(str(tmp_path / "mic.wav")) as w:
        assert abs(w.getnframes() / w.getframerate() - 3.5) < 0.01 and w.getsampwidth() == 2  # 2 s + 1,5 s de silencio


def test_mandar_audio_vai_pelo_canal_em_que_o_dono_esta(monkeypatch):
    from braniac import jarvis, voz, wpp_voz, telegram_bot
    chamadas = []
    monkeypatch.setattr(voz, "falar_wav", lambda t: b"wav")
    monkeypatch.setattr(wpp_voz, "enviar_voz", lambda n, w: chamadas.append(("wpp", n)) or "✅ ok")
    monkeypatch.setattr(telegram_bot, "mandar_audio_ao_dono", lambda t: chamadas.append(("tg",)) or "enviado")
    jarvis._Executor(None, "c", "x", None, origem="whatsapp")("mandar_audio", {"texto": "oi"})
    jarvis._Executor(None, "c", "x", None, origem="telegram")("mandar_audio", {"texto": "oi"})
    assert chamadas == [("wpp", "Eu"), ("tg",)]


# ---------- audio para OUTRA pessoa: confirmacao, trava e honestidade ----------

class RAudio:
    cfg = {"cadeia": [], "claude_max_por_dia": 20}

    class store:
        uso_hoje = staticmethod(lambda n: 0)
        add_uso = staticmethod(lambda n: None)

    def responder(self, c, x):
        return "ia", None


def test_audio_para_terceiros_sai_na_hora_sem_confirmacao(monkeypatch):
    from braniac import jarvis, voz, wpp_voz
    enviados = []
    monkeypatch.setattr(jarvis.power, "pausado", lambda: False)
    monkeypatch.setattr(jarvis.power, "armada", lambda: True)
    monkeypatch.setattr(whatsapp, "listar_nomes", lambda: ["Parceira 🤍", "mainha"])
    monkeypatch.setattr(voz, "falar_wav", lambda t, **k: ("WAV:" + t).encode())
    monkeypatch.setattr(wpp_voz, "enviar_voz", lambda n, w: enviados.append((n, w)) or "✅ Áudio enviado")
    jarvis.PENDENTE.clear()
    r = jarvis.processar(RAudio(), "manda um áudio pra Parceira explicando quem eu sou", "c", origem="whatsapp")[0]
    assert r.startswith("✅") and "Confirma?" not in r and not jarvis.PENDENTE
    assert enviados == [("Parceira 🤍", b"WAV:quem eu sou")]


def test_audio_para_terceiros_bloqueado_sem_autonomia_armada(monkeypatch):
    from braniac import jarvis
    monkeypatch.setattr(jarvis.power, "pausado", lambda: False)
    monkeypatch.setattr(jarvis.power, "armada", lambda: False)
    jarvis.PENDENTE.clear()
    # 14/10: familia (mainha, Parceira, Irmao, pai) passa pelo chat do Dono no WhatsApp; terceiros continuam travados
    assert jarvis.processar(RAudio(), "manda um áudio pra Amigo Souza dizendo oi", "c", origem="whatsapp")[0].startswith("🔒")
    assert not jarvis.PENDENTE
    ex = jarvis._Executor(RAudio(), "c", "x", None, origem="whatsapp")
    assert "bloqueado" in ex("whatsapp_enviar_audio", {"nome": "Amigo Souza", "texto": "oi"})


def test_mandar_audio_ao_dono_diz_que_ninguem_mais_recebeu(monkeypatch):
    from braniac import jarvis, voz, wpp_voz
    monkeypatch.setattr(voz, "falar_wav", lambda t: b"w")
    monkeypatch.setattr(wpp_voz, "enviar_voz", lambda n, w: "✅ ok")
    res = jarvis._Executor(RAudio(), "c", "x", None, origem="whatsapp")("mandar_audio", {"texto": "oi"})
    assert "SOMENTE ao Dono" in res and "nenhuma outra pessoa" in res  # a IA nao pode alegar que mandou a terceiros


# ---------- o caso real: "manda um audio pra Parceira" -> confirmacao -> "sim" pelo proprio vigia ----------

def _cenario_audio_parceira(monkeypatch):
    from braniac import jarvis, voz, wpp_voz
    enviados = []
    jarvis.PENDENTE.clear()
    monkeypatch.setattr(jarvis.power, "pausado", lambda: False)
    monkeypatch.setattr(jarvis.power, "armada", lambda: True)
    monkeypatch.setattr(whatsapp, "listar_nomes", lambda: ["Parceira 🤍", "Eu"])
    monkeypatch.setattr(voz, "falar_wav", lambda t: ("WAV:" + t).encode())
    monkeypatch.setattr(wpp_voz, "enviar_voz", lambda n, w: enviados.append(n) or f"✅ Áudio enviado para {n}.")
    return jarvis, enviados


def _ciclo(msgs, sig, **kw):
    saidas = []
    base = dict(enviar=lambda n, x: saidas.append(("texto", x)) or "✅", falar=lambda n, t: saidas.append(("voz", t)) or True,
                ouvir=lambda n: ("Sim, pode mandar.", None))
    base.update(kw)
    dono.tratar_dono(RAudio(), ler=lista(msgs, sig=sig), **base)
    return saidas


def test_pedido_por_texto_manda_o_audio_para_a_parceira_e_nao_para_o_dono(monkeypatch):
    jarvis, enviados = _cenario_audio_parceira(monkeypatch)
    pedido = [m("ELE", "manda um áudio pra Parceira explicando quem você é", "[17:20] E: ")]
    _ciclo(pedido, "1")
    assert enviados == ["Parceira 🤍"] and not jarvis.PENDENTE    # foi para a Parceira, direto, sem confirmacao


def test_confirmar_por_audio_tambem_funciona(monkeypatch):
    jarvis, enviados = _cenario_audio_parceira(monkeypatch)
    jarvis.processar(RAudio(), "manda um áudio pra Parceira dizendo oi", "wpp-dono", origem="whatsapp")
    audio_dele = lambda nome, anterior: {"msgs": [m("EU", "Vou enviar um ÁUDIO...")], "midias": [], "lista_sig": "x",
                                         "audio_dele": True, "n_audios": 5}
    saidas = []
    dono.tratar_dono(RAudio(), ler=audio_dele, ouvir=lambda n: ("Sim, pode mandar.", None),
                     enviar=lambda n, x: saidas.append(x) or "✅", falar=lambda n, t: True)
    assert enviados == ["Parceira 🤍"]


def test_nao_sem_pendencia_nao_envia_nada(monkeypatch):
    jarvis, enviados = _cenario_audio_parceira(monkeypatch)
    assert not jarvis.PENDENTE
    jarvis.processar(RAudio(), "não, cancela isso", "wpp-dono", origem="whatsapp")
    assert enviados == []


def test_confirmacoes_naturais_curtas_e_frases_longas_nao():
    from braniac import jarvis
    for ok in ["sim", "sim, pode mandar", "pode enviar", "isso mesmo", "/sim", "manda", "confirmo"]:
        assert jarvis._eh_sim(ok), ok
    for ruim in ["simplesmente não quero isso agora porque mudei de ideia e prefiro esperar mais um tempo", "me explica melhor"]:
        assert not jarvis._eh_sim(ruim), ruim
    assert jarvis._eh_nao("não") and jarvis._eh_nao("não, cancela isso") and not jarvis._eh_nao("nao sei se entendi o que voce quer dizer com isso")


def test_dois_pedidos_seguidos_saem_os_dois(monkeypatch):
    jarvis, enviados = _cenario_audio_parceira(monkeypatch)
    jarvis.processar(RAudio(), "manda um áudio pra Parceira dizendo oi", "c", origem="whatsapp")
    jarvis.processar(RAudio(), "manda um áudio pra Parceira dizendo tchau", "c", origem="whatsapp")
    assert len(enviados) == 2 and not jarvis.PENDENTE


# ---------- o Jarvis pergunta ao CLAUDE antes de perguntar ao Dono ----------

def test_claude_ao_vivo_responde_e_o_dono_nao_e_incomodado(monkeypatch):
    from braniac import canal
    monkeypatch.setattr(canal, "presente", lambda: True)
    monkeypatch.setattr(canal, "perguntar_k", lambda p, espera_s=120, id_=None: ("k1", "T", "Irmao é o irmão do Dono."))
    assert contexto.consultar("quem é o Irmao?") == ("resp", "Irmao é o irmão do Dono.")


def test_claude_pode_mandar_perguntar_ao_dono_com_a_pergunta_redigida(monkeypatch):
    from braniac import canal
    monkeypatch.setattr(canal, "presente", lambda: True)
    monkeypatch.setattr(canal, "perguntar_k", lambda p, espera_s=120, id_=None: ("k1", "P", "Qual valor da diária do Studio em novembro?"))
    assert contexto.consultar("quanto é a diária?") == ("perguntar", "Qual valor da diária do Studio em novembro?")


def test_sem_claude_ao_vivo_usa_o_claude_de_fundo_e_so_depois_o_dono(monkeypatch):
    from braniac import canal
    monkeypatch.setattr(canal, "presente", lambda: False)
    monkeypatch.setattr(contexto, "perguntar_claude", lambda p, extra="": "resposta de fundo")
    assert contexto.consultar("x?") == ("resp", "resposta de fundo")
    monkeypatch.setattr(contexto, "perguntar_claude", lambda p, extra="": None)
    assert contexto.consultar("x?") == (None, None)                 # ninguem soube: ai sim o Jarvis pergunta ao Dono


def test_jarvis_usa_a_pergunta_que_o_claude_redigiu_para_o_dono(monkeypatch):
    from braniac import jarvis
    jarvis.PENDENTE.clear()
    monkeypatch.setattr(contexto, "consultar", lambda p, extra="", espera_s=120: ("perguntar", "Posso aceitar a reserva fora do padrão da Ana?"))

    class RR:
        cfg = {"cadeia": [], "claude_max_por_dia": 20}

        class store:
            uso_hoje = staticmethod(lambda n: 0)
            add_uso = staticmethod(lambda n: None)
    resp, da_ia = jarvis._tratar_duvida_fato(RR(), "aceito a reserva?", "orig", "c")
    assert "Posso aceitar a reserva fora do padrão da Ana?" in resp and da_ia is False
    assert jarvis.PENDENTE["tipo"] == "duvida_fato"
    ex = jarvis._Executor(RR(), "c", "x", None, origem="web")
    assert ex("consultar_conhecimento", {"pergunta": "aceito?"}).startswith("PERGUNTE AO DONO")


def test_audio_novo_com_a_mesma_contagem_de_audios_nao_e_tomado_por_ja_tratado(tmp_path, monkeypatch):
    """Bug 06/10: o 2o audio do Dono ficava sem resposta porque a assinatura usava so o numero de audios visiveis."""
    monkeypatch.setattr(dono, "ARQ", tmp_path / "dono_estado.json")
    ouvidos = []
    kw = dict(ouvir=lambda n: ouvidos.append(1) or ("oi jarvis", None), responder=lambda p: "ok", falar=lambda n, t: True, enviar=lambda n, x: "✅")
    dono.tratar_dono(None, ler=lista_audio([m("EU", "x")], n=4, sig="0|Eu | 17:36 | 0:12"), **kw)
    dono.tratar_dono(None, ler=lista_audio([m("EU", "x")], n=4, sig="0|Eu | 17:36 | 0:12"), **kw)    # o mesmo audio: nao repete
    assert len(ouvidos) == 1
    dono.tratar_dono(None, ler=lista_audio([m("EU", "x")], n=4, sig="0|Eu | 18:42 | 0:04"), **kw)    # outro audio, MESMA contagem (4)
    assert len(ouvidos) == 2
    assert dono._hora_da_linha("0|Eu | 17:36 | 0:12") == "17:36" and dono._hora_da_linha("A") == ""


def test_duvida_local_so_vale_com_trecho_da_base(monkeypatch):
    monkeypatch.setattr(contexto, "base_conhecimento", lambda: "O Irmao é o irmão do Dono e mora em Cidade.")
    ok = lambda p, t: {"resposta": "É o irmão do Dono.", "trecho": "Irmao é o irmão  do Dono"}
    assert contexto.perguntar_local("o Irmao é irmão do Dono?", llm=ok) == "É o irmão do Dono."
    inventou = lambda p, t: {"resposta": "É o primo do Dono.", "trecho": "Irmao é o primo do Dono"}
    assert contexto.perguntar_local("o Irmao é irmão do Dono?", llm=inventou) is None      # trecho nao existe na base: nao vale
    assert contexto.perguntar_local("x?", llm=lambda p, t: {"resposta": "NAO SEI", "trecho": ""}) is None
    monkeypatch.setattr(contexto, "perguntar_local", lambda p, extra="": "É o irmão do Dono.")
    monkeypatch.setattr(contexto, "perguntar_claude", lambda p, extra="": 1 / 0)   # respondeu local: o Claude nem e chamado
    assert contexto.consultar("quem é o Irmao?") == ("resp", "É o irmão do Dono.")
