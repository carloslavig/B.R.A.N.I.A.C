# -*- coding: utf-8 -*-
import pytest
from braniac import escuta


def nova(respostas=None):
    falas = []
    e = escuta.Escuta(falar=falas.append, responder=(lambda t: (respostas or {}).get(t, "resposta de teste")), abrir=lambda: None)
    e.estado = "dormindo"
    return e, falas


@pytest.mark.parametrize("frase", [
    "Jarvis, tá acordado?", "jarvis ta acordado", "Jarvis, está acordado?", "Jarves, tá acordado", "Garvis tá acordado?",
    "jarvis acorda", "Jarvis, você tá me ouvindo?", "ei jarvis, tá aí? acorde",
])
def test_frases_que_acordam(frase):
    e, falas = nova()
    e.tratar_frase(frase)
    assert e.estado == "acordado" and falas and "Estou acordado, senhor. Em que posso te ajudar?" == falas[0]


@pytest.mark.parametrize("frase", [
    "bom dia pessoal", "o dono tá acordado?", "tá acordado", "vamos jantar hoje à noite", "jarvis", "o jarvis é legal",
])
def test_frases_que_nao_acordam(frase):
    e, falas = nova()
    e.tratar_frase(frase)
    assert e.estado == "dormindo" and falas == []


def test_dormindo_nao_responde_a_conversa_alheia():
    e, falas = nova()
    assert e.tratar_frase("jarvis qual a capital da França") is None
    assert e.estado == "dormindo" and falas == []


def test_acordado_responde_falando_e_continua_ouvindo():
    e, falas = nova({"que horas são": "São três da tarde."})
    e.tratar_frase("Jarvis, tá acordado?")
    e.tratar_frase("que horas são")
    e.tratar_frase("e a previsão do tempo")
    assert e.estado == "acordado" and falas[1] == "São três da tarde." and falas[2] == "resposta de teste"


@pytest.mark.parametrize("frase", ["pode descansar, Jarvis", "Jarvis, pode descansar", "pode descansar", "Jarvis, pode dormir"])
def test_pode_descansar_volta_a_dormir(frase):
    e, falas = nova()
    e.tratar_frase("Jarvis, tá acordado?")
    e.tratar_frase(frase)
    assert e.estado == "dormindo" and "descansar" in falas[-1]
    e.tratar_frase("que horas são")
    assert len(falas) == 2           # dormindo de novo: nao responde


def test_alucinacoes_do_whisper_sao_ignoradas():
    e, falas = nova()
    e.tratar_frase("Jarvis, tá acordado?")
    for lixo in ("Tchau.", "Obrigado.", "Legendas pela comunidade Amara.org", "", "a"):
        e.tratar_frase(lixo)
    assert len(falas) == 1


def test_parada_nao_faz_nada():
    e, falas = nova()
    e.estado = "parada"
    e.tratar_frase("Jarvis, tá acordado?")
    assert falas == [] and e.estado == "parada"


def test_resposta_longa_e_cortada_e_link_nao_e_falado():
    e, falas = nova({"manda o link": "veja https://exemplo.com " + "palavra " * 200})
    e.tratar_frase("Jarvis, tá acordado?")
    e.tratar_frase("manda o link")
    assert "https://" not in falas[1] and len(falas[1]) <= 760 and "por escrito" in falas[1]


@pytest.mark.parametrize("frase", ["Pode descassar, Jarvis.", "pode descancar jarvis", "Jarvis, pode discansar", "pode descansa"])
def test_descansar_tolera_erros_do_whisper(frase):
    assert escuta.quer_descansar(frase), frase


@pytest.mark.parametrize("frase", ["que horas são", "vamos conversar sobre a esfiharia", "quanto custa a landing page", "descobri um erro"])
def test_frases_normais_nao_mandam_descansar(frase):
    assert not escuta.quer_descansar(frase), frase


