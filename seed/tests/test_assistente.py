# -*- coding: utf-8 -*-
"""O assistente em si: conversa, acoes dentro das permissoes, confirmacao das perigosas, modo jogo e a transcricao de voz."""
import base64, http.client, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from braniac_seed import assistente, perfil, permissoes, pc_tools, servidor, transcricao


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("BRANIAC_HOME", str(tmp_path))
    assistente.HISTORICO.clear()
    assistente.PENDENTES.clear()
    perfil.atualizar(nome_assistente="Aurora", nome_pessoa="Ana", voz="feminina", concluido=True)
    yield tmp_path


def plano(acao="nenhuma", args=None, resposta="oi"):
    return lambda texto: {"acao": acao, "args": args or {}, "resposta": resposta}


def test_conversa_comum_sem_ferramenta():
    r = assistente.conversar("bom dia", planejar=plano(resposta="Bom dia! Como posso ajudar?"))
    assert r["resposta"] == "Bom dia! Como posso ajudar?" and not r.get("confirmar") and not r.get("ui")
    assert assistente.HISTORICO[-1] == ("ia", "Bom dia! Como posso ajudar?")


def test_texto_vazio_nao_chama_ia():
    def nunca(_):
        raise AssertionError("nao deveria chamar a IA")
    assert assistente.conversar("   ", planejar=nunca) == {"resposta": ""}


def test_ia_fora_do_ar_da_mensagem_amigavel():
    def quebra(_):
        raise RuntimeError("sem conexao")
    r = assistente.conversar("oi", planejar=quebra)
    assert "Não consegui falar com nenhuma IA" in r["resposta"]


def test_ferramenta_inventada_vira_conversa():
    r = assistente.conversar("formata o pc", planejar=plano("formatar_tudo", {}, "Não posso."))
    assert r["resposta"] == "Não posso." and not r.get("confirmar")


def test_acao_sem_permissao_explica_e_nao_executa(monkeypatch):
    chamou = []
    monkeypatch.setattr(pc_tools, "executar_ferramenta", lambda *a: chamou.append(a) or ("x", None))
    r = assistente.conversar("como está o pc?", planejar=plano("status_pc"))
    assert "não liberou" in r["resposta"] and "Configurações" in r["resposta"] and not chamou


def test_acao_segura_liberada_executa_direto():
    permissoes.conceder("sistema.status", com_filhos=True)
    r = assistente.conversar("como está o pc?", planejar=plano("status_pc", {}, "Vou ver."))
    assert "🚫" not in r["resposta"] and r["resposta"] and not r.get("confirmar")


def test_acao_perigosa_pede_confirmacao_e_so_executa_depois(tmp_path):
    permissoes.conceder("arquivos.escrever", com_filhos=True)
    alvo = tmp_path / "nota.txt"
    r = assistente.conversar("anota isso", planejar=plano("escrever_arquivo", {"caminho": str(alvo), "texto": "olá"}, "Posso criar o arquivo?"))
    assert r["confirmar"]["id"] and "escrever_arquivo" in r["confirmar"]["descricao"]
    assert not alvo.exists()                                   # ainda nada aconteceu
    r2 = assistente.confirmar(r["confirmar"]["id"], True)
    assert alvo.read_text(encoding="utf-8") == "olá" and "🚫" not in r2["resposta"]
    assert "expirou" in assistente.confirmar(r["confirmar"]["id"], True)["resposta"]    # id nao vale duas vezes


def test_cancelar_nao_executa(tmp_path):
    permissoes.conceder("arquivos.escrever", com_filhos=True)
    alvo = tmp_path / "nota.txt"
    r = assistente.conversar("anota", planejar=plano("escrever_arquivo", {"caminho": str(alvo), "texto": "x"}))
    assert "Cancelado" in assistente.confirmar(r["confirmar"]["id"], False)["resposta"] and not alvo.exists()


def test_confirmacao_vencida_nao_executa(tmp_path):
    permissoes.conceder("arquivos.escrever", com_filhos=True)
    alvo = tmp_path / "nota.txt"
    r = assistente.conversar("anota", planejar=plano("escrever_arquivo", {"caminho": str(alvo), "texto": "x"}))
    assistente.PENDENTES[r["confirmar"]["id"]]["ate"] = time.time() - 1
    assert "expirou" in assistente.confirmar(r["confirmar"]["id"], True)["resposta"] and not alvo.exists()


def test_permissao_revogada_antes_de_confirmar_bloqueia(tmp_path):
    permissoes.conceder("arquivos.escrever", com_filhos=True)
    alvo = tmp_path / "nota.txt"
    r = assistente.conversar("anota", planejar=plano("escrever_arquivo", {"caminho": str(alvo), "texto": "x"}))
    permissoes.revogar_tudo()
    assert "🚫" in assistente.confirmar(r["confirmar"]["id"], True)["resposta"] and not alvo.exists()


def test_modo_jogo_por_comando_suspende_e_nao_chama_ia():
    r = assistente.conversar("vou jogar um pouco", planejar=plano())
    assert r["ui"] == "suspender" and assistente.suspenso()
    def nunca(_):
        raise AssertionError("suspenso nao pode chamar a IA")
    assert "suspenso" in assistente.conversar("oi", planejar=nunca)["resposta"]
    assistente.definir_suspenso(False)
    assert not assistente.suspenso()


