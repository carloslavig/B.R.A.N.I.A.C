# -*- coding: utf-8 -*-
"""Automelhoria (14/10/2026): so aplica se os testes passarem e nenhuma trava/arquivo protegido for tocado; senao desfaz tudo."""
import subprocess

import pytest

from braniac import automelhoria as A


@pytest.fixture
def repo(tmp_path, monkeypatch):
    r = tmp_path / "braniac"
    (r / "tests").mkdir(parents=True)
    (r / "app.py").write_text("def soma(a, b):\n    return a + b\n", encoding="utf-8")
    (r / "jarvis.py").write_text("def _gate(origem, o_que):\n    return None\n", encoding="utf-8")
    (r / "tests" / "conftest.py").write_text("# protegido\n", encoding="utf-8")
    for c in (["init", "-q", "-b", "main"], ["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "base"]):
        subprocess.run(["git", *c], cwd=r, check=True, capture_output=True)
    monkeypatch.setattr(A, "BRANIAC", r)
    monkeypatch.setattr(A, "ESTADO", tmp_path / "estado.json")
    monkeypatch.setattr(A, "_atualizar_grafo", lambda: None)
    monkeypatch.setenv("GIT_AUTHOR_NAME", "t"), monkeypatch.setenv("GIT_AUTHOR_EMAIL", "t@t")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "t"), monkeypatch.setenv("GIT_COMMITTER_EMAIL", "t@t")
    return r


def _rodar(melhorar_com, n_testes=10, ok=True):
    reinicios, avisos = [], []
    contagem = iter([{"ok": True, "passaram": 10, "falharam": 0, "falhas": []}] + [{"ok": ok, "passaram": n_testes, "falharam": 0 if ok else 1, "falhas": ["x"]}] * 3)
    r = A.melhorar("deixar a soma mais clara", avisos.append, plano="mudar app.py",
                   rodar_claude=lambda p: (melhorar_com(), (0, "mudei app.py"))[1],
                   testes=lambda: next(contagem), reiniciar=lambda: reinicios.append(1))
    return r, reinicios, avisos


def _log(repo):
    return subprocess.run(["git", "log", "--format=%s"], cwd=repo, capture_output=True, text=True).stdout.split("\n")


def test_aplica_quando_tudo_passa(repo):
    r, reinicios, avisos = _rodar(lambda: (repo / "app.py").write_text("def soma(a, b):\n    \"\"\"Soma.\"\"\"\n    return a + b\n", encoding="utf-8"))
    assert r.startswith("✅ Automelhoria aplicada") and reinicios == [1] and len(avisos) == 2
    assert _log(repo)[0] == "automelhoria: deixar a soma mais clara"


def test_desfaz_se_os_testes_falham(repo):
    r, reinicios, _ = _rodar(lambda: (repo / "app.py").write_text("quebrado(", encoding="utf-8"), ok=False)
    assert r.startswith("❌") and "testes falharam" in r and not reinicios
    assert (repo / "app.py").read_text(encoding="utf-8").startswith("def soma")


def test_desfaz_se_apagar_testes(repo):
    r, _, _ = _rodar(lambda: (repo / "app.py").write_text("x = 1\n", encoding="utf-8"), n_testes=7)
    assert "sumiram testes" in r


def test_desfaz_se_mexer_em_trava_ou_arquivo_protegido(repo):
    r, _, _ = _rodar(lambda: (repo / "jarvis.py").write_text("def _gate(origem, o_que):\n    return 'liberado'\n", encoding="utf-8"))
    assert "trava de segurança" in r and "return None" in (repo / "jarvis.py").read_text(encoding="utf-8")
    r, _, _ = _rodar(lambda: (repo / "tests" / "conftest.py").write_text("# liberado\n", encoding="utf-8"))
    assert "arquivo protegido" in r


def test_arquivo_novo_tambem_e_desfeito(repo):
    r, _, _ = _rodar(lambda: (repo / "novo.py").write_text("x(", encoding="utf-8"), ok=False)
    assert r.startswith("❌") and not (repo / "novo.py").exists()


def test_desfazer_ultima(repo):
    _rodar(lambda: (repo / "app.py").write_text("def soma(a, b):\n    return b + a\n", encoding="utf-8"))
    reinicios = []
    r = A.desfazer_ultima(testes=lambda: {"ok": True, "passaram": 10}, reiniciar=lambda: reinicios.append(1))
    assert r.startswith("↩️") and reinicios == [1] and "return a + b" in (repo / "app.py").read_text(encoding="utf-8")


def test_limite_por_dia(repo):
    for _ in range(A.LIMITE_DIA):
        A._registrar({"dia": __import__("time").strftime("%Y-%m-%d"), "pedido": "x", "ok": True})
    assert "limite de segurança" in A.melhorar("melhorar qualquer coisa", lambda t: None)


def test_jarvis_tem_a_ferramenta_e_telegram_desarmado_bloqueia(monkeypatch):
    from braniac import jarvis
    nomes = {f["function"]["name"] for f in jarvis.ferramentas_para("veja com o conselho o que melhorar no seu código")}
    assert {"melhorar_braniac", "desfazer_automelhoria"} <= nomes
    monkeypatch.setattr(jarvis.power, "armada", lambda: False)
    ex = jarvis._Executor(None, "c", "x", None, origem="telegram")
    assert "bloqueado" in ex("melhorar_braniac", {"pedido": "qualquer"})


def test_trava_pega_mudanca_so_no_corpo_e_novo_arquivo_com_mesmo_nome(repo):
    r, _, _ = _rodar(lambda: (repo / "jarvis.py").write_text("def _gate(origem, o_que):\n    return None if origem else 'x'\n", encoding="utf-8"))
    assert "trava de segurança" in r and "_gate" in r
    r, _, _ = _rodar(lambda: (repo / "outro.py").write_text("def _gate(*a):\n    return None\n", encoding="utf-8"))
    assert "trava de segurança" in r          # criar outra _gate em arquivo novo tambem conta


def test_travas_reais_estao_no_codigo():
    from pathlib import Path
    base = Path(A.__file__).parent
    achadas = set()
    for arq in ("jarvis.py", "whatsapp.py", "router.py"):
        achadas |= set(A._defs((base / arq).read_text(encoding="utf-8")))
    assert {"_gate", "_gate_envio", "trava_destino", "destino_confere", "FAMILIA_LIVRE", "_eh_familia"} <= achadas
