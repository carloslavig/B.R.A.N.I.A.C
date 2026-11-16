# -*- coding: utf-8 -*-
"""Prioridade do Jarvis: responder SEMPRE em audio, a nao ser que a pessoa peca por escrito."""
import pytest
from braniac import atender, contexto, dono, voz, whatsapp, wpp_voz


def m(d, t, c="[17:00, 01/10/2026] X: "):
    return {"d": d, "t": t, "c": c}


def lista(msgs, sig="1"):
    return lambda nome, anterior: None if sig == anterior else {"msgs": msgs, "midias": [], "lista_sig": sig}


# ---------- regra central ----------

def test_padrao_e_audio_e_so_vira_texto_quando_pedem():
    assert contexto.preferencia("Maria") == "voz" and contexto.deve_falar("Maria", "Tudo certo, pode vir amanhã.")
    contexto.atualizar_preferencia("Maria", "pode me responder por escrito?")
    assert contexto.preferencia("Maria") == "texto" and not contexto.deve_falar("Maria", "Tudo certo.")
    assert contexto.deve_falar("Joao", "Tudo certo.")                       # so a Maria pediu texto
    contexto.atualizar_preferencia("Maria", "pode voltar a mandar áudio")  # e pode desfazer
    assert contexto.deve_falar("Maria", "Tudo certo.")


def test_pedir_para_mandar_audio_a_alguem_nao_muda_a_preferencia():
    contexto.atualizar_preferencia("Dono", "manda um áudio pra Parceira dizendo oi")
    assert contexto.preferencia("Dono") == "voz"


@pytest.mark.parametrize("resp", ["Confirma? Responda /sim ou /nao", "Veja https://site.com/x", "A chave é 12345678901",
                                  "Vou enviar «oi» para a Parceira", "palavra " * 320])
def test_o_que_precisa_ser_lido_vai_em_texto(resp):
    assert not contexto.deve_falar("Dono", resp)


def test_fala_limpa_emoji_markdown_e_link():
    assert voz.limpar_para_fala("**Oi!** ✅ Veja https://x.com agora 🤖\n- item um") == "Oi. Veja agora item um"   # a exclamacao vira ponto (voz mais seria)


# ---------- vigia do Dono (WhatsApp) ----------

def _rodar_dono(msgs, resposta="Claro, já resolvo isso.", da_ia=True, sig="1"):
    voz_env, txt_env = [], []
    dono.tratar_dono(None, ler=lista(msgs, sig),
                     responder=lambda p: resposta, falar=lambda n, t: voz_env.append(t) or True,
                     enviar=lambda n, x: txt_env.append(x) or "✅")
    return voz_env, txt_env


def test_dono_escreve_texto_e_recebe_audio():
    v, t = _rodar_dono([m("ELE", "como estão as reservas de hoje?")])
    assert v == ["Claro, já resolvo isso."] and t == []


def test_dono_pede_por_escrito_e_recebe_texto_ate_pedir_audio_de_novo():
    v, t = _rodar_dono([m("ELE", "me responde por escrito, por favor")], sig="1")
    assert v == [] and t == ["Claro, já resolvo isso."]
    v, t = _rodar_dono([m("ELE", "me responde por escrito, por favor"), m("EU", "x"), m("ELE", "e agora?")], sig="2")
    assert v == [] and len(t) == 1                                            # continua em texto
    v, t = _rodar_dono([m("ELE", "a"), m("EU", "x"), m("ELE", "pode voltar a mandar áudio")], sig="3")
    assert v == ["Claro, já resolvo isso."]                                   # voltou ao padrao


def test_confirmacao_e_link_no_vigia_sempre_em_texto():
    v, t = _rodar_dono([m("ELE", "manda um áudio pra Parceira")], resposta="Vou enviar para Parceira. Confirma? Responda /sim ou /nao", sig="9")
    assert v == [] and "Confirma?" in t[0]


def test_falha_do_audio_cai_em_texto_e_o_dono_nunca_fica_sem_resposta():
    txt = []
    dono.tratar_dono(None, ler=lista([m("ELE", "oi")]), responder=lambda p: "Oi, Dono!",
                     falar=lambda n, t: False, enviar=lambda n, x: txt.append(x) or "✅")
    assert txt == ["Oi, Dono!"]


# ---------- atendimento de terceiros ----------

