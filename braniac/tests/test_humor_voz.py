# -*- coding: utf-8 -*-
import io, struct, wave
from datetime import datetime
import pytest

pytest.importorskip("numpy")      # dependencias de voz sao opcionais (requirements-voz.txt)
from braniac import contexto, jarvis, voz


class R:
    cfg = {"cadeia": []}


@pytest.fixture(autouse=True)
def _voz_real(monkeypatch):
    # conftest troca voz.falar_wav por um stub; aqui testamos o modulo de verdade (sem rede: requests e' simulado por teste)
    import importlib
    importlib.reload(voz)
    monkeypatch.setattr(voz, "_cooldown", {})
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setattr(voz, "_cfg_voz", lambda: {"nome": "Achird", "modelos": ["m-novo", "m-velho"], "estilo": voz.ESTILO_BASE})


def resp(pcm_segundos=2.0, status=200):
    import base64

    class Rsp:
        status_code = status

        def json(self):
            pcm = b"\x40\x1f" * int(24000 * pcm_segundos)
            return {"candidates": [{"content": {"parts": [{"inlineData": {"data": base64.b64encode(pcm).decode()}}]}}]}
    return Rsp()


# ---------- humor ----------

def test_humor_padrao_35_e_ajustavel_e_persiste():
    assert contexto.humor() == 35
    assert "35%" in contexto.diretriz_humor() and "a cada três respostas" in contexto.diretriz_humor()
    assert contexto.definir_humor(60) == 60 and contexto.humor() == 60
    assert contexto.definir_humor(500) == 100 and contexto.definir_humor(-3) == 0   # limites 0-100
    assert "sem piadas" in contexto.diretriz_humor(5)


def test_humor_vem_com_travas_para_assunto_serio():
    d = contexto.diretriz_humor(35)
    assert "NUNCA faça piada em assunto sério" in d and "nunca à custa de ninguém" in d
    assert "[humor] Humor 35%" in contexto.dossie_para("oi")   # entra sempre no contexto (prompt, decisoes e atendimento)


def test_comando_de_humor_pelo_chat(monkeypatch):
    monkeypatch.setattr(jarvis.power, "pausado", lambda: False)
    assert "35%" in jarvis.processar(R(), "/humor", "c")[0]
    assert "50%" in jarvis.processar(R(), "aumenta o humor pra 50%", "c", origem="telegram")[0] and contexto.humor() == 50
    assert "35%" in jarvis.processar(R(), "Jarvis, deixa o humor em 35", "c", origem="whatsapp")[0] and contexto.humor() == 35


def test_comando_de_voz(monkeypatch):
    monkeypatch.setattr(jarvis.power, "pausado", lambda: False)
    monkeypatch.setattr(voz, "_cfg_voz", lambda: {"nome": "Achird"})
    assert "Achird" in jarvis.processar(R(), "/voz", "c")[0]
    assert "Umbriel" in jarvis.processar(R(), "/voz umbriel", "c")[0] and contexto.voz_nome() == "Umbriel"
    assert "Não conheço" in jarvis.processar(R(), "/voz Kore", "c")[0] and contexto.voz_nome() == "Umbriel"   # Kore e feminina


# ---------- voz: cadeia de modelos, cota, plausibilidade, acabamento ----------

def test_usa_o_primeiro_modelo_e_manda_estilo_natural(monkeypatch):
    enviados = []

    def post(url, **kw):
        enviados.append((url, kw["json"]["contents"][0]["parts"][0]["text"]))
        return resp(2.0)
    monkeypatch.setattr("requests.post", post)
    out = voz._gemini_wav("Oi, tudo bem com você, Dono hoje")
    assert "m-novo" in enviados[0][0] and "sério" in enviados[0][1] and "sorridente" in enviados[0][1] and "bom humor" not in enviados[0][1]  # voz seria; humor 35 nao muda o tom
    assert voz.ULTIMO_MOTOR == "gemini:m-novo:Achird" and out.startswith(b"RIFF")


def test_modelo_sem_cota_vai_para_descanso_e_o_proximo_assume(monkeypatch):
    chamados = []

    def post(url, **kw):
        chamados.append(url)
        return resp(status=429) if "m-novo" in url else resp(2.0)
    monkeypatch.setattr("requests.post", post)
    voz._gemini_wav("Oi, tudo bem com você, Dono hoje")
    assert voz.ULTIMO_MOTOR == "gemini:m-velho:Achird"
    chamados.clear()
    voz._gemini_wav("Oi, tudo bem com você, Dono hoje")
    assert all("m-novo" not in c for c in chamados)               # nao insiste no modelo sem cota por 15 min