def test_ao_acordar_abre_a_tela_de_voz_e_mostra_a_conversa():
    abertas = []
    falas = []
    e = escuta.Escuta(falar=falas.append, responder=lambda t: "São três da tarde.", abrir=lambda: abertas.append(1))
    e.estado = "dormindo"
    e.tratar_frase("Jarvis, tá acordado?")
    import time; time.sleep(0.2)
    assert abertas == [1] and falas[0] == "Estou acordado, senhor. Em que posso te ajudar?"
    e.tratar_frase("que horas são")
    d = e.estado_completo()
    papeis = [h[0] for h in d["historico"]]
    assert d["estado"] == "acordado" and ("u", "que horas são") in d["historico"] and ("j", "São três da tarde.") in d["historico"] and "s" in papeis
    e.tratar_frase("pode descansar, Jarvis")
    assert e.estado_completo()["estado"] == "dormindo" and e.historico[-1] == ("s", "Voltei a dormir.")


def test_amplificar_sobe_audio_fraco_sem_estourar():
    import numpy as np
    fraco = (np.sin(np.linspace(0, 200, 8000)) * 0.04 * 32768).astype(np.int16).tobytes()
    forte = escuta._amplificar(fraco)
    a = np.frombuffer(forte, dtype=np.int16)
    assert 0.6 <= np.abs(a).max() / 32768.0 <= 0.8
    silencio = np.zeros(1000, dtype=np.int16).tobytes()
    assert escuta._amplificar(silencio) == silencio          # nao amplifica ruido nulo
    muito_fraco = (np.ones(500) * 3).astype(np.int16).tobytes()
    assert np.abs(np.frombuffer(escuta._amplificar(muito_fraco), dtype=np.int16)).max() <= 3 * 40   # ganho limitado


