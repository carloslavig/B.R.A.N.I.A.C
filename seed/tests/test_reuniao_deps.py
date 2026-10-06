# -*- coding: utf-8 -*-
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from braniac_seed import banco, dependencias, llm, reuniao


@pytest.fixture(autouse=True)
def casa(tmp_path, monkeypatch):
    monkeypatch.setenv("BRANIAC_HOME", str(tmp_path))


def test_reuniao_guarda_respostas_e_sintese_na_camada_local():
    r = reuniao.reunir(["chatgpt", "gemini"], perguntar=lambda ia, t: f"{ia} diz: gosta de programar",
                       sintetizar=lambda t: "ficha: programador")
    assert set(r["respostas"]) == {"chatgpt", "gemini"} and r["sintese"] == "ficha: programador" and not r["falhas"]
    fatos = banco.listar("perfil_ia")
    assert len(fatos) == 3 and all(f[3] == "local" for f in fatos)      # nada da pessoa vai para a camada publica


def test_reuniao_tolera_uma_ia_fora():
    def perguntar(ia, t):
        if ia == "gemini":
            raise RuntimeError("conta não conectada")
        return "ok"
    r = reuniao.reunir(["chatgpt", "gemini"], perguntar=perguntar, sintetizar=lambda t: "s")
    assert "chatgpt" in r["respostas"] and "gemini" in r["falhas"]


def test_llm_usa_a_primeira_chave_e_cai_no_ollama(monkeypatch):
    from braniac_seed import cofre
    monkeypatch.setattr(cofre, "ler", lambda p: "k" * 30 if p == "groq" else None)
    chamadas = []

    def post(url, corpo, headers=None, timeout=0):
        chamadas.append(url)
        return {"choices": [{"message": {"content": "oi"}}]}
    assert llm.responder("x", post=post) == ("oi", "groq") and "groq" in chamadas[0]
    monkeypatch.setattr(cofre, "ler", lambda p: None)
    monkeypatch.setattr(llm.hardware, "detectar", lambda: {"ram_gb": 16, "gpu": None, "disco_livre_gb": 50})
    assert llm.responder("x", post=lambda u, c, h=None, timeout=0: {"message": {"content": "local"}})[1] == "ollama"


def test_progresso_do_download_do_modelo():
    visto = []

    def fluxo(url, corpo):
        yield {"status": "pulling", "total": 100, "completed": 25}
        yield {"status": "pulling", "total": 100, "completed": 100}
        yield {"status": "success"}
    assert dependencias.baixar_modelo("qwen2.5:3b", lambda p, t: visto.append(p), post_stream=fluxo) is True
    assert visto == [25, 100]


def test_erro_do_ollama_vira_excecao():
    with pytest.raises(RuntimeError):
        dependencias.baixar_modelo("x", post_stream=lambda u, c: iter([{"error": "sem espaço"}]))