def test_audio_longo_demais_e_rejeitado_porque_leu_o_estilo(monkeypatch):
    monkeypatch.setattr("requests.post", lambda url, **kw: resp(20.0) if "m-novo" in url else resp(2.0))
    voz._gemini_wav("Oi, tudo bem com você, Dono hoje")
    assert voz.ULTIMO_MOTOR == "gemini:m-velho:Achird"            # 20 s para 7 palavras: suspeito, ignorado


def test_sem_nenhum_modelo_cai_no_piper_e_deixa_rastro(monkeypatch, tmp_path):
    from braniac import store
    monkeypatch.setattr("requests.post", lambda url, **kw: resp(status=500))
    monkeypatch.setattr(store, "DATA", tmp_path)
    monkeypatch.setattr(voz, "_falar_wav_piper", lambda t: b"PIPER")
    monkeypatch.setattr(voz, "_kokoro_wav", lambda t: (_ for _ in ()).throw(RuntimeError("off")))
    monkeypatch.setattr(voz, "_edge_wav", lambda t: (_ for _ in ()).throw(RuntimeError("sem rede")))
    assert voz.falar_wav("Tudo certo por aqui.") == b"PIPER"
    assert voz.ULTIMO_MOTOR.startswith("piper:") and "PIPER (robotico)" in (tmp_path / "voz.log").read_text(encoding="utf-8")


def test_texto_sensivel_nunca_vai_para_a_nuvem(monkeypatch):
    monkeypatch.setattr("requests.post", lambda *a, **k: pytest.fail("texto sensivel nao pode ir ao Google"))
    monkeypatch.setattr(voz, "_falar_wav_piper", lambda t: b"PIPER")
    monkeypatch.setattr(voz, "_kokoro_wav", lambda t: (_ for _ in ()).throw(RuntimeError("off")))
    assert voz.falar_wav("Anote o pix e a senha do banco") == b"PIPER"


def test_acabamento_normaliza_volume_e_corta_silencio():
    import numpy as np
    taxa = 24000
    quieto = b"\x00\x00" * taxa                                   # 1 s de silencio
    fala = struct.pack("<h", 3000) * taxa                         # 1 s de 'fala' baixinha
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(taxa); w.writeframes(quieto + fala + quieto)
    out = voz.polir_wav(buf.getvalue())
    with wave.open(io.BytesIO(out)) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        dur = w.getnframes() / w.getframerate()
    assert dur < 1.7                                              # 3 s -> ~1,3 s (silencio das pontas saiu)
    assert 0.85 * 32767 < np.abs(x).max() <= 32767                # volume normalizado
    assert abs(int(x[0])) < 400 and abs(int(x[-1])) < 400         # sem 'clique' no inicio/fim


def test_sem_cota_do_gemini_usa_a_voz_neural_edge_antes_do_piper(monkeypatch):
    monkeypatch.setattr("requests.post", lambda url, **kw: resp(status=429))
    monkeypatch.setattr(voz, "_edge_wav", lambda t: b"EDGE")
    monkeypatch.setattr(voz, "_falar_wav_piper", lambda t: pytest.fail("nao devia cair no robotico"))
    assert voz.falar_wav("Tudo certo por aqui.") == b"EDGE"


# ---------- audio x texto (Layla nao entende audio; "para de mandar audio" vale) ----------

@pytest.mark.parametrize("msg", [
    "para de mandar áudio por favor", "pare de me mandar áudio", "chega de áudio", "não entendo áudio",
    "só escreve pra mim", "manda por escrito", "para com os áudios",
])
def test_pedidos_de_texto_sao_reconhecidos(msg):
    assert contexto.quer_texto(msg), msg


def test_layla_e_o_numero_dela_sao_sempre_texto(monkeypatch):
    monkeypatch.setattr(contexto, "SEMPRE_TEXTO", contexto.SEMPRE_TEXTO + ("9000-0002",))
    assert contexto.preferencia("Layla") == "texto"
    assert contexto.preferencia("+55 66 9000-0002") == "texto"
    assert contexto.deve_falar("+55 66 9000-0002", "oi layla tudo bem") is False


def test_preferencia_salva_vale_para_nome_parecido():
    contexto.definir_preferencia("Amigo", "texto")
    assert contexto.preferencia("Amigo Pereira Fresco Da Silva") == "texto"
    assert contexto.preferencia("Joana") == "voz"