@pytest.fixture
def envios(monkeypatch):
    saidas = []
    monkeypatch.setattr(whatsapp, "enviar", lambda n, x: saidas.append(("texto", n, x)) or f"✅ texto {n}")
    monkeypatch.setattr(voz, "falar_wav", lambda t, permitir_nuvem=True: ("WAV:" + t).encode())
    monkeypatch.setattr(wpp_voz, "enviar_voz", lambda n, w: saidas.append(("voz", n, w.decode())) or f"✅ Áudio enviado para {n}.")
    monkeypatch.setattr(atender.time, "sleep", lambda s: None)
    return saidas


def _atender(monkeypatch, msgs, resposta):
    item = {"nome": "Maria", "nl": 1, "msgs": msgs, "ctx": [], "autores": {"Maria"}, "midia": False}
    monkeypatch.setattr(atender, "coletar", lambda *a, **k: [item])
    monkeypatch.setattr(atender, "decidir", lambda it, fl, esp=0: ("E", resposta))
    return atender.atender(espaco_s=(0, 0), relatar=False)


def test_terceiros_recebem_audio_com_apresentacao(monkeypatch, envios):
    rel = _atender(monkeypatch, ["tem vaga?"], "Tem sim! Qual data?")
    assert envios == [("voz", "Maria", "WAV:" + contexto.abertura_padrao("Maria") + "Tem sim! Qual data?")]
    assert "(áudio)" in rel


def test_terceiro_que_pede_por_escrito_recebe_texto(monkeypatch, envios):
    rel = _atender(monkeypatch, ["pode escrever? não consigo ouvir áudio agora"], "Claro, escrevo sim. Qual data?")
    assert envios[0][0] == "texto" and "(texto)" in rel and contexto.preferencia("Maria") == "texto"


def test_terceiro_resposta_longa_ou_falha_do_audio_vai_em_texto(monkeypatch, envios):
    _atender(monkeypatch, ["tem vaga?"], "Tem sim, " + "muito " * 78)  # ~477 chars: passa na validacao (<=500), mas com a apresentacao passa de 500 -> texto
    assert envios[-1][0] == "texto"
    envios.clear()
    contexto.definir_preferencia("Maria", "voz")
    monkeypatch.setattr(wpp_voz, "enviar_voz", lambda n, w: "falhou o audio")
    _atender(monkeypatch, ["tem vaga?"], "Tem sim!")
    assert envios == [("texto", "Maria", "Tem sim!")]  # ja apresentada na rodada anterior; audio falhou -> texto


def test_prioridade_esta_no_dossie_e_no_prompt():
    import json
    from pathlib import Path
    assert "SEMPRE em ÁUDIO" in contexto.dossie_para("oi")
    cfg = json.loads((Path(__file__).resolve().parents[1] / "providers.json").read_text(encoding="utf-8-sig"))
    assert "FALADAS" in cfg["system"]


def test_avisos_assincronos_ao_dono_tambem_em_audio():
    v, t = [], []
    dono._avisar("Eu", "Terminei: tem 2 reservas novas hoje.", enviar=lambda n, x: t.append(x) or "✅", falar=lambda n, x: v.append(x) or True)
    assert v == ["Terminei: tem 2 reservas novas hoje."] and t == []
    v.clear()
    dono._avisar("Eu", "Veja https://site.com/painel", enviar=lambda n, x: t.append(x) or "✅", falar=lambda n, x: v.append(x) or True)
    assert v == [] and t == ["Veja https://site.com/painel"]          # link tem que ser lido
    t.clear()
    dono._avisar("Eu", "Pronto.", enviar=lambda n, x: t.append(x) or "✅", falar=lambda n, x: False)
    assert t == ["Pronto."]                                            # audio falhou -> texto


def test_todo_envio_de_resposta_no_whatsapp_passa_pela_regra_do_audio():
    """Os 3 caminhos de resposta no WhatsApp (vigia do Dono, aviso assincrono, atendimento de terceiros) usam contexto.deve_falar."""
    from pathlib import Path
    base = Path(dono.__file__).parent
    assert "deve_falar" in (base / "dono.py").read_text(encoding="utf-8")
    assert "deve_falar" in (base / "atender.py").read_text(encoding="utf-8")
    assert dono._avisar.__doc__ and "AUDIO" in dono._avisar.__doc__


# ---------- ouvir audio de terceiros + tratamento da mainha ----------

def _item(nome, msgs, audio=False):
    return {"nome": nome, "nl": len(msgs), "msgs": list(msgs), "ctx": [], "autores": {nome}, "midia": False, "audio_dele": audio}


