# -*- coding: utf-8 -*-
"""16/11/2026 (Dono): "Jarvis sempre deve me responder no WhatsApp. Sempre... e fazer a tarefa sempre que eu mandar."
Nada do caminho de resposta ao Dono passa pelo funil; IA/revisor fora do ar nao deixa ele sem resposta; pedido de construcao vira tarefa com entrega."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import pytest
from braniac import contexto, dono, funil, jarvis, power, revisor_claude, whatsapp


@pytest.fixture(autouse=True)
def isolado(tmp_path, monkeypatch):
    monkeypatch.setattr(contexto, "ARQ", tmp_path / "contexto.json")
    monkeypatch.setattr(dono, "ARQ", tmp_path / "dono_estado.json")
    monkeypatch.setattr(dono, "LOG", tmp_path / "dono.log")
    monkeypatch.setattr(dono, "DATA", tmp_path)
    monkeypatch.setattr(dono, "ENTREGAS", tmp_path / "entregas")
    monkeypatch.setattr(whatsapp, "PEND_ARQ", tmp_path / "pend.json")
    monkeypatch.setattr(whatsapp, "DATA", tmp_path)
    monkeypatch.setattr(dono.entrelinhas, "observar", lambda t: None)
    from braniac import claude_agent
    monkeypatch.setattr(claude_agent, "executar_em_segundo_plano", lambda *a, **k: None)   # nunca o Claude de verdade
    # o funil e so de aviso AUTOMATICO: se a resposta ao Dono encostar nele, o teste quebra
    for f in ("passar", "envolver", "tick"):
        monkeypatch.setattr(funil, f, lambda *a, **k: (_ for _ in ()).throw(AssertionError("resposta ao Dono passou pelo funil")))


def m(d, t, h="03:10"):
    return {"d": d, "t": t, "c": f"[{h}, 16/11/2026] X: "}


def ler(msgs, sig="1|x"):
    return lambda nome, anterior: None if sig == anterior else {"msgs": msgs, "midias": [], "lista_sig": sig}


SEM_VOZ = dict(falar=lambda n, t: False)


def _env(lista):
    return lambda n, x: lista.append(x) or "✅ ok"


def test_revisor_fora_do_ar_nao_segura_a_resposta(monkeypatch):
    # caso real de 16/11 11h: 'SEGUROU (sem revisor)' e o Dono ficou sem resposta
    monkeypatch.setattr(dono.jarvis, "processar", lambda *a, **k: ("A esteira está rodando, senhor.", False))
    monkeypatch.setattr(revisor_claude, "revisar", lambda *a, **k: {"ok": None, "motivo": "fora", "corrigida": ""})
    env = []
    r = dono.tratar_dono(None, ler=ler([m("ELE", "Como tá a esteira?")]), enviar=_env(env), **SEM_VOZ)
    assert r == "A esteira está rodando, senhor." and env == [r]


def test_revisor_com_erro_tambem_nao_cala(monkeypatch):
    monkeypatch.setattr(dono.jarvis, "processar", lambda *a, **k: ("Tudo certo.", False))
    monkeypatch.setattr(revisor_claude, "revisar", lambda *a, **k: 1 / 0)
    env = []
    assert dono.tratar_dono(None, ler=ler([m("ELE", "E aí?")]), enviar=_env(env), **SEM_VOZ) == "Tudo certo."


def test_ia_falhou_responde_estou_vendo():
    env = []
    r = dono.tratar_dono(None, ler=ler([m("ELE", "Verifica o disco")]), responder=lambda p: 1 / 0, enviar=_env(env), **SEM_VOZ)
    assert r == dono.ESTOU_VENDO and env == [dono.ESTOU_VENDO]


def test_ia_falhou_claude_responde_depois():
    class R:
        cfg = {"claude_max_por_dia": 20}
        class store:
            usos = []
            uso_hoje = staticmethod(lambda k: 0)
            add_uso = staticmethod(lambda k: R.store.usos.append(k))
    feitos, env = [], []
    assert dono._responder_depois(R, "como tá a loja?", "Eu", _env(env), SEM_VOZ["falar"], executar=lambda *a: feitos.append(a))
    prompt, cb = feitos[0][0], feitos[0][1]
    assert "como tá a loja?" in prompt and R.store.usos == ["claude"]
    cb("A loja vendeu bem hoje, senhor.")
    assert env == ["A loja vendeu bem hoje, senhor."]


def test_resposta_de_madrugada_sai_na_hora(monkeypatch):
    # silencio/teto/dedup do funil nao valem para a resposta: a mesma pergunta respondida duas vezes, de madrugada
    env = []
    kw = dict(responder=lambda p: "Tô aqui, senhor.", enviar=_env(env), **SEM_VOZ)
    dono.tratar_dono(None, ler=ler([m("ELE", "Tá aí?")], "A"), **kw)
    dono.tratar_dono(None, ler=ler([m("ELE", "Tá aí?"), m("EU", "Tô aqui, senhor."), m("ELE", "Tá aí?", "03:12")], "B"), **kw)
    assert env == ["Tô aqui, senhor.", "Tô aqui, senhor."]


def test_desistir_ainda_avisa():
    env = []
    falha = lambda n, x: env.append(x) or "erro"
    for s in "ABC":
        dono.tratar_dono(None, ler=ler([m("ELE", "Oi")], s), responder=lambda p: "oi", enviar=falha, **SEM_VOZ)
    dono.tratar_dono(None, ler=ler([m("ELE", "Oi")], "D"), responder=lambda p: "oi", enviar=_env(env), **SEM_VOZ)
    assert env[-1] == dono.ESTOU_VENDO


@pytest.mark.parametrize("t", ["Faz um jogo da velha e me manda", "Jarvis, cria um site pra loja", "monta uma planilha de gastos",
                               "Desenvolve um script que renomeia as fotos"])
def test_eh_tarefa(t):
    assert dono.eh_tarefa(t)


@pytest.mark.parametrize("t", ["Como tá a esteira?", "Faz mais 10 vídeos", "gera uma imagem de praia", "Você consegue fazer um site?",
                               "Verifica o disco", "Obrigado", "faz um vídeo pro site"])
def test_nao_e_tarefa(t):
    assert not dono.eh_tarefa(t)


def test_tarefa_responde_na_hora_e_entrega_o_arquivo():
    feitos, env, arqs = [], [], []
    r = dono.tratar_dono(None, ler=ler([m("ELE", "Faz um jogo da velha e me manda")]), enviar=_env(env), **SEM_VOZ)
    assert r.startswith("Recebi") and env == [r]
    dono._tratar_tarefa(None, "Eu", "Faz um jogo da velha", "s", "l", {}, _env(env), SEM_VOZ["falar"],
                        executar=lambda p, cb: feitos.append((p, cb)), enviar_arquivo=lambda n, c, leg: arqs.append(c) or "✅ enviado")
    prompt, cb = feitos[0]
    pasta = Path(prompt.split("dentro da pasta ")[1].split(" ")[0])
    (pasta / "jogo.html").write_text("<html></html>", encoding="utf-8")
    cb("Fiz o jogo.")
    assert arqs == [str(pasta / "jogo.html")] and env[-1].startswith("Terminei")


def test_tarefa_varios_arquivos_vai_zip_e_falha_avisa():
    feitos, env, arqs = [], [], []
    dono._tratar_tarefa(None, "Eu", "Cria um site", "s", "l", {}, _env(env), SEM_VOZ["falar"],
                        executar=lambda p, cb: feitos.append((p, cb)), enviar_arquivo=lambda n, c, leg: arqs.append(c) or "✅")
    dono._tratar_tarefa(None, "Eu", "Cria um app", "s2", "l", {}, _env(env), SEM_VOZ["falar"],
                        executar=lambda p, cb: feitos.append((p, cb)), enviar_arquivo=lambda n, c, leg: arqs.append(c) or "✅")
    pasta = Path(feitos[0][0].split("dentro da pasta ")[1].split(" ")[0])
    (pasta / "index.html").write_text("a", encoding="utf-8")
    (pasta / "style.css").write_text("b", encoding="utf-8")
    feitos[0][1]("ok")
    assert arqs[0].endswith(".zip")
    feitos[1][1]("Claude terminou com erro (código 1)")
    assert "não consegui terminar" in env[-1]


def test_tarefa_proibida_nao_aciona_o_claude():
    feitos, env = [], []
    r = dono._tratar_tarefa(None, "Eu", "Faz um script que apaga a pasta Downloads", "s", "l", {}, _env(env), SEM_VOZ["falar"],
                            executar=lambda *a: feitos.append(a))
    assert not feitos and "não faço" in r


def test_pc_livre_so_no_chat_do_dono(monkeypatch):
    from braniac import pc
    monkeypatch.setattr(pc, "executar", lambda acao, alvo: f"feito {acao}")
    monkeypatch.setattr(power, "armada", lambda: False)
    dono_ex = jarvis._Executor(None, jarvis.DONO_CONV, "procura o arquivo", None, origem="whatsapp")
    assert dono_ex("pc", {"acao": "procurar", "alvo": "x"}) == "feito procurar" and not dono_ex.saida_direta
    tele = jarvis._Executor(None, "telegram", "procura o arquivo", None, origem="telegram")
    assert "bloqueado" in tele("pc", {"acao": "procurar", "alvo": "x"}) and tele.saida_direta