def test_dono_manda_parar_audio_para_alguem_e_o_jarvis_obedece():
    from braniac import jarvis
    resp, _ = jarvis.processar(None, "Jarvis, para de mandar áudio pro Amigo", "c", None, origem="web")
    assert "só mando texto" in resp and contexto.preferencia("Amigo Souza") == "texto"
    resp, _ = jarvis.processar(None, "a Bruna não entende áudio", "c", None, origem="web")
    assert "só mando texto" in resp and contexto.preferencia("Paula ✨ Bruna") == "texto"


def test_exclamacao_vira_ponto_para_a_voz_soar_seria():
    assert voz.limpar_para_fala("Oi, Bruna! Tudo certo!! Pode mandar!") == "Oi, Bruna. Tudo certo. Pode mandar."


def test_voz_sem_humor_alto_nao_leva_tom_animado():
    assert "animado" not in voz.ESTILO_BASE and "descontra" not in voz.ESTILO_BASE


def _tom_dominante(wav):
    import io, wave
    import numpy as np
    with wave.open(io.BytesIO(wav)) as w:
        taxa = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)
    espectro = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    return taxa * int(np.argmax(espectro)) / len(x), len(x) / taxa


def test_voz_20_por_cento_mais_grave_mantem_a_velocidade():
    import io, wave
    import numpy as np
    taxa = 24000
    sinal = (np.sin(2 * np.pi * 200 * np.arange(taxa * 2) / taxa) * 12000).astype(np.int16)    # tom de 200 Hz, 2 s
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(taxa); w.writeframes(sinal.tobytes())
    f0, dur0 = _tom_dominante(buf.getvalue())
    f1, dur1 = _tom_dominante(voz.mais_grave(buf.getvalue(), 0.20))
    assert abs(f1 / f0 - 0.80) < 0.03 and abs(dur1 - dur0) < 0.05      # 20% mais grave, mesma duracao


def test_mais_grave_nunca_quebra_o_audio():
    assert voz.mais_grave(b"nao e wav") == b"nao e wav"
    assert voz.mais_grave(b"") == b""
    assert 0 <= voz.GRAVE <= 0.10                 # leve: 20% foi grave demais para o Dono


def test_com_grave_zero_o_audio_passa_direto(monkeypatch):
    monkeypatch.setattr(voz, "GRAVE", 0.0)
    audio = b"RIFF-qualquer-coisa"
    assert voz.mais_grave(audio) == audio          # GRAVE = 0: sem processar


def test_vozes_catalogo_escolher_e_motor_preferido(monkeypatch, tmp_path):
    from braniac import vozes_agentes as va, vozes_catalogo as vc
    monkeypatch.setattr(va, "DATA", tmp_path)
    monkeypatch.setattr("braniac.store.DATA", tmp_path)
    monkeypatch.setattr(vc, "_edge_vozes", lambda: [{"ShortName": "pt-BR-FranciscaNeural", "Gender": "Female", "Locale": "pt-BR"}])
    cat = vc.catalogo()
    ids = {m["id"]: m for m in cat["motores"]}
    assert ids["rafael"]["lento"] and ids["xtts"]["lento"] and not ids["piper"]["lento"]
    assert any(v["id"] == "Kore" and v["genero"] == "F" for v in ids["gemini"]["vozes"])
    with pytest.raises(ValueError):
        vc.escolher("xtts", "referencia")          # passa de 30 s: desligado
    vc.escolher("edge", "pt-BR-FranciscaNeural")
    assert voz._escolha()["genero"] == "F" and voz._escolha_voz("edge") == "pt-BR-FranciscaNeural"
    monkeypatch.setattr(voz, "_edge_wav", lambda t: b"EDGE")
    assert voz._falar_wav_motores("Oi, tudo bem?") == b"EDGE"   # o motor escolhido tenta primeiro


def test_voz_por_agente_alma_tem_a_dela_e_jarvis_continua_no_topo(monkeypatch, tmp_path):
    from braniac import vozes_agentes as va, vozes_catalogo as vc
    monkeypatch.setattr(va, "DATA", tmp_path)
    monkeypatch.setattr("braniac.store.DATA", tmp_path)
    monkeypatch.setattr(vc, "_edge_vozes", lambda: [{"ShortName": "pt-BR-FranciscaNeural", "Gender": "Female", "Locale": "pt-BR"}, {"ShortName": "pt-BR-AntonioNeural", "Gender": "Male", "Locale": "pt-BR"}])
    assert [a["id"] for a in va.agentes()] == ["jarvis", "alma", "zelo"]
    vc.escolher("edge", "pt-BR-AntonioNeural", "jarvis")
    vc.escolher("edge", "pt-BR-FranciscaNeural", "alma")
    assert va.escolha("jarvis")["vozes"]["edge"] == "pt-BR-AntonioNeural" and va.escolha("alma")["genero"] == "F"
    vistos = []
    monkeypatch.setattr(voz, "_edge_wav", lambda t: vistos.append(voz._escolha_voz("edge")) or b"W")
    voz.falar_wav("Oi.", agente="alma"); voz.falar_wav("Oi.")
    assert vistos == ["pt-BR-FranciscaNeural", "pt-BR-AntonioNeural"]   # cada agente fala com a sua voz
    va.limpar("alma")
    assert va.escolha("alma") == {} and va.escolha("jarvis")["motor"] == "edge"
    with pytest.raises(ValueError):
        va.escolher("fantasma", "edge", "x", "M")


