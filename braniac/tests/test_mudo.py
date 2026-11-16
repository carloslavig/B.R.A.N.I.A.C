# -*- coding: utf-8 -*-
"""MUDO do Jarvis (08/10/2026): para de falar em voz alta (texto continua), corta a fala na hora, comandos de voz e interruptor do WhatsApp."""
import threading, time
from braniac import escuta, mudo


def _escuta_acordada(falas):
    e = escuta.Escuta(falar=lambda t: falas.append(t), responder=lambda t: "resposta longa do Jarvis", abrir=lambda: None)
    e.estado = "acordado"
    return e


def test_padrao_nao_esta_mudo_e_whatsapp_desligado():
    est = mudo.estado()
    assert est["mudo"] is False and est["whatsapp_dono"] is False
    assert mudo.bloqueia_audio_dono() is False


def test_mutar_ate_desmutar_e_desmutar():
    mudo.mutar()
    assert mudo.ativo() and mudo.estado()["ate_desmutar"] and mudo.CORTAR.is_set()
    mudo.desmutar()
    assert not mudo.ativo() and not mudo.CORTAR.is_set()


def test_mutar_por_10_min_expira_sozinho():
    mudo.mutar(10)
    est = mudo.estado()
    assert est["mudo"] and not est["ate_desmutar"] and est["restante_min"] == 10
    assert not mudo.ativo(agora=time.time() + 11 * 60)
    mudo.desmutar()


def test_mudo_nao_fala_mas_o_texto_aparece():
    falas = []
    e = _escuta_acordada(falas)
    mudo.mutar()
    try:
        e.tratar_frase("qual a previsao do tempo hoje")
        assert falas == []                                       # nada saiu no alto-falante
        assert ("j", "resposta longa do Jarvis") in e.historico  # mas o texto esta na tela
    finally:
        mudo.desmutar()
    e.tratar_frase("qual a previsao do tempo hoje")
    assert falas == ["resposta longa do Jarvis"]                 # desmutado: volta a falar


def test_comandos_de_voz_mutam_e_desmutam():
    falas = []
    e = _escuta_acordada(falas)
    for frase in ("Jarvis, silêncio", "cala a boca", "Mudo.", "para de falar"):
        mudo.desmutar()
        assert e.tratar_frase(frase) is None
        assert mudo.ativo(), frase
    assert falas == []                       # mutar nao fala nada
    e.tratar_frase("pode falar")
    assert not mudo.ativo()


def test_pode_falar_sem_estar_mudo_e_conversa_normal():
    assert mudo.comando("pode falar") is None
    assert mudo.comando("silencio") == "mutar"
    assert mudo.comando("hoje o silencio da casa estava estranho, me conta uma historia") is None


def test_dormindo_so_muta_se_chamar_o_jarvis():
    e = escuta.Escuta(falar=lambda t: None, responder=lambda t: "x", abrir=lambda: None)
    e.estado = "dormindo"
    e.tratar_frase("silencio")               # alguem na sala falou 'silencio': nao e com ele
    assert not mudo.ativo()
    e.tratar_frase("Jarvis, silêncio")
    assert mudo.ativo()
    mudo.desmutar()


def test_mutar_corta_a_fala_em_andamento(monkeypatch):
    tocando, cortada = threading.Event(), []

    class WinsoundFalso:
        SND_FILENAME, SND_ASYNC, SND_MEMORY = 1, 2, 4
        @staticmethod
        def PlaySound(som, flags):
            if som is None:
                cortada.append(True)
            else:
                tocando.set()

    import io, wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(b"\0\0" * 8000 * 30)   # 30 s de audio
    mudo.desmutar()
    t0 = time.time()
    th = threading.Thread(target=lambda: cortada.append(escuta._tocar_interrompivel(buf.getvalue(), WinsoundFalso)))
    th.start()
    assert tocando.wait(2)
    mudo.mutar()
    th.join(3)
    assert not th.is_alive() and time.time() - t0 < 3     # parou na hora, nao esperou os 30 s
    assert cortada == [True, True]                         # PlaySound(None) chamado + devolveu 'cortada'
    mudo.desmutar()


def test_interruptor_whatsapp_so_vale_com_mudo_ativo():
    mudo.definir_whatsapp_dono(True)
    assert not mudo.bloqueia_audio_dono()      # sem mudo, o audio ao Dono continua
    mudo.mutar()
    assert mudo.bloqueia_audio_dono()
    mudo.desmutar()
    mudo.definir_whatsapp_dono(False)


def test_jarvis_entende_comando_de_mudo_por_texto():
    from braniac import jarvis
    resp, da_ia = jarvis.processar(None, "/mudo 10", "web")
    assert "10 min" in resp and not da_ia and mudo.ativo()
    resp, _ = jarvis.processar(None, "/mudo off", "web")
    assert "voltei" in resp and not mudo.ativo()


def _tratar(dono, sig):
    voz_env, txt_env = [], []
    ler = lambda nome, anterior: None if sig == anterior else {"msgs": [{"d": "EU", "t": "oi", "c": ""}], "midias": [], "lista_sig": sig,
                                                                 "audio_dele": True, "n_audios": 3}
    dono.tratar_dono(None, ler=ler, ouvir=lambda n: ("me conta uma coisa", None), responder=lambda p: "Claro, Dono.",
                     falar=lambda n, t: voz_env.append(t) or True, enviar=lambda n, x: txt_env.append(x) or "✅")
    return voz_env, txt_env


def test_whatsapp_do_dono_vai_por_texto_so_com_mudo_e_interruptor(tmp_path, monkeypatch):
    from braniac import dono
    monkeypatch.setattr(dono, "ARQ", tmp_path / "dono_a.json")
    mudo.mutar()                                    # so mudo (interruptor desligado = padrao): audio ao Dono continua
    assert _tratar(dono, "A") == (["Claro, Dono."], [])
    monkeypatch.setattr(dono, "ARQ", tmp_path / "dono_b.json")
    mudo.definir_whatsapp_dono(True)              # mudo + interruptor: vai por escrito
    assert _tratar(dono, "B") == ([], ["Claro, Dono."])
    mudo.desmutar()
    mudo.definir_whatsapp_dono(False)