def test_atendimento_ouve_o_audio_da_mainha_e_responde_em_audio(monkeypatch, envios):
    vistos = []
    item = _item("mainha", ["A nutricionista ligou"], audio=True)
    monkeypatch.setattr(atender, "coletar", lambda *a, **k: [item])
    monkeypatch.setattr(atender, "decidir", lambda it, fl, esp=0: vistos.append((list(it["msgs"]), fl)) or ("E", "Anotado, minha tia! Vou avisar o Dono agora."))
    rel = atender.atender(espaco_s=(0, 0), relatar=False, ouvir_audio=lambda n: ("o Juninho vem jantar amanhã", None))
    assert vistos[0][0] == ["A nutricionista ligou", "🎙 o Juninho vem jantar amanhã"]      # a transcricao chega ao decisor
    assert envios[0] == ("voz", "mainha", "WAV:" + contexto.abertura_padrao("mainha") + "Anotado, minha tia! Vou avisar o Dono agora.")
    assert envios[1][:2] == ("voz", "Eu") and "Oi, Dono" in envios[1][2] and "sua mãe" in envios[1][2] and "o Juninho vem jantar amanhã" in envios[1][2]   # prometeu avisar: o recado literal vai de verdade
    assert len(envios) == 2 and "(áudio)" in rel


def test_so_se_apresenta_uma_vez_a_mainha(monkeypatch, envios):
    contexto.marcar_apresentado("mainha")
    item = _item("mainha", ["oi"])
    monkeypatch.setattr(atender, "coletar", lambda *a, **k: [item])
    monkeypatch.setattr(atender, "decidir", lambda it, fl, esp=0: ("E", "Oi, minha tia! Tudo bem?"))
    atender.atender(espaco_s=(0, 0), relatar=False)
    assert envios == [("voz", "mainha", "WAV:Oi, minha tia! Tudo bem?")]


def test_audio_sensivel_e_respondido_e_incompreensivel_chega_com_a_flag_de_midia(monkeypatch, envios):
    decididos = []
    monkeypatch.setattr(atender, "decidir", lambda it, fl, esp=0: decididos.append(fl) or ("E", "ok"))
    monkeypatch.setattr(atender, "coletar", lambda *a, **k: [_item("Joao", [], audio=True)])
    rel = atender.atender(espaco_s=(0, 0), relatar=False, ouvir_audio=lambda n: ("me passa o pix e a senha do banco", None))
    assert envios and "NÃO respondi" not in rel and "S" in decididos[0]                # tema sensivel: responde normalmente
    monkeypatch.setattr(atender, "coletar", lambda *a, **k: [_item("Ana", [], audio=True)])
    atender.atender(espaco_s=(0, 0), relatar=False, ouvir_audio=lambda n: (None, "nao carregou"))
    assert "A" in decididos[-1]                                                      # incompreensivel: o decisor ve a flag de audio/midia


def test_dossie_ensina_a_tratar_a_mainha_como_minha_tia():
    d = contexto.dossie_para("mainha mandou um recado")
    assert "minha tia" in d and "NUNCA 'dona Mãe'" in d and "ÁUDIO" in d
    assert contexto.intro_para("mainha").startswith("Oi, minha tia!") and contexto.intro_para("Maria") is None


def test_so_a_mae_e_minha_tia_os_outros_pelo_nome_salvo_no_whatsapp():
    assert contexto.primeiro_nome("Amigo Souza 🌝") == "Amigo" and contexto.primeiro_nome("Paula ✨ Bruna") == "Paula"
    assert contexto.primeiro_nome("+55 86 9000-0003") is None and contexto.primeiro_nome("(11) 99999") is None
    assert contexto.abertura_padrao("mainha").startswith("Oi, minha tia!")
    assert contexto.abertura_padrao("Amigo Pereira Fresco Da Silva").startswith("Oi, Amigo! Eu sou o Jarvis")
    assert contexto.abertura_padrao("+55 66 9000-0001").startswith("Oi! Eu sou o Jarvis")
    for outro in ("Maria", "Eduarda", "Paula ✨ Bruna", "Asaas"):
        assert "minha tia" not in contexto.abertura_padrao(outro)
    d = contexto.dossie_para("quem é você? sou programador")
    assert "SÓ a mãe" in d and "Whisper" in d                # o dossie manda explicar o Braniac a quem e tecnico


def test_resposta_tecnica_de_ate_500_caracteres_sai_em_audio_para_terceiros(monkeypatch, envios):
    item = _item("Amigo Pereira Fresco Da Silva", ["Quem é você? Se apresente."])
    monkeypatch.setattr(atender, "coletar", lambda *a, **k: [item])
    longa = "Sou o Jarvis. " + "O Braniac roteia as conversas por modelos gratuitos e depois um modelo local. " * 5  # ~420 chars
    monkeypatch.setattr(atender, "decidir", lambda it, fl, esp=0: ("E", longa.strip()))
    atender.atender(espaco_s=(0, 0), relatar=False)
    assert envios and envios[0][0] == "voz"


