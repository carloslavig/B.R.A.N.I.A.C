import time
from datetime import datetime

from braniac import candidatura_rotina as R, candidaturas as C


def test_janela():
    assert R.janela(datetime(2026, 11, 4, 9)) == "manha" and R.janela(datetime(2026, 11, 4, 14)) == "tarde"
    assert R.janela(datetime(2026, 11, 4, 20)) == "noite" and R.janela(datetime(2026, 11, 4, 3)) is None


def test_tick_dispara_uma_vez_e_conta_enviadas(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "ARQ", tmp_path / "r.json")
    monkeypatch.setattr(R, "PAUSA", tmp_path / "pausa")
    monkeypatch.setattr(C, "ARQ", tmp_path / "c.json")
    chamadas, msgs = [], []
    agora = datetime.now().replace(hour=9)

    def falso(p):
        chamadas.append(p)
        C.registrar("enviada", "Dev Irmao", "Acme", "https://x.y/1")
        return 0, "1 enviada, 0 puladas"
    assert R.tick(agora, msgs.append, falso) == "manha"
    for _ in range(50):
        if msgs:
            break
        time.sleep(0.05)
    assert len(chamadas) == 1 and "1 enviada" in msgs[0]
    assert R.tick(agora, msgs.append, falso) is None        # espera de 1 h entre tentativas
