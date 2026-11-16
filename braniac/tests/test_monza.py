from braniac import monza


def test_preco_dez_km():
    assert monza.preco(10) == 23.0


def test_conversa_completa(tmp_path, monkeypatch):
    monkeypatch.setattr(monza, "ARQ", tmp_path / "m.json")
    monkeypatch.setattr(monza, "geocodar", lambda x: (0, 0))
    monkeypatch.setattr(monza, "distancia_km", lambda a, b: 10.0)
    avisos = []
    assert monza.eh_pedido("quero uma corrida")
    assert "onde você está" in monza.responder("Ana", "quero uma corrida")
    assert monza.eh_pedido("Rua A", "Ana")          # conversa em andamento
    assert "pra onde" in monza.responder("Ana", "Rua A")
    r = monza.responder("Ana", "Rodoviária", avisos.append)
    assert "R$ 23,00" in r and "10.0 km" in r and avisos
    assert not monza.eh_pedido("oi", "Ana")          # conversa fechada


def test_de_para_direto(tmp_path, monkeypatch):
    monkeypatch.setattr(monza, "ARQ", tmp_path / "m.json")
    monkeypatch.setattr(monza, "geocodar", lambda x: (0, 0))
    monkeypatch.setattr(monza, "distancia_km", lambda a, b: 5.0)
    assert "R$ 11,50" in monza.responder("Bia", "corrida de Rua A para Rua B")
