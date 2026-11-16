from braniac import termico as t


def _d(gpu=50, cpu_c=None, pct=10):
    return {"gpu_c": gpu, "cpu_c": cpu_c, "cpu_pct": pct, "ram_pct": 40, "top": []}


def test_motivo():
    assert "placa" in t.motivo(_d(gpu=85), [])
    assert "processador" in t.motivo(_d(cpu_c=95), [])
    assert t.motivo(_d(), []) == ""
    alto = [{"cpu_pct": "95"}] * 3
    assert "uso" in t.motivo(_d(pct=95), alto)
    assert t.motivo(_d(cpu_c=60, pct=95), alto) == ""        # com sensor e fresco, a carga sozinha nao alarma
