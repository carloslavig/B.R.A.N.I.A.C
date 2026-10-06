# -*- coding: utf-8 -*-
import array, base64, http.client, io, json, sys, urllib.error, wave
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from braniac_seed import cofre, provedores, servidor, voz_nuvem


@pytest.fixture(autouse=True)
def casa(tmp_path, monkeypatch):
    monkeypatch.setenv("BRANIAC_HOME", str(tmp_path))
    voz_nuvem._cooldown.clear()


def pcm(seg=1.0, amp=8000):
    n = int(24000 * seg)
    return array.array("h", [amp if (i // 40) % 2 else -amp for i in range(n)]).tobytes()


def resposta(pcm_bytes):
    return 200, {"candidates": [{"content": {"parts": [{"inlineData": {"data": base64.b64encode(pcm_bytes).decode()}}]}}]}


def http_erro(cod):
    return urllib.error.HTTPError("u", cod, "x", {}, None)


def test_texto_e_limpo_para_ser_falado():
    t = voz_nuvem.limpar("**Olá!** Veja https://x.com/abc 😀 e - item\n- outro!!")
    assert "http" not in t and "*" not in t and "😀" not in t and "!" not in t and "outro" in t


def test_voz_padrao_por_genero_e_opcoes():
    assert voz_nuvem.voz_padrao("feminina") == "Kore" and voz_nuvem.voz_padrao("masculina") == "Achird"
    assert all(len(v) >= 3 for v in voz_nuvem.VOZES.values())


def test_sem_chave_levanta_erro_para_cair_na_voz_do_sistema():
    with pytest.raises(voz_nuvem.VozErro):
        voz_nuvem.sintetizar("Olá, tudo bem?", chaves=[])


def test_gera_wav_polido_e_guarda_em_cache():
    chamadas = []

    def post(url, chave, corpo, timeout=60):
        chamadas.append((url, corpo["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"]))
        return resposta(pcm(1.0))
    wav = voz_nuvem.sintetizar("Olá, tudo bem com você hoje?", "masculina", post=post, chaves=[("google", "k" * 30)])
    assert wav[:4] == b"RIFF" and chamadas[0][1] == "Achird"
    voz_nuvem.sintetizar("Olá, tudo bem com você hoje?", "masculina", post=post, chaves=[("google", "k" * 30)])
    assert len(chamadas) == 1                                    # 2a vez veio do cache: zero cota


def test_estilo_e_voz_diferentes_nao_reaproveitam_o_cache():
    n = []
    post = lambda u, k, c, timeout=60: n.append(1) or resposta(pcm(1.0))
    ch = [("google", "k" * 30)]
    voz_nuvem.sintetizar("Boa tarde, como vai você?", "feminina", post=post, chaves=ch, estilo="calmo")
    voz_nuvem.sintetizar("Boa tarde, como vai você?", "feminina", post=post, chaves=ch, estilo="animado")
    voz_nuvem.sintetizar("Boa tarde, como vai você?", "feminina", voz="Sulafat", post=post, chaves=ch, estilo="animado")
    assert len(n) == 3


def test_sem_cota_passa_para_a_proxima_chave_e_a_primeira_fica_em_descanso():
    usadas = []

    def post(url, chave, corpo, timeout=60):
        usadas.append((url.split("/models/")[1].split(":")[0], chave))
        if chave == "primeira" * 4:
            raise http_erro(429)
        return resposta(pcm(1.0))
    ch = [("google", "primeira" * 4), ("google_b", "segunda" * 5)]
    voz_nuvem.sintetizar("Teste de cota esgotada aqui.", post=post, chaves=ch, usar_cache=False)
    assert usadas[0][1] == "primeira" * 4 and usadas[-1][1] == "segunda" * 5          # a 2a chave (outro projeto) assumiu
    usadas.clear()
    voz_nuvem.sintetizar("Teste de cota esgotada aqui.", post=post, chaves=ch, usar_cache=False)
    assert all(c == "segunda" * 5 for _, c in usadas)                                  # a 1a ficou em descanso (nao insiste 15 min)


def test_audio_longo_demais_e_rejeitado_como_se_lesse_o_estilo():
    post = lambda u, k, c, timeout=60: resposta(pcm(30.0))
    with pytest.raises(voz_nuvem.VozErro):
        voz_nuvem.sintetizar("Oi.", post=post, chaves=[("google", "k" * 30)], usar_cache=False)


def test_todos_falham_vira_erro_amigavel():
    def post(url, chave, corpo, timeout=60):
        raise http_erro(500)
    with pytest.raises(voz_nuvem.VozErro) as e:
        voz_nuvem.sintetizar("Falha geral aqui.", post=post, chaves=[("google", "k" * 30)], usar_cache=False)
    assert "sem voz natural" in str(e.value)


def test_polir_normaliza_e_corta_silencio():
    silencio = array.array("h", [0] * 24000).tobytes()
    bruto = voz_nuvem._para_wav(silencio + pcm(0.5, 3000) + silencio)
    with wave.open(io.BytesIO(voz_nuvem.polir(bruto))) as w:
        x = array.array("h")
        x.frombytes(w.readframes(w.getnframes()))
    assert len(x) < 24000 * 1.0 and max(x) > 0.85 * 32767            # cortou as pontas e normalizou o volume


def test_disponivel_so_com_chave_do_google(monkeypatch):
    monkeypatch.setattr(cofre, "tem", lambda c: c == "groq")
    assert not voz_nuvem.disponivel()
    monkeypatch.setattr(cofre, "tem", lambda c: c == "google_b")
    assert voz_nuvem.disponivel()


# ---------- chaves: passo a passo e nivel ----------

def test_todo_provedor_tem_passo_a_passo_e_formato():
    for c in provedores.catalogo():
        assert len(c["passos"]) >= 2 and c["formato"] and c["onde"].startswith("https://")
    assert provedores.ORDEM[0] == "google" and provedores.PROVEDORES["google"]["passos"][0].startswith("Abra aistudio")


def test_niveis_mostram_que_mais_chaves_e_melhor():
    assert provedores.nivel([])["nome"] == "Nenhuma" and not provedores.nivel([])["voz_natural"]
    assert provedores.nivel(["groq"])["nome"] == "Básico" and not provedores.nivel(["groq"])["voz_natural"]
    assert provedores.nivel(["google"])["voz_natural"]
    assert provedores.nivel(["google", "groq"])["nome"] == "Bom"
    assert provedores.nivel(["google", "google_b", "groq", "openrouter"])["nome"] == "Excelente"


# ---------- servidor ----------

@pytest.fixture()
def srv(tmp_path, monkeypatch):
    monkeypatch.setenv("BRANIAC_HOME", str(tmp_path))
    s, porta = servidor.servir(porta=servidor.porta_livre(9000), bloquear=False)
    yield porta
    s.shutdown()


def chamar(porta, metodo, caminho, corpo=None):
    c = http.client.HTTPConnection("127.0.0.1", porta, timeout=10)
    c.request(metodo, caminho, json.dumps(corpo).encode() if corpo is not None else None, {"Content-Type": "application/json"})
    r = c.getresponse()
    dados = r.read()
    c.close()
    return r.status, r.getheader("Content-Type"), dados


def test_voz_sem_chave_devolve_503_para_usar_voz_do_sistema(srv):
    assert chamar(srv, "POST", "/api/voz", {"texto": "Olá"})[0] == 503


def test_voz_privada_nunca_manda_texto_para_fora(srv, monkeypatch):
    chamou = []
    monkeypatch.setattr(voz_nuvem, "sintetizar", lambda *a, **k: chamou.append(1) or b"RIFF")
    chamar(srv, "POST", "/api/voz/config", {"privada": True})
    assert chamar(srv, "POST", "/api/voz", {"texto": "Olá"})[0] == 409 and not chamou


def test_voz_com_chave_devolve_audio(srv, monkeypatch):
    monkeypatch.setattr(voz_nuvem, "sintetizar", lambda *a, **k: b"RIFFxxxx")
    st, tipo, dados = chamar(srv, "POST", "/api/voz", {"texto": "Olá", "genero": "masculina"})
    assert st == 200 and tipo == "audio/wav" and dados == b"RIFFxxxx"


def test_estado_traz_voz_nivel_e_explicacoes(srv):
    e = json.loads(chamar(srv, "GET", "/api/estado")[2])
    assert e["voz"]["nuvem"] is False and e["nivel"]["nome"] == "Nenhuma" and "Quanto mais chaves" in e["por_que_mais"]
    assert "Kore" in [n for n, _ in e["voz"]["vozes"]["feminina"]] and set(e["voz"]["estilos"]) == {"calmo", "profissional", "animado"}
    assert e["etapas"][1] == "chaves"
