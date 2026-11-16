import pytest

from braniac import modulos


@pytest.fixture(autouse=True)
def _isolado(tmp_path, monkeypatch):
    monkeypatch.setattr(modulos, "ARQUIVO", tmp_path / "modulos.json")


def test_instalacao_antiga_sem_arquivo_tem_tudo_ligado():
    assert not modulos.configurado()
    assert set(modulos.ativos()) == set(modulos.IDS)


def test_escolha_liga_so_o_escolhido_e_ignora_id_invalido():
    assert modulos.definir(["marketing", "marketing", "nao-existe"]) == ["marketing"]
    assert modulos.configurado()
    assert modulos.ativo("marketing") and not modulos.ativo("programacao")
    modulos.exigir("marketing")
    with pytest.raises(RuntimeError):
        modulos.exigir("programacao")


def test_so_base_desliga_todos_os_andares():
    modulos.definir([])
    assert modulos.ativos() == []
    assert all(not m["ativo"] for m in modulos.estado()["modulos"])


def test_gates_dos_andares(monkeypatch):
    from braniac import sauraki
    modulos.definir(["marketing"])
    assert sauraki._agentes_empresa() == []
    monkeypatch.setattr("braniac.sauraki._agentes_registrados", lambda: [])
    monkeypatch.setattr("braniac.empresa_mkt.agentes", lambda: [{"nome": "Zé", "papel": "teste"}])
    assert [a[0] for a in sauraki._agentes_marketing()] == ["Zé"]
    modulos.definir([])
    assert sauraki._agentes_marketing() == []


def test_opcionais_airbnb_exercito_vaquinha(monkeypatch):
    from braniac import airbnb_vigia, exercito, financeiro, vaquinha
    modulos.definir([])
    assert not exercito.eh_pergunta("qual o prazo do exame do exército?")
    assert not vaquinha.aguardando()
    assert vaquinha.tick(lambda m: None, lambda m: None) is None
    assert not financeiro.eh_vaquinha("como está a vaquinha, quanto arrecadou?")
    with pytest.raises(RuntimeError):
        airbnb_vigia.ligar()
    assert not airbnb_vigia.ligado()
    modulos.definir(["exercito", "vaquinha"])
    assert exercito.eh_pergunta("qual o prazo do exame do exército?")
    assert financeiro.eh_vaquinha("como está a vaquinha, quanto arrecadou?")
