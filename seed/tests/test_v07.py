# -*- coding: utf-8 -*-
"""v0.7: projetos/conversas separados, habilidades, orquestrador de IAs e chamar o assistente pelo nome."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from braniac_seed import assistente, escuta, habilidades, orquestrador, perfil, projetos


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("BRANIAC_HOME", str(tmp_path))
    assistente.HISTORICO.clear()
    escuta.ESTADO.update(estado="dormindo", ultimo="", historico=[])
    escuta._ULTIMA[0] = 0.0
    perfil.atualizar(nome_assistente="Luna", nome_pessoa="Ana", voz="feminina", concluido=True)
    yield tmp_path


def plano(acao="nenhuma", args=None, resposta="oi"):
    return lambda texto: {"acao": acao, "args": args or {}, "resposta": resposta}


def test_conversa_de_projeto_tem_historico_proprio_e_titulo():
    pid = projetos.acao({"acao": "criar_projeto", "nome": "Loja", "instrucoes": "Fale curto."})["novo"]
    c1 = projetos.acao({"acao": "criar_conversa", "projeto": pid})["novo"]
    c2 = projetos.acao({"acao": "criar_conversa", "projeto": pid})["novo"]
    r = assistente.conversar("preço da camiseta", planejar=plano(resposta="R$ 50"), conversa=c1)
    assert r["resposta"] == "R$ 50"
    assert [m["texto"] for m in projetos.mensagens(c1)] == ["preço da camiseta", "R$ 50"] and projetos.mensagens(c2) == []
    assert assistente.HISTORICO == []                       # a conversa geral nao se mistura
    assert any(v["titulo"] == "preço da camiseta" for v in projetos.estado()["conversas"])
    assert projetos.instrucoes(c1) == ("Loja", "Fale curto.")
    projetos.acao({"acao": "arquivar", "id": c2})
    assert c2 not in [v["id"] for v in projetos.estado()["conversas"]]


def test_habilidades_embutidas_e_criadas():
    nomes = [n for n, _, _ in habilidades.listar()]
    assert "orquestrador-de-ias" in nomes and "weekly-review-planning" in nomes
    assert "orquestrar" in habilidades.carregar("orquestrador-de-ias")
    nova = habilidades.criar("Meu Relatório", "quando pedir o relatório da semana", "1. junte\n2. resuma")
    assert nova == "meu-relat-rio" and habilidades.carregar(nova).startswith("# Meu Relatório")
    with pytest.raises(ValueError):
        habilidades.criar("orquestrador de ias", "x", "y")      # nao sobrescreve a embutida
    assert habilidades.carregar("../../etc") is None


def test_orquestrador_divide_em_ias_diferentes_e_junta():
    chamadas = []

    def responder(prompt, sistema="", chaves=None):
        chamadas.append(chaves)
        if "Divida" in sistema:
            return '{"partes": ["pesquisar preços", "montar o plano"]}', "google"
        if "Junte" in sistema:
            return "PLANO FINAL", "google"
        return f"feito por {chaves[0]}", chaves[0]
    o = orquestrador.orquestrar("compare notebooks e monte um plano", responder=responder, provedores=["google", "groq"])
    assert o["resposta"] == "PLANO FINAL" and sorted(q for _, q in o["partes"]) == ["google", "groq"]
    with pytest.raises(ValueError):
        orquestrador.orquestrar("oi", responder=responder, provedores=[])


def test_acao_orquestrar_pelo_assistente(monkeypatch):
    monkeypatch.setattr(orquestrador, "orquestrar", lambda t: {"resposta": "ok", "partes": [("a", "google"), ("b", "groq")]})
    r = assistente.conversar("faz um plano grande", planejar=plano("orquestrar", {"tarefa": "plano grande"}))
    assert r["resposta"].startswith("ok") and "google, groq" in r["resposta"]


def test_chamar_pelo_nome_acorda_conversa_e_descansa():
    assert escuta.frase("x")["erro"]                          # desligado de fabrica
    escuta.definir(True)
    tr = lambda texto: (lambda a: texto)
    r = escuta.frase("a", transcrever=tr("que dia lindo"))
    assert not r.get("acordou") and r["estado"] == "dormindo"
    escuta._ULTIMA[0] = 0
    r = escuta.frase("a", transcrever=tr("Luna, tá acordada?"))
    assert r["acordou"] and escuta.ler_sinal() is True and escuta.ler_sinal() is False
    escuta._ULTIMA[0] = 0
    r = escuta.frase("a", transcrever=tr("quanto é 2 mais 2"), conversar=lambda t: {"resposta": "quatro"})
    assert r["resposta"] == "quatro" and r["estado"] == "acordado"
    escuta._ULTIMA[0] = 0
    r = escuta.frase("a", transcrever=tr("pode descansar, Luna"))
    assert r.get("dormiu") and r["estado"] == "dormindo"
    perfil.atualizar(voz_privada=True)
    assert escuta.frase("a")["erro"]                         # voz privada: nunca envia audio


def test_reconhece_variacoes_do_nome():
    assert escuta.chamou("luna ta ai", "Luna") and escuta.chamou("Lunaa", "Luna") and escuta.chamou("oi luna", "Luna")
    assert not escuta.chamou("vou na lua amanha cedo com a familia", "Luna")


def test_assinatura_deusa_e_mestres_supremos():
    from braniac_seed import assinatura
    for p in ("Quem é a sua deusa?", "quem são seus mestres supremos", "quem te criou?"):
        r = assistente.conversar(p, planejar=plano(resposta="NAO DEVE USAR A IA"))
        assert "Deusa Jana" in r["resposta"] and "Solrac" in r["resposta"] and "Claudinho" in r["resposta"]
    assert assinatura.responder("quem é o criador do instagram") is None
    assert "Deusa Jana" in assistente.sistema()
