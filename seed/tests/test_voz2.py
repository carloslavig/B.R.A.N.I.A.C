# -*- coding: utf-8 -*-
import array, base64, http.client, json, sys, time, urllib.error
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from braniac_seed import servidor, voz_nuvem


@pytest.fixture(autouse=True)
def casa(tmp_path, monkeypatch):
    monkeypatch.setenv("BRANIAC_HOME", str(tmp_path))
    voz_nuvem._cooldown.clear()


def pcm(seg=1.0, amp=8000):
    return array.array("h", [amp if (i // 40) % 2 else -amp for i in range(int(24000 * seg))]).tobytes()


def ok():
    return 200, {"candidates": [{"content": {"parts": [{"inlineData": {"data": base64.b64encode(pcm()).decode()}}]}}]}


def erro(cod):
    return urllib.error.HTTPError("u", cod, "x", {}, None)


CH = [("google", "k" * 30)]


def test_modelo_travado_nao_prende_a_voz_o_proximo_corre_em_paralelo(monkeypatch):
    monkeypatch.setattr(voz_nuvem, "HEDGE_S", 0.05)

    def post(url, chave, corpo, timeout=60):
        if "3.1" in url:
            time.sleep(1.5)            # modelo 'preview' que trava
        return ok()
    t = time.time()
    voz_nuvem.sintetizar("Teste de modelo lento aqui.", post=post, chaves=CH, usar_cache=False)
    assert time.time() - t < 1.0                # nao esperou o travado terminar


def test_motivo_cota_quando_tudo_esta_sem_cota():
    def post(url, chave, corpo, timeout=60):
        raise erro(429)
    with pytest.raises(voz_nuvem.VozErro) as e:
        voz_nuvem.sintetizar("Sem cota em nenhum modelo.", post=post, chaves=CH, usar_cache=False)
    assert e.value.motivo == "cota"
    t = time.time()
    with pytest.raises(voz_nuvem.VozErro) as e2:      # 2a vez: tudo em descanso, responde na hora
        voz_nuvem.sintetizar("Sem cota em nenhum modelo.", post=post, chaves=CH, usar_cache=False)
    assert e2.value.motivo == "cota" and time.time() - t < 0.5


def test_motivo_lento_quando_estoura_o_tempo():
    def post(url, chave, corpo, timeout=60):
        raise TimeoutError("The read operation timed out")
    with pytest.raises(voz_nuvem.VozErro) as e:
        voz_nuvem.sintetizar("Tudo travado por aqui.", post=post, chaves=CH, usar_cache=False)
    assert e.value.motivo == "lento"


def test_cada_tentativa_tem_tempo_curto():
    vistos = []

    def post(url, chave, corpo, timeout=60):
        vistos.append(timeout)
        return ok()
    voz_nuvem.sintetizar("Verificando o tempo limite.", post=post, chaves=CH, usar_cache=False)
    assert vistos and vistos[0] <= 25


def test_sem_chave_tem_motivo_proprio():
    with pytest.raises(voz_nuvem.VozErro) as e:
        voz_nuvem.sintetizar("Sem chave nenhuma.", chaves=[])
    assert e.value.motivo == "sem_chave"


def test_servidor_devolve_o_motivo_para_a_tela(tmp_path, monkeypatch):
    def falha(*a, **k):
        raise voz_nuvem.VozErro("sem cota", "cota")
    monkeypatch.setattr(voz_nuvem, "sintetizar", falha)
    s, porta = servidor.servir(porta=servidor.porta_livre(9200), bloquear=False)
    try:
        c = http.client.HTTPConnection("127.0.0.1", porta, timeout=10)
        c.request("POST", "/api/voz", json.dumps({"texto": "Olá"}).encode(), {"Content-Type": "application/json"})
        r = c.getresponse()
        d = json.loads(r.read())
        assert r.status == 503 and d["motivo"] == "cota"
    finally:
        s.shutdown()
