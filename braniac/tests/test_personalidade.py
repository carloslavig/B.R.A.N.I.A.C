import pytest

from braniac import personalidade as P


@pytest.fixture(autouse=True)
def isolado(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "ARQ", tmp_path / "personalidade.json")


def test_padrao_nao_acrescenta_nada_ao_prompt():
    assert P.bloco() == "" and set(P.niveis().values()) == {5}


def test_mais_e_menos_andam_de_2_em_2():
    assert "empatia de 5 para 7" in P.comando("Jarvis, aumenta a empatia")
    assert "humor de 5 para 3" in P.comando("diminui o humor")
    assert "humor de 3 para 1" in P.comando("menos humor")
    assert "empatia de 7 para 9" in P.comando("seja mais empático")


def test_definir_valor_e_limites():
    assert "formalidade de 5 para 8" in P.comando("coloca a formalidade em 8")
    assert "para 10" in P.comando("empatia no máximo")
    assert "já está em 10/10" in P.comando("mais empatia")
    assert "para 0" in P.comando("humor no mínimo")
    assert P.niveis()["humor"] == 0 and P.niveis()["empatia"] == 10


def test_bloco_descreve_so_o_que_saiu_do_neutro():
    P.comando("humor em 9")
    P.comando("empatia em 1")
    b = P.bloco()
    assert "humor 9/10" in b and "empatia 1/10" in b and "formalidade" not in b


def test_resumo_e_volta_ao_normal():
    P.comando("humor em 9")
    assert "humor 9/10" in P.comando("como está sua personalidade?")
    assert "tudo em 5" in P.comando("volta a personalidade ao normal")
    assert P.bloco() == ""


def test_conversa_comum_nao_dispara():
    for t in ["tenho mais humor hoje do que ontem, vou sair com a Parceira para comer", "qual o humor da Layla?", "o humor do gerente é ruim", "manda mensagem pra Parceira", "mais café"]:
        assert P.comando(t) is None, t
    assert P.niveis()["humor"] == 5


def test_lembrete_so_aparece_fora_do_neutro():
    assert P.lembrete() == ""
    P.comando("humor no máximo")
    assert "humor 10/10" in P.lembrete() and "OBRIGATORIO" in P.lembrete()
