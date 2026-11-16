# -*- coding: utf-8 -*-
import pytest
from braniac import criacao


def _pergunta(log):
    def f(ia, texto):
        log.append(ia)
        if ia == "chatgpt":
            raise RuntimeError("fora do ar")
        return "A detailed cinematic prompt of a red house at sunset, warm light, wide shot"
    return f


def test_reuniao_chatgpt_cai_grok_escreve_gemini_melhora_e_motores_em_cascata(tmp_path, monkeypatch):
    monkeypatch.setattr(criacao, "CRIACOES", tmp_path)
    monkeypatch.setattr(criacao, "EXEMPLOS", tmp_path / "sem_exemplos")
    log, chamados = [], []

    def motor(nome, ok=False):
        def f():
            chamados.append(nome)
            if not ok:
                raise criacao.SemCriacao(f"{nome}: limite de imagens do dia")
            return b"\x89PNG..."
        return (nome, f)
    avisos = []
    res = criacao.criar("uma casa vermelha no por do sol", None, avisos.append, perguntar=_pergunta(log),
                        melhorar=lambda p: "IMPROVED: " + "x" * 60, motores=[motor("gemini"), motor("chatgpt"), motor("grok", True), motor("ollama")])
    assert log == ["chatgpt", "grok"]                                   # ChatGPT falhou, o Grok escreveu o 1o prompt
    assert [q for q, _ in res["reuniao"]] == ["grok", "gemini"] and res["prompt"].startswith("IMPROVED")
    assert chamados == ["gemini", "chatgpt", "grok"] and res["motor"] == "grok"   # cota acabou: ChatGPT -> Grok; o Ollama nem foi preciso
    assert res["caminho"].endswith(".png") and (tmp_path / (res["caminho"].split("\\")[-1].split("/")[-1].replace(".png", ".json"))).exists()
    assert any("grok" in a for a in avisos)


def test_pedido_sensivel_e_barrado_e_todos_falham_devolve_o_prompt(tmp_path, monkeypatch):
    monkeypatch.setattr(criacao, "CRIACOES", tmp_path)
    monkeypatch.setattr(criacao, "EXEMPLOS", tmp_path / "x")
    with pytest.raises(criacao.SemCriacao):
        criacao.criar("logo com meu cartao 4111 1111 1111 1111", None, perguntar=lambda i, t: "x" * 50)
    falha = lambda: (_ for _ in ()).throw(criacao.SemCriacao("sem cota"))
    with pytest.raises(criacao.SemCriacao) as e:
        criacao.criar("um gato", None, perguntar=lambda i, t: "a cat prompt " * 5, melhorar=lambda p: "better cat prompt " * 5, motores=[("gemini", falha)])
    assert "Prompt pronto" in str(e.value)


def test_referencias_descritas_localmente_e_video_devolve_so_o_prompt(tmp_path, monkeypatch):
    monkeypatch.setattr(criacao, "EXEMPLOS", tmp_path)
    (tmp_path / "ex1.png").write_bytes(b"\x89PNG....")
    (tmp_path / "nota.txt").write_text("x")
    refs = criacao.referencias()
    assert [p.name for p, _ in refs] == ["ex1.png"]
    vistos = []
    r = criacao.criar_video("um drone sobre a cidade", None, perguntar=lambda i, t: vistos.append(t) or "video prompt " * 6,
                            melhorar=lambda p: "better video prompt " * 5, descrever=lambda d, i, t: "estilo flat, cores quentes")
    assert r["motor"] is None and "better video" in r["prompt"] and "estilo flat" in vistos[0]