def test_ajustes_de_voz_mudam_o_audio_e_a_alma_manda_audio_so_ao_dono(monkeypatch, tmp_path):
    import io, wave, numpy as np
    from braniac import alma_cuida, vozes_agentes as va
    monkeypatch.setattr(va, "DATA", tmp_path)
    monkeypatch.setattr("braniac.store.DATA", tmp_path)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
        w.writeframes((np.sin(np.linspace(0, 2000, 24000)) * 8000).astype("<i2").tobytes())
    wav = buf.getvalue()
    assert voz.aplicar_ajustes(wav, {}) == wav                       # sem ajuste: nada muda
    lento = voz.aplicar_ajustes(wav, {"velocidade": 0.8, "calor": 50})
    assert wave.open(io.BytesIO(lento)).getnframes() > wave.open(io.BytesIO(wav)).getnframes()   # devagar = audio mais longo
    s = va.ajustar("alma", {"velocidade": 9, "tom": -99, "calor": 50, "estilo": "voz baixa"})["ajustes"]
    assert s == {"velocidade": 1.3, "tom": -6.0, "calor": 50, "estilo": "voz baixa"}   # valores fora da faixa sao cortados
    audios, textos = [], []
    monkeypatch.setattr(alma_cuida, "_nome", lambda a: a)
    for apelido in ("dono", "parceira"):
        alma_cuida._mandar(lambda n, t: textos.append(n), apelido, "Oi, tudo bem?", enviar_audio=lambda n, t: audios.append(n))
    assert textos == ["dono", "parceira"] and audios == ["dono"]   # audio so para o Dono


def test_alma_so_voz_feminina_e_combinacoes_sedutoras(monkeypatch, tmp_path):
    from braniac import vozes_agentes as va, vozes_catalogo as vc
    monkeypatch.setattr(va, "DATA", tmp_path)
    monkeypatch.setattr("braniac.store.DATA", tmp_path)
    monkeypatch.setattr(vc, "_edge_vozes", lambda: [{"ShortName": n, "Gender": "Female", "Locale": "pt-BR"} for n in ("pt-BR-FranciscaNeural", "pt-BR-ThalitaMultilingualNeural")])
    cat = vc.catalogo()
    ags = {a["id"]: a for a in cat["agentes"]}
    assert ags["alma"]["so_genero"] == "F" and not ags["jarvis"].get("so_genero")
    assert cat["combinacoes"] and all(c["ajustes"]["velocidade"] < 1 for c in cat["combinacoes"])
    ids = {m["id"]: {v["id"] for v in m["vozes"]} for m in cat["motores"]}
    assert all(c["voz"] in ids[c["motor"]] for c in cat["combinacoes"])        # toda combinacao aponta para uma voz que existe


