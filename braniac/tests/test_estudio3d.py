# -*- coding: utf-8 -*-
import time

import pytest

from braniac import estudio3d as e3

NARR = " ".join(["palavra"] * 40)


def test_validar_corrige_pecas_e_exige_narracao_e_cenas():
    t, n, c = e3.validar({"titulo": "X", "narracao": NARR, "cenas": [
        {"titulo": "a", "peca": "inexistente", "dados": {"valores": [1, 2, 3]}}, {"titulo": "b", "peca": "pilha", "dados": {"itens": 7}}]})
    assert [x["peca"] for x in c] == ["barras", "pilha"] and c[1]["dados"] == {"itens": 7}
    with pytest.raises(ValueError):
        e3.validar({"narracao": "curta", "cenas": []})
    with pytest.raises(ValueError):
        e3.validar({"narracao": NARR + " minha senha é 123", "cenas": [{"peca": "globo"}, {"peca": "globo"}]})


def test_ajustar_cenas_encosta_cortes_na_legenda_e_nao_sobrepoe():
    falas = [{"inicio": 0.0, "fim": 2.0, "texto": "a"}, {"inicio": 2.5, "fim": 5.0, "texto": "b"}, {"inicio": 5.4, "fim": 9.0, "texto": "c"}]
    cenas = e3.ajustar_cenas([{}, {}, {}], falas)
    assert cenas[0]["inicio"] == 0 and cenas[-1]["fim"] >= 9.0
    assert all(c["fim"] > c["inicio"] for c in cenas) and all(cenas[i]["fim"] == cenas[i + 1]["inicio"] for i in range(2))


def test_criar_barra_tema_sensivel_segredo_e_curto(tmp_path, monkeypatch):
    monkeypatch.setattr(e3, "PASTA", tmp_path)
    assert "fonte primária" in e3.criar("explique a eleição de 2026", None)
    assert "segredo" in e3.criar("explique minha senha do banco", None)
    assert "Qual o tema" in e3.criar("oi", None)


def test_criar_roda_em_segundo_plano_avisa_e_respeita_teto(tmp_path, monkeypatch):
    monkeypatch.setattr(e3, "PASTA", tmp_path)
    monkeypatch.setattr(e3, "ARQ_USO", tmp_path / "uso.json")
    avisos = []
    class R:
        def responder_neutro(self, s, t):
            return ('{"titulo":"Juros","narracao":"' + NARR + '","cenas":[{"titulo":"a","peca":"globo"},{"titulo":"b","peca":"pilha","dados":{"itens":4}}]}', "x")
    msg = e3.criar("como funcionam os juros compostos", R(), produzir_fn=lambda t, n, c: "C:/v.mp4", avisar_fn=avisos.append)
    assert "Começando" in msg
    for _ in range(50):
        if avisos:
            break
        time.sleep(0.05)
    assert avisos and "ficou pronto" in avisos[0] and "C:/v.mp4" in avisos[0]
    for _ in range(50):          # a trava e solta no fim da thread
        if e3._trava.acquire(blocking=False):
            e3._trava.release()
            break
        time.sleep(0.05)
    for _ in range(e3.MAX_DIA):
        e3.criar("outro tema de teste qualquer", R(), produzir_fn=lambda *a: "x", avisar_fn=lambda t: None)
        time.sleep(0.2)
    assert "teto" in e3.criar("mais um tema de teste", R(), produzir_fn=lambda *a: "x", avisar_fn=lambda t: None)


def test_validar_cenas_pecas_novas():
    import pytest as _p
    from braniac import estudio3d as E
    ok = E.validar_cenas([
        {"peca": "mapa", "dados": {"uf": "ba", "municipio": "Cidade C"}},
        {"peca": "numero", "dados": {"valor": "R$ 12,4 mi", "rotulo": "Receita"}},
        {"peca": "linha", "dados": {"valores": [1, 2, 3], "rotulos": ["a", "b", "c"], "final": 9}, "inicio": 0, "fim": 5},
    ], 10)
    assert ok[0]["dados"]["uf"] == "BA" and ok[1]["dados"]["valor"] == "R$ 12,4 mi" and ok[2]["fim"] == 5.0 and ok[2]["dados"]["final"] == 9.0
    for ruim in ({"peca": "mapa", "dados": {"uf": "bahia", "municipio": "x"}}, {"peca": "numero", "dados": {}}, {"peca": "linha", "dados": {"valores": [1]}}):
        with _p.raises(ValueError):
            E.validar_cenas([ruim, {"peca": "globo"}])


def test_fim_selo_estende_a_cena_anterior_e_nao_vira_barras():
    cenas = e3.validar_cenas([{"peca": "barras", "inicio": 0, "fim": 5, "dados": {"valores": [1, 2], "rotulos": ["A R$ 1 MI", "B R$ 2 MI"]}},
                              {"peca": "globo", "inicio": 5, "fim": 9},
                              {"peca": "fim_selo", "inicio": 9, "fim": 12}], 10)
    assert [c["peca"] for c in cenas] == ["barras", "globo"] and cenas[-1]["fim"] == 12
    assert cenas[0]["dados"]["rotulos"] == ["A R$ 1 MI", "B R$ 2 MI"]