def test_suspender_cancela_confirmacoes_pendentes(tmp_path):
    permissoes.conceder("arquivos.escrever", com_filhos=True)
    r = assistente.conversar("anota", planejar=plano("escrever_arquivo", {"caminho": str(tmp_path / "a.txt"), "texto": "x"}))
    assistente.definir_suspenso(True)
    assert not assistente.PENDENTES and "expirou" in assistente.confirmar(r["confirmar"]["id"], True)["resposta"]


def test_descansar_so_oculta_a_janela():
    r = assistente.conversar("pode descansar", planejar=plano())
    assert r["ui"] == "ocultar" and not assistente.suspenso()


def test_resultado_da_ferramenta_nao_volta_para_a_ia(monkeypatch):
    permissoes.conceder("sistema.status", com_filhos=True)
    vistos = []
    monkeypatch.setattr(pc_tools, "executar_ferramenta", lambda nome, args: ("SEGREDO-DA-FERRAMENTA", None))
    def planejar(texto):
        vistos.append(texto)
        return {"acao": "status_pc", "args": {}, "resposta": ""}
    assistente.conversar("status", planejar=planejar)
    assistente.conversar("e agora?", planejar=planejar)
    assert all("SEGREDO-DA-FERRAMENTA" not in v for v in vistos) and all("SEGREDO-DA-FERRAMENTA" not in t for _, t in assistente.HISTORICO)


def test_prompt_so_lista_ferramentas_liberadas():
    assert "(nenhuma" in assistente.sistema() and "executar(" not in assistente.sistema()
    permissoes.conceder("sistema.status", com_filhos=True)
    s = assistente.sistema()
    assert "status_pc" in s and "executar(" not in s and "Aurora" in s


# ---------- transcricao ----------
def test_transcricao_com_chave_devolve_o_texto():
    d = {"candidates": [{"content": {"parts": [{"text": " abre a calculadora "}]}}]}
    chamadas = []
    def post(url, chave, corpo, timeout=45):
        chamadas.append((url, chave, corpo))
        return d
    assert transcricao.transcrever("QUJD", post=post, chaves=["k1"]) == "abre a calculadora"
    assert chamadas[0][1] == "k1" and "gemini" in chamadas[0][0] and chamadas[0][2]["contents"][0]["parts"][1]["inline_data"]["data"] == "QUJD"


def test_transcricao_inaudivel_vira_vazio():
    post = lambda *a, **k: {"candidates": [{"content": {"parts": [{"text": "[inaudível]"}]}}]}
    assert transcricao.transcrever("QUJD", post=post, chaves=["k"]) == ""


def test_transcricao_tenta_a_proxima_chave():
    def post(url, chave, corpo, timeout=45):
        if chave == "ruim":
            raise RuntimeError("falhou")
        return {"candidates": [{"content": {"parts": [{"text": "oi"}]}}]}
    assert transcricao.transcrever("QUJD", post=post, chaves=["ruim", "boa"]) == "oi"


def test_transcricao_sem_chave_ou_privada_nao_envia():
    with pytest.raises(transcricao.TranscricaoErro):
        transcricao.transcrever("QUJD", post=lambda *a, **k: pytest.fail("nao deveria enviar"), chaves=[])
    perfil.atualizar(voz_privada=True)
    with pytest.raises(transcricao.TranscricaoErro, match="privada"):
        transcricao.transcrever("QUJD", post=lambda *a, **k: pytest.fail("nao deveria enviar"), chaves=["k"])
    assert transcricao.disponivel() is False


# ---------- rotas ----------
@pytest.fixture()
def srv():
    s, porta = servidor.servir(porta=servidor.porta_livre(8950), bloquear=False)
    yield porta
    s.shutdown()


def req(porta, metodo, caminho, corpo=None):
    c = http.client.HTTPConnection("127.0.0.1", porta, timeout=10)
    c.request(metodo, caminho, json.dumps(corpo).encode() if corpo is not None else None, {"Content-Type": "application/json"})
    r = c.getresponse()
    dados = r.read()
    c.close()
    try:
        return r.status, json.loads(dados)
    except ValueError:
        return r.status, dados


def test_raiz_abre_o_assistente_depois_de_concluir_e_o_instalador_antes(srv):
    st, html = req(srv, "GET", "/")
    assert st == 200 and b'id="chat"' in html                      # app.html
    st, html = req(srv, "GET", "/instalacao")
    assert st == 200 and b'id="chat"' not in html and b"BRANIAC" in html
    perfil.atualizar(concluido=False)
    st, html = req(srv, "GET", "/")
    assert b'id="chat"' not in html


def test_modo_jogo_e_chat_pela_api(srv):
    assert req(srv, "POST", "/api/modo-jogo", {"ligado": True}) == (200, {"suspenso": True})
    st, e = req(srv, "GET", "/api/estado")
    assert e["suspenso"] is True and e["concluido"] is True
    st, r = req(srv, "POST", "/api/chat", {"texto": "oi"})
    assert st == 200 and "suspenso" in r["resposta"]
    assert req(srv, "POST", "/api/modo-jogo", {"ligado": False})[1] == {"suspenso": False}


def test_transcrever_sem_chave_devolve_erro_legivel(srv):
    st, r = req(srv, "POST", "/api/transcrever", {"audio": base64.b64encode(b"x").decode()})
    assert st == 200 and r["texto"] == "" and r["erro"]
