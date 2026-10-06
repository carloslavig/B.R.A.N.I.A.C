# -*- coding: utf-8 -*-
import array, base64, sys, urllib.error
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from braniac_seed import perfil, voz_nuvem


@pytest.fixture(autouse=True)
def casa(tmp_path, monkeypatch):
    monkeypatch.setenv("BRANIAC_HOME", str(tmp_path))
    voz_nuvem._cooldown.clear()
    voz_nuvem._cooldown_motivo.clear()


def ok():
    pcm = array.array("h", [8000 if (i // 40) % 2 else -8000 for i in range(24000)]).tobytes()
    return 200, {"candidates": [{"content": {"parts": [{"inlineData": {"data": base64.b64encode(pcm).decode()}}]}}]}


def test_modelo_que_travou_uma_vez_e_tentado_de_novo_na_mesma_chamada():
    n = []

    def post(url, chave, corpo, timeout=60):
        n.append(url)
        if len(n) == 1:
            raise TimeoutError("The read operation timed out")
        return ok()
    wav = voz_nuvem.sintetizar("Tente de novo se travar.", post=post, chaves=[("google", "k" * 30)], usar_cache=False)
    assert wav[:4] == b"RIFF" and len(n) == 2 and n[0] == n[1]       # mesmo modelo, 2a tentativa funcionou


def test_travar_nao_deixa_o_modelo_em_descanso():
    def post(url, chave, corpo, timeout=60):
        raise TimeoutError("The read operation timed out")
    with pytest.raises(voz_nuvem.VozErro):
        voz_nuvem.sintetizar("Tudo trava aqui.", post=post, chaves=[("google", "k" * 30)], usar_cache=False)
    assert not voz_nuvem._cooldown            # so cota/erro de servico dao descanso


def test_descanso_por_servico_fora_nao_e_chamado_de_cota():
    def post(url, chave, corpo, timeout=60):
        raise urllib.error.HTTPError("u", 500, "x", {}, None)
    with pytest.raises(voz_nuvem.VozErro):
        voz_nuvem.sintetizar("Servico fora do ar.", post=post, chaves=[("google", "k" * 30)], usar_cache=False)
    with pytest.raises(voz_nuvem.VozErro) as e:
        voz_nuvem.sintetizar("Servico fora do ar.", post=post, chaves=[("google", "k" * 30)], usar_cache=False)
    assert e.value.motivo == "outro"


def test_reserva_robotica_comeca_desligada():
    assert perfil.carregar()["voz_reserva"] is False