def test_legenda_usa_texto_do_autor_com_tempos_do_whisper():
    from braniac.link.render_estudio import _legenda_do_texto
    ws = [("Segue", 0.0, 0.4), ("o", 0.4, 0.5), ("Arroba", 0.5, 0.8), ("e", 0.8, 0.9), ("o", 0.9, 1.0), ("para", 1.0, 1.2),
          ("mais", 1.2, 1.4), ("Educação", 1.5, 2.0), ("2", 2.0, 2.2), ("bilhões.", 2.2, 2.6)]
    ro = {"legenda": [{"inicio": 0, "fim": 2.6, "texto": "", "palavras": [{"inicio": a, "fim": b, "texto": w} for w, a, b in ws]}]}
    _legenda_do_texto(ro, "Segue o @parceiro-exemplo para mais Educação, 2 bilhões.", 8)
    texto = " ".join(f["texto"] for f in ro["legenda"])
    assert texto == "Segue o @parceiro-exemplo para mais Educação, 2 bilhões."
    p = {w["texto"]: w for f in ro["legenda"] for w in f["palavras"]}
    assert p["@parceiro-exemplo"]["inicio"] == 0.5 and p["Educação,"]["inicio"] == 1.5


def test_legenda_nao_parte_valor():
    from braniac.link.render_estudio import _legenda_do_texto
    txt = "Salvador arrecadou 12 bilhões e 200 milhões em 2024, depois mais."
    ws = [(w, i * 0.3, i * 0.3 + 0.25) for i, w in enumerate(txt.split())]
    ro = {"legenda": [{"inicio": 0, "fim": 9, "texto": "", "palavras": [{"inicio": a, "fim": b, "texto": w} for w, a, b in ws]}]}
    _legenda_do_texto(ro, txt, 4)
    assert any("12 bilhões e 200 milhões" in f["texto"] for f in ro["legenda"])


def test_mesa_continua_casinhas_ficam_e_ano_recomeca():
    from braniac.link.render_estudio import _mesa_continua
    s = lambda n, v: {"nome": n, "valor": v, "tipo": "casa"}
    cenas = [{"peca": "maquete", "inicio": 10, "fim": 20, "dados": {"ano": "2024", "cor": "dourado", "gastou": {"valor": 9e6}, "setores": [s("Educação", 3e6), s("Saúde", 2e6)]}},
             {"peca": "maquete", "inicio": 20, "fim": 30, "dados": {"ano": "2024", "setores": [s("Obras", 1e6)]}},
             {"peca": "maquete", "inicio": 30, "fim": 40, "dados": {"ano": "2025", "setores": [s("Educação", 4e6)]}},
             {"peca": "barras", "inicio": 40, "fim": 45, "dados": {"mesa": True, "valores": [1, 2]}}]
    _mesa_continua(cenas)
    d = [c["dados"] for c in cenas]
    assert [x["nome"] for x in d[0]["todos"]] == ["Educação", "Saúde", "Obras"]
    assert d[1]["ja"] == ["Educação", "Saúde"] and d[1]["ja_ano"] == {"Educação": 3e6, "Saúde": 2e6} and d[1]["gastou_ano"] == 9e6
    assert d[2]["inicio_ano"] and d[2]["volta"] == 1 and d[2]["ja_ano"] == {} and d[2]["t0"] == 30
    assert d[3]["ja"] == ["Educação", "Saúde", "Obras"] and d[3]["ano"] == "2025"


def _render_falso(tmp_path, monkeypatch, codigo_rs):
    """motor-rs de mentira: grava o video quando aceita; o Remotion de mentira grava sempre. Devolve a lista de chamadas."""
    exe = tmp_path / "motor-rs.exe"
    exe.write_text("x")
    monkeypatch.setattr(e3, "PASTA", tmp_path)
    monkeypatch.setattr(e3, "MOTOR_RS", exe)
    monkeypatch.setattr(e3, "_etapa", lambda *a: None)
    monkeypatch.delenv("ESTUDIO_MOTOR", raising=False)
    chamadas = []

    def run(cmd, **k):
        chamadas.append(cmd[0])
        saida = tmp_path / "edicoes" / "001-x" / "video.mp4"
        saida.parent.mkdir(parents=True, exist_ok=True)
        rs = cmd[0] == str(exe)
        if not rs or codigo_rs == 0:
            saida.write_text("v")
        return e3.subprocess.CompletedProcess(cmd, codigo_rs if rs else 0, "", "motor-rs ainda nao faz: globo" if rs and codigo_rs else "")
    monkeypatch.setattr(e3.subprocess, "run", run)
    return chamadas


def test_renderizar_usa_motor_rs_quando_ele_aceita(tmp_path, monkeypatch):
    chamadas = _render_falso(tmp_path, monkeypatch, 0)
    saida, motor = e3.renderizar("001-x")
    assert motor == "motor-rs" and saida.is_file() and chamadas == [str(tmp_path / "motor-rs.exe")]


def test_renderizar_cai_no_remotion_se_motor_rs_recusa_ou_esta_desligado(tmp_path, monkeypatch):
    chamadas = _render_falso(tmp_path, monkeypatch, 3)
    assert e3.renderizar("001-x")[1] == "remotion" and chamadas[-1] == "node"
    chamadas.clear()
    monkeypatch.setenv("ESTUDIO_MOTOR", "remotion")
    assert e3.renderizar("001-x")[1] == "remotion" and chamadas == ["node"]