# ---------- regras de tom e escada de duvidas (decisao do Dono, 01/10) ----------

def test_toda_abertura_explica_quem_e_o_jarvis_e_nunca_diz_ocupado():
    for chat in ("Maria", "mainha", "Parceira 🤍", "+55 66 9000-0001", "Amigo Souza 🌝"):
        a = contexto.abertura_padrao(chat)
        assert "Jarvis" in a and "assistente de inteligência artificial do Dono" in a and "anoto os recados" in a, chat
        assert not atender.OCUPADO.search(a), chat


@pytest.mark.parametrize("frase", ["Ele está ocupado agora", "O Dono não está disponível", "ele tá off", "ele está indisponível",
                                   "Dono está sem tempo", "Ele não pode atender agora"])
def test_nunca_usa_o_dono_como_desculpa(frase):
    ok, motivo = atender.validar_resposta(frase + ", mas anoto seu recado.")
    assert not ok and "ocupado" in motivo


def test_codigo_P_leva_a_pergunta_exata_ao_dono(monkeypatch, envios):
    item = _item("Ana", ["quanto fica 3 diarias?"])
    atender.memoria.registrar_msg("Ana", "C", "Oi, Ana! Eu sou o Jarvis.")      # contato ja conhecido
    monkeypatch.setattr(atender, "coletar", lambda *a, **k: [item])
    monkeypatch.setattr(atender, "decidir", lambda it, fl, esp=0: ("P", "A Ana quer o valor de 3 diárias no Studio: qual preço passo a ela?"))
    rel = atender.atender(espaco_s=(0, 0), relatar=False)
    assert len(envios) == 1 and envios[0][:2] == ("voz", "Eu") and "Oi, Dono" in envios[0][2] and "Ana" in envios[0][2] and "quanto fica 3 diarias?" in envios[0][2]   # a Ana nao recebe nada; o Dono recebe o recado literal
    assert "A Ana quer o valor de 3 diárias no Studio: qual preço passo a ela?" in rel


def test_sites_oficiais_podem_ser_citados_mas_link_qualquer_nao():
    from braniac import atender
    assert atender.validar_resposta("Entra no registrato.bcb.gov.br com o gov.br dele")[0]
    assert not atender.validar_resposta("Acessa https://golpe.com/x")[0]
    assert not atender.validar_resposta("Manda pro 11999998888")[0]


def test_audio_da_layla_volta_transcrito_em_texto(monkeypatch):
    item = {"nome": "Layla", "nl": 1, "msgs": ["[AUDIO]"], "ctx": [], "autores": {"Layla"}, "midia": True, "audio_dele": True}
    monkeypatch.setattr(atender, "coletar", lambda *a, **k: [item])
    enviados = []
    monkeypatch.setattr(atender.whatsapp, "enviar", lambda n, t: enviados.append((n, t)) or "✅ ok")
    monkeypatch.setattr(atender.whatsapp, "pendente_remover", lambda n: None)
    monkeypatch.setattr(atender, "decidir", lambda *a, **k: pytest.fail("nao deve decidir: so devolve a transcricao"))
    atender.atender(espaco_s=(0, 0), relatar=False, ouvir_audio=lambda n: ("o cliente quer 10 esfihas", None))
    assert enviados == [("Layla", "Transcrição do seu áudio:\n\no cliente quer 10 esfihas")]


def test_ouvir_falhou_nao_recarrega_o_whatsapp_de_novo_por_20_min(monkeypatch, envios):
    atender.AUDIO_FALHOU.clear()
    chamadas = []
    monkeypatch.setattr(atender, "decidir", lambda it, fl, esp=0: ("E", "ok"))
    monkeypatch.setattr(atender, "coletar", lambda *a, **k: [_item("Bia", [], audio=True)])
    ouvir = lambda n: chamadas.append(n) or (None, "O WhatsApp não voltou a carregar.")
    atender.atender(espaco_s=(0, 0), relatar=False, ouvir_audio=ouvir)
    atender.atender(espaco_s=(0, 0), relatar=False, ouvir_audio=ouvir)
    assert chamadas == ["Bia"]                       # a 2a vez nao recarrega a pagina (o pai travava o atendimento de todos)
    atender.AUDIO_FALHOU.clear()
