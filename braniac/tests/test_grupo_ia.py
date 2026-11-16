from braniac import grupo_ia as g


def test_marcacao_so_do_numero_do_dono(monkeypatch):
    monkeypatch.setattr(g, "MEU_NUMERO", "99999-0000")
    assert g.me_chamaram("@Dono você sabe de algum modelo?")
    assert g.me_chamaram("oi @5511999990000 tudo bem?")
    assert g.me_chamaram("@+55 11 99999-0000 ajuda aqui")
    assert not g.me_chamaram("@todos olhem isso")
    assert not g.me_chamaram("@Tiago e @Vinicius, o Dono viu isso?")
    assert not g.me_chamaram("sem marcar ninguém")


def test_primeira_rodada_so_marca_como_vista_e_nao_responde(tmp_path, monkeypatch):
    monkeypatch.setattr(g, "ESTADO", tmp_path / "e.json")
    msgs = [{"d": "ELE", "c": "[10:00, 26/10/2026] Tiago:", "t": "@Dono olha esse modelo novo"}]
    enviados = []
    r = g.ciclo(None, ler=lambda: msgs, enviar=lambda *a: enviados.append(a))
    assert r == {"novas": 0} and not enviados
