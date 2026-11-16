# -*- coding: utf-8 -*-
"""16/11: voz PRIMARIA + SECUNDARIA (+ terciaria) por agente; se a primaria cair, a reserva fala sozinha."""
import pytest

from braniac import voz


def _prep(monkeypatch, tmp_path):
    from braniac import vozes_agentes as va, vozes_catalogo as vc
    monkeypatch.setattr(va, "DATA", tmp_path)
    monkeypatch.setattr("braniac.store.DATA", tmp_path)
    monkeypatch.setattr(vc, "_edge_vozes", lambda: [{"ShortName": "pt-BR-FranciscaNeural", "Gender": "Female", "Locale": "pt-BR"},
                                                     {"ShortName": "pt-BR-AntonioNeural", "Gender": "Male", "Locale": "pt-BR"}])
    monkeypatch.setattr(vc, "_kokoro_vozes", lambda: ["pf_dora", "pm_alex"])
    monkeypatch.setattr(voz, "_eleven_wav", lambda t: pytest.fail("nao devia chegar na ordem de sempre"))
    return va, vc


def test_primaria_cai_por_cota_e_a_secundaria_fala(monkeypatch, tmp_path):
    va, vc = _prep(monkeypatch, tmp_path)
    vc.escolher("gemini", "Kore", "alma", 1)
    vc.escolher("edge", "pt-BR-FranciscaNeural", "alma", 2)
    vc.escolher("kokoro", "pf_dora", "alma", 3)
    assert [r["motor"] for r in va.reservas("alma")] == ["edge", "kokoro"]
    assert va.escolha("alma")["motor"] == "gemini"                         # primaria no formato antigo, compativel
    monkeypatch.setattr(voz, "_gemini_wav", lambda t, **k: (_ for _ in ()).throw(RuntimeError("429 cota esgotada")))
    usadas = []
    monkeypatch.setattr(voz, "_edge_wav", lambda t, voz_nome=None, **k: usadas.append(voz_nome) or b"SECUNDARIA")
    with voz_agente("alma"):
        assert voz._falar_wav_motores("Oi, meu bem, tudo certo?") == b"SECUNDARIA"
    assert usadas == ["pt-BR-FranciscaNeural"]
    log = (tmp_path / "voz.log").read_text(encoding="utf-8")
    assert "alma" in log and "RESERVA edge:pt-BR-FranciscaNeural" in log and "cota" in log


def test_secundaria_com_audio_vazio_passa_para_a_terciaria(monkeypatch, tmp_path):
    va, vc = _prep(monkeypatch, tmp_path)
    vc.escolher("gemini", "Charon", "jarvis", 1)
    vc.escolher("edge", "pt-BR-AntonioNeural", "jarvis", 2)
    vc.escolher("kokoro", "pm_alex", "jarvis", 3)
    monkeypatch.setattr(voz, "_gemini_wav", lambda t, **k: (_ for _ in ()).throw(RuntimeError("fora do ar")))
    monkeypatch.setattr(voz, "_edge_wav", lambda t, voz_nome=None, **k: b"RIFF" + b"\0" * 40)   # so cabecalho = vazio
    monkeypatch.setattr(voz, "_kokoro_wav", lambda t, voz_nome=None: b"TERCIARIA:" + voz_nome.encode())
    assert voz._falar_wav_motores("Bom dia, senhor.") == b"TERCIARIA:pm_alex"


def test_alma_nao_aceita_reserva_masculina_e_tirar_reserva(monkeypatch, tmp_path):
    va, vc = _prep(monkeypatch, tmp_path)
    with pytest.raises(ValueError):
        vc.escolher("edge", "pt-BR-AntonioNeural", "alma", 2)              # Alma: so voz feminina, tambem na reserva
    with pytest.raises(ValueError):
        vc.escolher("xtts", "referencia", "jarvis", 2)                    # passa de 30 s: nem como reserva
    vc.escolher("edge", "pt-BR-FranciscaNeural", "alma", 3)               # terciaria sem secundaria vira secundaria
    vc.escolher("kokoro", "pf_dora", "alma", 3)
    assert [r["voz"] for r in va.reservas("alma")] == ["pt-BR-FranciscaNeural", "pf_dora"]
    va.tirar_reserva("alma", 2)
    assert [r["voz"] for r in va.reservas("alma")] == ["pf_dora"]         # a terciaria sobe
    va.limpar("jarvis")
    assert va.reservas("jarvis") == []


class voz_agente:
    def __init__(self, ag):
        self.ag = ag

    def __enter__(self):
        self.tok = voz._AGENTE.set(self.ag)

    def __exit__(self, *a):
        voz._AGENTE.reset(self.tok)
