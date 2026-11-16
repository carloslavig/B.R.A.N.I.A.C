import re

import pytest

from braniac import projeto_consulta as P


@pytest.fixture(autouse=True)
def isolado(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "ARQ", tmp_path / "consultados.json")
    monkeypatch.setattr(P, "PASTAS", [tmp_path / "Projetos"])
    (tmp_path / "Projetos").mkdir()
    monkeypatch.setattr(P, "_no_banco", lambda nome, texto: False)


def _rodar(texto, **kw):
    log = {"notif": [], "fatos": [], "gpt": [], "claude": []}
    r = P.verificar(texto, lambda p: log["gpt"].append(p) or "e um app de corridas", lambda t, fim: (log["claude"].append(t), fim("achei a pasta X")),
                    log["notif"].append, lambda c, t, f: log["fatos"].append((c, f)), kw.get("sens"))
    return r, log


def test_nome_do_projeto():
    assert P.nome_do_projeto("como esta o projeto Taximetro?") == "Taximetro"
    assert P.nome_do_projeto("abre o app SePique") == "SePique"
    assert P.nome_do_projeto("tenho um projeto novo") is None
    assert P.nome_do_projeto("bom dia, tudo bem?") is None


def test_projeto_desconhecido_pergunta_ao_gpt_e_ao_claude():
    import time
    r, log = _rodar("como esta o projeto Zeta?")
    time.sleep(0.3)
    assert "NAO ha nada" in r and log["claude"] and "SOMENTE LEITURA" in log["claude"][0]
    assert log["gpt"] and {f for _, f in log["fatos"]} == {"gpt", "claude"}
    assert len(log["notif"]) == 2


def test_so_uma_vez_por_dia():
    _rodar("projeto Zeta")
    r, log = _rodar("e o projeto Zeta de novo?")
    assert "ja perguntei" in r and not log["claude"]


def test_pasta_local_ensina_sem_gastar_ia(tmp_path):
    p = tmp_path / "Projetos" / "TaximetroApp"
    p.mkdir()
    (p / "README.md").write_text("Taximetro para motoristas de app", encoding="utf-8")
    r, log = _rodar("fala do projeto Taximetro")
    assert "TaximetroApp" in r and not log["claude"] and not log["gpt"] and log["fatos"][0][1] == "pasta"


def test_dado_sensivel_nao_vai_ao_gpt():
    r, log = _rodar("projeto Zeta senha 1234", sens=re.compile(r"(?i)senha"))
    assert "senha" not in log["gpt"][0] if log["gpt"] else True


def test_mencao_solta_no_banco_nao_conta_como_conhecido(monkeypatch):
    from braniac import banco
    monkeypatch.undo()                                  # volta o _no_banco real
    monkeypatch.setattr(banco, "consultar", lambda *a, **k: ("[fato] Curriculo atualizado: Okara removido; Foundever em destaque", False))
    assert not P._no_banco("Okarã", "")
    monkeypatch.setattr(banco, "consultar", lambda *a, **k: ("[fato] Projeto Okara: plataforma de hospedagens em Next.js", False))
    assert P._no_banco("Okarã", "")


def test_pergunta_sobre_si_nao_vai_aos_agentes():
    from braniac import jarvis
    assert jarvis.SOBRE_SI.search("resumo do que você é e do que o Braniac é, como você foi feito")
    assert jarvis.SOBRE_SI.search("quem é você?")
    assert not jarvis.SOBRE_SI.search("quem é a Layla?")
    assert not jarvis.SOBRE_SI.search("o que você acha da Layla?")
    assert jarvis.SOBRE_SI.search("me explique como você funciona por dentro")
    assert jarvis.SOBRE_SI.search("como você economiza tokens do Claude?")
    assert not jarvis.SOBRE_SI.search("como a Layla funciona no caixa?")


def test_pergunta_nao_abre_modo_profundo():
    from braniac import jarvis
    ex = jarvis._Executor(None, "claude", "como você economiza tokens? Só responda.", None, "web")
    assert "nao abra o modo profundo" in ex("trabalho_profundo", {"objetivo": "x"})
    ex = jarvis._Executor(None, "web", "quanto custa? só responda, não execute nenhuma ação", None, "web")
    assert "nao abra o modo profundo" in ex("trabalho_profundo", {"objetivo": "x"})


def test_lista_de_chamadas_em_texto_nao_vira_resposta():
    from braniac.router import chamada_em_texto
    r = chamada_em_texto('[ {"name": "consultar_lei", "arguments": {"numero": "8078"}}, {"name": "consultar_lei", "arguments": {"numero": "1"}} ]')
    assert r == ("consultar_lei", {"numero": "8078"})


def test_cooldown_com_ate_vazio_nao_quebra(tmp_path):
    from braniac.store import Store
    s = Store(tmp_path / "x.db")
    s.db.execute("INSERT OR REPLACE INTO estado VALUES('p', NULL, '')")
    assert s.cooldown("p") == 0.0
