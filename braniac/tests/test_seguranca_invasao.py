from braniac import seguranca


def test_invasao_sinais(tmp_path, monkeypatch):
    monkeypatch.setattr(seguranca, "BASE", tmp_path / "base.json")
    d = {"falhas": 50, "rdp_entrou": 2, "ameacas": ["x"], "externas_suspeitas": ["a.exe->1.2.3.4:80"], "contas": ["usuario"], "admins": ["usuario"]}
    gravs = [g for g, *_ in seguranca.invasao(d)]
    assert gravs.count("alta") == 3 and gravs.count("media") == 1
    d2 = dict(d, contas=["usuario", "intruso"], admins=["usuario", "intruso"], falhas=0, rdp_entrou=0, ameacas=[], externas_suspeitas=[])
    assert [t for _, t, _ in seguranca.invasao(d2)] == ["Conta ativa nova no PC: intruso.", "Novo administrador no PC: intruso."]


def test_sem_permissao_nao_diz_que_esta_tudo_certo(tmp_path, monkeypatch):
    monkeypatch.setattr(seguranca, "BASE", tmp_path / "b.json")
    assert any("Sem permissao" in t for _, t, _ in seguranca.invasao({"falhas": None}))