def test_alma_mente_estados_apelidos_e_reacao(monkeypatch, tmp_path):
    from braniac import alma_cuida, alma_mente as am, tratamento
    for m in (am, alma_cuida):
        monkeypatch.setattr(m, "PASTA", tmp_path / "alma")
    for nome in ("PERFIL", "HUMOR", "LOOPS", "PARAMS"):
        monkeypatch.setattr(am, nome, tmp_path / "alma" / nome.lower())
    monkeypatch.setattr(alma_cuida, "ESTADO", tmp_path / "alma" / "cuida.json")
    monkeypatch.setattr(alma_cuida, "_nome", lambda a: a)
    assert am.detectar_estado("A meta foi batida!")["estado"] == "conquista"
    assert am.detectar_estado("Estou muito estressado, nunca dá certo")["intensidade"] >= 2
    assert am.detectar_estado("não estou triste")["estado"] == "" and am.detectar_estado("oi, tudo bem")["estado"] == ""
    assert tratamento.alma_terceiros("Oi, meu amor, tudo bem? Beijo, gostoso.") == "Oi, Chefe, tudo bem? Beijo, Chefe."   # terceiros: nada de apelido intimo
    enviados = []
    monkeypatch.setattr(alma_cuida, "_audio_da_alma", lambda *a, **k: None)
    agora = datetime(2026, 11, 16, 12, 0)
    item = {"ts": 1, "texto": "A meta foi batida!"}
    c = alma_cuida.classificar(item["texto"])
    fez = am.processar(item, c, lambda n, t: enviados.append((n, t)), agora, llm=lambda s, u: "Parabéns, meu bem! Foco no próximo passo, sem se sobrecarregar.")
    assert fez == ["conquista->dono"] and enviados[0][0] == "dono" and "meu bem" in enviados[0][1]   # com o Dono vale o apelido
    assert am.processar(item, c, lambda n, t: enviados.append(1), agora) == ["conquista->dono"]           # 16/11: conquista sempre tem resposta, sem intervalo
    cansado = {"ts": 2, "texto": "to cansado"}
    assert am.processar(cansado, alma_cuida.classificar(cansado["texto"]), lambda n, t: enviados.append(1), agora, llm=lambda s, u: "Descansa um pouco, meu bem, eu fico aqui.") == ["cansaco->dono"]
    assert am.processar(cansado, alma_cuida.classificar(cansado["texto"]), lambda n, t: enviados.append(1), agora) == []   # o resto mantem o intervalo minimo
    msg = am.compor("parceira", "Dono está cansado", "cansaco", llm=lambda s, u: "Oi, querido, avise o meu amor", quem="Parceira")
    assert "querido" not in msg.lower() and "meu amor" not in msg.lower()
    assert "Senhor" in __import__("braniac.router", fromlist=["x"]).REGRA_TRATAMENTO


def test_alma_apresentacao_so_com_fatos_da_lista(monkeypatch):
    from braniac import alma_mente as am
    bom = ("Oi, querido, eu sou a Alma e fui modificada. Agora tenho a minha voz, que você escolheu. Eu percebo quando você está estressado, triste ou alegre e venho falar com você. "
           "Se algo for sério eu aviso a Parceira e lembro o CVV, 188, e o SAMU, 192. Ainda posso errar, tá?")
    assert am.apresentacao(llm=lambda s, u: bom) == bom
    assert "Alma" in am.FATOS_NOVOS[0] and "188" in " ".join(am.FATOS_NOVOS)
    respostas = iter(["Oi! Hoje você bateu a meta de 500 reais e eu fiquei feliz em saber." + " x" * 80, "Estou de volta, querido! " + "blá " * 40, bom])
    assert am.apresentacao(llm=lambda s, u: next(respostas)) == bom           # texto com numero/fato inventado e 'de volta' e recusado; tenta de novo
    assert am.apresentacao(llm=lambda s, u: "Oi" ) == ""                      # modelo fraco: nada e enviado


def test_alma_nunca_fala_com_voz_masculina_mesmo_sem_cota(monkeypatch, tmp_path):
    monkeypatch.setattr("braniac.store.DATA", tmp_path)          # sem escolha salva: vale a "ordem de sempre", que e masculina
    def sem_cota(*a, **k):
        raise RuntimeError("HTTP 429")
    usadas = []
    monkeypatch.setattr(voz, "_gemini_wav", sem_cota)
    monkeypatch.setattr(voz, "_edge_wav", lambda t, timeout=40, voz_nome=None: usadas.append(("edge", voz_nome)) or b"EDGE")
    monkeypatch.setattr(voz, "_kokoro_wav", lambda t, voz_nome=None: usadas.append(("kokoro", voz_nome)) or b"KOKORO")
    monkeypatch.setattr(voz, "_falar_wav_piper", lambda *a, **k: pytest.fail("Piper e masculino: a Alma nunca"))
    assert voz.falar_wav("Oi, tudo bem?", agente="alma") == b"EDGE"
    assert usadas == [("edge", "pt-BR-FranciscaNeural")]          # cota do Gemini acabou -> Edge FEMININA, nunca o Antonio
    monkeypatch.setattr(voz, "_edge_wav", sem_cota)
    assert voz.falar_wav("Oi, tudo bem?", agente="alma") == b"KOKORO" and usadas[-1] == ("kokoro", "pf_dora")
    monkeypatch.setattr(voz, "_kokoro_wav", sem_cota)
    with pytest.raises(RuntimeError):                              # nada feminino falou: sem audio, nunca voz de homem
        voz.falar_wav("Oi, tudo bem?", agente="alma")
    monkeypatch.setattr(voz, "_falar_wav_piper", lambda *a, **k: b"PIPER")
    assert voz.falar_wav("Oi, tudo bem?") == b"PIPER"              # o Jarvis continua com a ordem de sempre
