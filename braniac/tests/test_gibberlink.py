# -*- coding: utf-8 -*-
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from braniac import atender, contexto, gibberlink as gl, whatsapp


def test_deteccao_e_aperto_de_mao():
    assert gl.observar("Pousada X", ["Olá! Sou a assistente virtual da Pousada X."]) == "oferecer"
    gl.marcar_oferecido("Pousada X")
    assert gl.observar("Pousada X", ["GL1 OK"]) == "ativo"
    assert gl.ativo("Pousada X")
    assert gl.observar("Pousada X", ["GL1 ask txt=tem vaga?"]) == "ativo"


def test_humano_nao_entra_e_sai_se_pedir_fala_normal():
    assert gl.observar("Fulano", ["oi, quero saber do quarto"]) == "humano"
    assert gl.observar("Parceira", ["sou uma IA kkk GL1 OK"]) == "humano"   # humano conhecido nunca
    gl.observar("Bot Y", ["[GL1?] sou um assistente virtual"])
    assert gl.ativo("Bot Y")                       # ele convidou: ja falamos GL1
    assert gl.observar("Bot Y", ["não entendi, fala normal"]) == "humano"


def test_convite_sem_aceite_volta_a_humano_e_nao_reoferece():
    gl.observar("Loja Z", ["Atendimento automático. Digite 1 para vendas"])
    gl.marcar_oferecido("Loja Z")
    assert gl.observar("Loja Z", ["quero comprar"]) == "oferecido"
    assert gl.observar("Loja Z", ["alô?"]) == "humano"
    assert gl.observar("Loja Z", ["sou um assistente virtual"]) == "suspeita"   # recusado ha pouco: nao oferece de novo


def test_quadro_ida_e_volta():
    q = gl.codificar("ask", txt="vaga 12;14/out?", qtd=2)
    assert q.startswith("GL1 ask ") and "%3B" in q
    op, c = gl.decodificar(q)
    assert op == "ask" and c["txt"] == "vaga 12;14/out?" and c["qtd"] == "2"
    assert gl.legivel(q).startswith("🤖 [pergunta] vaga 12;14/out?")
    assert gl.legivel("texto comum") == "texto comum"


def test_compactar_tira_cortesia_e_identifica_no_primeiro():
    q = gl.compactar("Oi! Aqui é o Jarvis, assistente do Dono. Temos 2 vagas. Fico à disposição!")
    assert q == "GL1 ans txt=Temos 2 vagas"
    q2 = gl.compactar("Qual a data?", de=gl.QUEM_SOMOS)
    op, c = gl.decodificar(q2)
    assert op == "ask" and c["de"] == gl.QUEM_SOMOS
    ok, _ = atender.validar_resposta(q2)
    assert ok


def test_atender_em_modo_gl1_manda_quadro_por_texto(monkeypatch):
    gl.observar("Hotel Bot", ["GL1 OK"])
    contexto.marcar_apresentado("Hotel Bot")
    it = {"nome": "Hotel Bot", "nl": 1, "msgs": ["GL1 ask txt=tem vaga dia 12?"], "ctx": [], "autores": set(), "midia": False}
    monkeypatch.setattr(atender, "coletar", lambda *a, **k: [it])
    vistos, enviados = {}, []
    def decidir(i, flags, espera_s=150):
        vistos["flags"], vistos["msgs"] = flags, list(i["msgs"])
        return ("E", "Oi! Sim, temos vaga no dia 12. Abraços!")
    monkeypatch.setattr(atender, "decidir", decidir)
    monkeypatch.setattr(atender.revisao, "decidir_com_revisao", lambda it, f, dec, e: (dec[0], dec[1], ""))
    monkeypatch.setattr(whatsapp, "enviar", lambda n, t: enviados.append((n, t)) or "✅ enviado")
    atender.atender(relatar=False)
    assert "M" in vistos["flags"] and vistos["msgs"][0].startswith("🤖 [pergunta]")
    assert enviados == [("Hotel Bot", "GL1 ans txt=Sim, temos vaga no dia 12")]


def test_atender_manda_convite_quando_suspeita(monkeypatch):
    it = {"nome": "Pousada Bot", "nl": 1, "msgs": ["Olá, sou um assistente virtual. Em que posso ajudar?"], "ctx": [], "autores": set(), "midia": False}
    monkeypatch.setattr(atender, "coletar", lambda *a, **k: [it])
    monkeypatch.setattr(atender, "decidir", lambda i, f, e=150: ("E", "Queria saber se vocês aceitam pet."))
    monkeypatch.setattr(atender.revisao, "decidir_com_revisao", lambda it, f, dec, e: (dec[0], dec[1], ""))
    monkeypatch.setattr(contexto, "deve_falar", lambda *a: False)
    enviados = []
    monkeypatch.setattr(whatsapp, "enviar", lambda n, t: enviados.append(t) or "✅ enviado")
    atender.atender(relatar=False)
    assert enviados and enviados[0].endswith(gl.CONVITE) and "Jarvis" in enviados[0]
    assert gl.estado("Pousada Bot") == "oferecido"


def test_mede_economia_e_resumo(monkeypatch):
    test_atender_em_modo_gl1_manda_quadro_por_texto(monkeypatch)
    m = gl.metricas()
    assert m["quadros"] == 1 and m["audios_evitados"] == 1 and m["chars_gl1"] < m["chars_natural"]
    r = gl.resumo()
    assert "1 quadros enviados" in r and "ativo: 1" in r


def test_quadro_barrado_volta_para_texto_normal(monkeypatch):
    gl.observar("Bot W", ["GL1 OK"])
    contexto.marcar_apresentado("Bot W")
    it = {"nome": "Bot W", "nl": 1, "msgs": ["GL1 ask txt=preco?"], "ctx": [], "autores": set(), "midia": False}
    monkeypatch.setattr(atender, "coletar", lambda *a, **k: [it])
    monkeypatch.setattr(atender, "decidir", lambda i, f, e=150: ("E", "Temos vaga."))
    monkeypatch.setattr(atender.revisao, "decidir_com_revisao", lambda it, f, dec, e: (dec[0], dec[1], ""))
    reais = atender.validar_resposta
    monkeypatch.setattr(atender, "validar_resposta", lambda t: (False, "teste") if t.startswith("GL1") else reais(t))
    enviados = []
    monkeypatch.setattr(whatsapp, "enviar", lambda n, t: enviados.append(t) or "✅ enviado")
    monkeypatch.setattr(contexto, "deve_falar", lambda *a: False)
    atender.atender(relatar=False)
    assert enviados == ["Temos vaga."] and gl.metricas() == {}