def test_envelope_acompanha_o_volume_da_fala():
    import io, wave
    import numpy as np
    taxa = 24000
    alto = (np.sin(np.linspace(0, 3000, taxa // 2)) * 20000).astype(np.int16)      # 0,5 s alto
    baixo = (np.sin(np.linspace(0, 3000, taxa // 2)) * 2000).astype(np.int16)      # 0,5 s baixo
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(taxa)
        w.writeframes(np.concatenate([alto, baixo]).tobytes())
    env = escuta.envelope(buf.getvalue())
    assert len(env) == 20 and max(env) == 1.0 and env[2] > 0.9 and env[15] < 0.2


def test_estado_completo_traz_atividade_e_niveis():
    import time
    e, _ = nova()
    e.nivel = 0.01
    d = e.estado_completo()
    assert d["atividade"] == "idle" and 0.4 < d["entrada"] < 0.7 and d["fala"] == 0.0
    e._fala = {"ini": time.time() - 0.12, "env": [0.1, 0.2, 0.9, 0.3]}
    assert e.nivel_fala() == 0.9
    e._fala["ini"] = time.time() - 5
    assert e.nivel_fala() == 0.0       # passou do fim do audio


def test_acordado_e_a_janela_foi_fechada_a_frase_reabre_a_tela():
    abertas, falas = [], []
    e = escuta.Escuta(falar=falas.append, responder=lambda t: "resposta comum", abrir=lambda: abertas.append(1))
    e.estado = "dormindo"
    e.tratar_frase("Jarvis, tá acordado?")
    import time; time.sleep(0.2)
    assert abertas == [1]
    # a janela foi fechada, mas o Jarvis continua 'acordado': perguntar de novo reabre e cumprimenta (nao vira conversa comum)
    e.tratar_frase("Jarvis, tá acordado?")
    time.sleep(0.2)
    assert abertas == [1, 1]
    assert falas == [escuta.Escuta.SAUDACAO, escuta.Escuta.SAUDACAO] and "resposta comum" not in falas
    assert e.estado == "acordado"


def test_abrir_janela_nao_duplica_se_a_tela_ainda_esta_aberta(monkeypatch):
    import subprocess
    lancados = []
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: lancados.append(a))
    e = escuta.Escuta(falar=lambda t: None, responder=lambda t: "x")   # sem 'abrir' injetado: usa o caminho real
    escuta.ULTIMA_CONSULTA[0] = __import__("time").time()               # a tela acabou de consultar o estado: esta aberta
    e._abrir_janela()
    assert lancados == []
    escuta.ULTIMA_CONSULTA[0] = __import__("time").time() - 30          # faz 30 s que ninguem consulta: foi fechada
    e._abrir_janela()
    assert len(lancados) == 1 and any("--app=http://127.0.0.1:8765/voz" in str(x) for x in lancados[0][0])


def test_modo_da_tela_fica_salvo(tmp_path, monkeypatch):
    monkeypatch.setattr(escuta, "MODO_ARQ", tmp_path / "ui_voz.json")
    assert escuta.modo_tela() == "completo"
    escuta.definir_modo_tela("mini")
    assert escuta.modo_tela() == "mini"
    escuta.definir_modo_tela("completo")
    assert escuta.modo_tela() == "completo"


def test_no_modo_mini_acordar_mostra_so_o_orbe(tmp_path, monkeypatch):
    from braniac import orbe
    monkeypatch.setattr(escuta, "MODO_ARQ", tmp_path / "ui_voz.json")
    escuta.definir_modo_tela("mini")
    chamadas = []
    monkeypatch.setattr(orbe, "iniciar_processo", lambda: chamadas.append("orbe"))
    import subprocess
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: chamadas.append("chrome"))
    e = escuta.Escuta(falar=lambda t: None, responder=lambda t: "x")     # sem 'abrir' injetado: usa o caminho real
    monkeypatch.setattr(escuta, "_janela_voz", lambda: None)
    monkeypatch.setattr(escuta, "mostrar_janela", lambda h, maximizar=True: None)
    e._abrir_janela()
    assert chamadas == ["orbe"]
    e._abrir_janela(forcar=True)                                          # duplo clique no orbe: interface completa
    assert chamadas[-1] == "chrome"


def test_orbe_tem_o_tamanho_do_icone_de_rede_mais_4px():
    from braniac import orbe
    assert orbe.TAM_ICONE + orbe.EXTRA == 20 and 3 <= orbe.EXTRA <= 5


def test_duplo_clique_maximiza_e_traz_para_a_frente_a_janela_que_ja_existe(monkeypatch):
    mostradas = []
    monkeypatch.setattr(escuta, "_janela_voz", lambda: 4242)
    monkeypatch.setattr(escuta, "mostrar_janela", lambda h, maximizar=True: mostradas.append((h, maximizar)))
    import subprocess
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("ja existe: nao abre outra"))
    e = escuta.Escuta(falar=lambda t: None, responder=lambda t: "x")
    e._abrir_janela(forcar=True)       # duplo clique: maximiza
    e._abrir_janela()                  # acordar pela voz: so traz para a frente, sem mudar o tamanho
    assert mostradas == [(4242, True), (4242, False)]


def test_ja_rodando_detecta_o_orbe_pela_porta_trava_mesmo_com_fila_cheia():
    import socket
    from braniac import orbe
    livre = socket.socket(); livre.bind(("127.0.0.1", 0)); porta = livre.getsockname()[1]; livre.close()
    orbe.PORTA_TRAVA = porta              # porta de teste (a real pode estar com o orbe de verdade rodando)
    trava = socket.socket()
    trava.bind(("127.0.0.1", orbe.PORTA_TRAVA))
    trava.listen(1)                       # como o orbe real: escuta mas nunca atende
    try:
        for _ in range(5):                # varias consultas do vigia nao podem 'entupir' a deteccao
            c = socket.socket(); c.settimeout(0.2); c.connect_ex(("127.0.0.1", orbe.PORTA_TRAVA)); c.close()
        assert orbe.ja_rodando() is True
    finally:
        trava.close()
    assert orbe.ja_rodando() is False


def test_animacao_do_orbe_ao_falar_segue_o_volume_inteiro():
    import time
    e, _ = nova()
    e._fala = {"ini": time.time() - 0.12, "env": [0.1, 0.2, 1.0, 0.3]}
    assert escuta.ANIMACAO_FALA == 1.0 and e.estado_completo()["fala"] == 1.0


def test_perguntar_se_esta_acordado_com_o_orbe_minimizado_abre_a_tela_inteira(tmp_path, monkeypatch):
    import subprocess, time
    from braniac import orbe
    monkeypatch.setattr(escuta, "MODO_ARQ", tmp_path / "ui_voz.json")
    escuta.definir_modo_tela("mini")
    chamadas = []
    monkeypatch.setattr(orbe, "iniciar_processo", lambda: chamadas.append("orbe"))
    monkeypatch.setattr(subprocess, "Popen", lambda args, *a, **k: chamadas.append(("chrome", "--start-maximized" in args)))
    monkeypatch.setattr(escuta, "_janela_voz", lambda: None)
    monkeypatch.setattr(escuta, "mostrar_janela", lambda h, maximizar=True: None)
    e = escuta.Escuta(falar=lambda t: None, responder=lambda t: "x")      # sem 'abrir' injetado: caminho real
    e.estado = "dormindo"
    e.tratar_frase("Jarvis, tá acordado?")
    for _ in range(40):
        if chamadas:
            break
        time.sleep(0.1)
    assert ("chrome", True) in chamadas and "orbe" not in chamadas        # abriu a tela maximizada, nao so o orbe


def test_com_a_tela_ja_aberta_e_minimizada_a_frase_maximiza_e_traz_para_a_frente(monkeypatch):
    import time
    mostradas = []
    monkeypatch.setattr(escuta, "_janela_voz", lambda: 77)
    monkeypatch.setattr(escuta, "mostrar_janela", lambda h, maximizar=True: mostradas.append((h, maximizar)))
    e = escuta.Escuta(falar=lambda t: None, responder=lambda t: "x")
    e.estado = "dormindo"
    e.tratar_frase("Jarvis, tá acordado?")
    for _ in range(40):                      # a janela abre numa thread: espera ate 4 s (a suite inteira roda pesada)
        if mostradas:
            break
        time.sleep(0.1)
    assert mostradas == [(77, True)]


def test_dividir_em_frases_junta_curtas_e_respeita_o_maximo():
    partes = escuta.dividir_em_frases("Oi. Tudo bem? " + "Esta é uma frase razoavelmente longa para o teste. " * 8)
    assert partes[0].startswith("Oi. Tudo bem?") and all(len(p) <= 330 for p in partes) and len(partes) >= 2
    assert escuta.dividir_em_frases("Só uma frase") == ["Só uma frase"]


def test_depois_de_falar_o_jarvis_nao_fica_surdo(monkeypatch):
    # a estimativa de ruido NAO e mais zerada depois da resposta, e o piso inicial cabe na sua voz baixa (RMS ~0,01)
    import inspect
    fonte = inspect.getsource(escuta.Escuta._loop)
    assert "recentes.clear()" not in fonte and "else 0.0008" in fonte


def test_descansar_minimiza_a_janela(monkeypatch):
    chamadas = []
    monkeypatch.setattr(escuta, "_janela_voz", lambda: 1234)
    e = escuta.Escuta(None, falar=lambda t: None, responder=lambda t: "", abrir=lambda: None) if False else None
    import ctypes
    class U:
        def ShowWindow(self, h, c): chamadas.append((h, c))
    monkeypatch.setattr(ctypes, "windll", type("W", (), {"user32": U()})(), raising=False)
    escuta.Escuta._minimizar_janela(object.__new__(escuta.Escuta))
    assert chamadas == [(1234, 6)]


# ---- 15/11: chamados mais naturais, 'me mostra' e links ----
from braniac import mostrar


@pytest.mark.parametrize("frase", [
    "Jarvis, tá por aí?", "Jarvis, você tá aí?", "ô Jarvis", "oi Jarvis", "fala Jarvis", "e aí Jarvis", "Jarvis, tá na escuta?",
    "Jarvis, cadê você?", "Jarvis tá ligado?",
])
def test_chamados_naturais_acordam(frase):
    e, falas = nova()
    e.tratar_frase(frase)
    assert e.estado == "acordado" and falas[0] == e.SAUDACAO


@pytest.mark.parametrize("frase", ["o jarvis falou besteira", "o jarvis é legal", "oi pessoal", "fala sério", "cadê você menino"])
def test_chamado_no_meio_da_conversa_nao_acorda(frase):
    e, falas = nova()
    e.tratar_frase(frase)
    assert e.estado == "dormindo" and falas == []


@pytest.mark.parametrize("frase,url", [
    ("como tá a situação da esteira?", "/parceiro"),
    ("como tá o NexoDev?", "/sauraki?andar=nexodev"),
    ("como tá o nexo dev", "/sauraki?andar=nexodev"),
    ("como tá o time da esteira?", "/sauraki?andar=esteira"),
    ("me mostra o andar da esteira", "/sauraki?andar=esteira"),
    ("como tá a Fornalha?", "/sauraki?andar=marketing"),
    ("abre a claquete", "/sauraki?andar=cortes"),
    ("como tá a estreia do Parceiro?", "/parceiro"),
    ("como tá o Nexus Dev?", "/sauraki?andar=nexodev"),
])
def test_intencao_tela(frase, url):
    assert mostrar.intencao(frase)[0] == url


@pytest.mark.parametrize("frase", ["que horas são", "o parceiro ligou", "a esteira de casa quebrou", "manda o vídeo pro grupo"])
def test_sem_intencao_tela(frase):
    assert mostrar.intencao(frase) is None


def test_acordado_mostra_tela_sem_chamar_o_cerebro(monkeypatch):
    chamou = []
    e, falas = nova()
    e._responder_ext = lambda t: chamou.append(t) or "x"
    e.estado = "acordado"
    monkeypatch.setattr(mostrar, "TELAS", [(r"\bnexo ?dev\b", "/sauraki?andar=nexodev", lambda: "NexoDev: 3 de 9 agentes trabalhando agora.")])
    antes = mostrar.TELA["id"]
    e.tratar_frase("como tá o NexoDev?")
    assert chamou == [] and falas[-1].startswith("NexoDev: 3 de 9")
    assert mostrar.TELA["id"] == antes + 1 and e.estado_completo()["tela"]["url"] == "/sauraki?andar=nexodev"


def test_dormindo_pergunta_de_situacao_com_jarvis_acorda_e_mostra(monkeypatch):
    e, falas = nova()
    monkeypatch.setattr(mostrar, "TELAS", [(r"\besteira\b", "/parceiro", lambda: "Esteira do Parceiro: 41 de 50 vídeos prontos no lote.")])
    e.tratar_frase("Jarvis, como tá a esteira?")
    assert e.estado == "acordado" and falas == ["Esteira do Parceiro: 41 de 50 vídeos prontos no lote."]


@pytest.mark.parametrize("resposta,como", [("no whatsapp", "whatsapp"), ("manda no celular", "whatsapp"), ("pelo telegram", "telegram"),
                                           ("abre aqui", "aqui"), ("não, deixa", "nao")])
def test_escolha_do_link(resposta, como):
    assert mostrar.escolha(resposta) == como


def test_link_pergunta_e_manda_no_whatsapp(monkeypatch):
    enviados = []
    monkeypatch.setattr(mostrar, "_outbox", enviados.append)
    monkeypatch.setattr(mostrar, "_abrir_navegador", lambda u: pytest.fail("nao pode abrir navegador sozinho"))
    e, falas = nova({"abre o site da vaquinha": "Aqui está: https://vaquinha-exemplo.vercel.app."})
    e.estado = "acordado"
    e.tratar_frase("abre o site da vaquinha")
    assert "Isso é um link" in falas[-1] and "http" not in falas[-1]
    e.tratar_frase("manda no zap")
    assert enviados and "https://vaquinha-exemplo.vercel.app" in enviados[0] and "WhatsApp" in falas[-1]


def test_link_abre_aqui_no_navegador(monkeypatch):
    abertos = []
    monkeypatch.setattr(mostrar, "_abrir_navegador", abertos.append)
    e, falas = nova({"me passa o link do youtube": "https://youtube.com"})
    e.estado = "acordado"
    e.tratar_frase("me passa o link do youtube")
    e.tratar_frase("abre aqui no computador")
    assert abertos == ["https://youtube.com"] and e._links == []


def test_quero_falar_com_a_alma_troca_e_volta():
    e, falas = nova()
    e._alma = lambda t: "resposta da alma"
    e.tratar_frase("Jarvis, tá acordado?")
    e.tratar_frase("Jarvis, eu quero falar com a Alma")
    assert e.agente == "alma" and falas[-1] == escuta.ALMA_ENTRA
    e.tratar_frase("hoje o dia foi puxado")
    assert falas[-1] == "resposta da alma"          # quem responde e a Alma, nao o Jarvis
    e.tratar_frase("agora quero falar com o Jarvis")
    assert e.agente == "jarvis" and falas[-1] == escuta.JARVIS_VOLTA
    e.tratar_frase("que horas são")
    assert falas[-1] == "resposta de teste"


def test_descansar_e_acordar_devolvem_o_jarvis():
    e, falas = nova()
    e.tratar_frase("Jarvis, tá acordado?")
    e.tratar_frase("chama a Alma")
    assert e.agente == "alma"
    e.tratar_frase("pode descansar")
    assert e.agente == "jarvis" and e.estado == "dormindo"
