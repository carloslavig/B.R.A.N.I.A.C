from datetime import datetime

import pytest

from braniac import alma_cuida as A, barramento as B, compasso

MANHA = datetime(2026, 10, 27, 10, 0)
MADRUGADA = datetime(2026, 10, 27, 3, 0)


def test_barramento_entrega_e_recusa_desconhecido():
    i = B.enviar("Jarvis", "Alma", "dono_disse", "oi")
    assert [m["texto"] for m in B.caixa("Alma")] == ["oi"]
    B.responder(B.caixa("Alma")[0], "Alma", "ok")
    assert B.caixa("Alma") == [] and B.caixa("Jarvis")[0]["texto"] == "ok"
    with pytest.raises(ValueError):
        B.enviar("Fulano", "Alma", "x", "y")
    assert i


def test_classifica():
    c = A.classificar
    assert c("meu filho Filho tá com febre")["pessoal"] and c("meu filho Filho tá com febre")["tema"] == "saude"
    assert c("estou passando mal")["urgencia"] == 3
    assert c("quero morrer")["crise"] and c("quero morrer")["urgencia"] == 3
    assert c("estou muito ansioso, piorou")["urgencia"] == 2 and c("estou muito ansioso, piorou")["necessidade"] == "emocional"
    assert c("qual o preço do dólar")["pessoal"] is False and c("qual o preço do dólar")["urgencia"] == 0
    assert c("fiquei triste hoje", {"emocional": 3})["urgencia"] == 2      # recorrencia sobe a urgencia aos poucos


def test_observar_ignora_prompts_internos_e_comandos():
    assert not A.observar("/panico")
    assert not A.observar("OBJETIVO: x ETAPA 1/4 resultados")
    assert A.observar("minha mãe está preocupada comigo")
    assert B.caixa("Alma")[0]["tipo"] == "dono_disse"


def test_urgencia_avisa_parceira_e_crise_avisa_dono(monkeypatch):
    enviados = []
    env = lambda nome, texto: enviados.append((nome, texto))
    monkeypatch.setattr(A, "_nome", lambda ap: ap)
    A.agir({"ts": 1, "texto": "quero morrer"}, A.classificar("quero morrer"), env, agora=MADRUGADA)    # crise vale de madrugada
    assert [n for n, _ in enviados] == ["dono", "parceira"] and "188" in enviados[0][1]


def test_teto_diario_e_horario(monkeypatch):
    enviados = []
    monkeypatch.setattr(A, "_nome", lambda ap: ap)
    c = A.classificar("estou muito ansioso, piorou")
    A.agir({"ts": 1, "texto": "x"}, c, lambda n, t: enviados.append(n), lambda p: "descansa e fala com a Parceira", MADRUGADA)
    assert enviados == []                                         # nao urgente: nada de mensagem de madrugada
    A.agir({"ts": 1, "texto": "x"}, c, lambda n, t: enviados.append((n, t)), lambda p: "descansa e fala com a Parceira", MANHA)
    assert enviados[0][0] == "dono" and "conselho" in enviados[0][1] and "ansios" not in enviados[0][1].lower().split("conselho")[0]
    for _ in range(5):
        A.agir({"ts": 1, "texto": "x"}, c, lambda n, t: enviados.append((n, t)), lambda p: "dica", MANHA)
    assert len(enviados) <= A.TETOS["conselho"]


def test_pergunta_ao_conselho_nao_leva_o_texto_do_dono(monkeypatch):
    vistas = []
    monkeypatch.setattr(A, "_nome", lambda ap: ap)
    A.agir({"ts": 1, "texto": "Filho do colégio X me deixa angustiado, piorou"}, A.classificar("estou muito angustiado, piorou"), lambda n, t: None, lambda p: vistas.append(p) or "dica", MANHA)
    assert vistas and "Filho" not in vistas[0] and "colégio" not in vistas[0]


def test_ciclo_guarda_diario_e_aprende_estilo(monkeypatch):
    monkeypatch.setattr(A, "_nome", lambda ap: ap)
    for i in range(26):
        B.enviar("Jarvis", "Alma", "dono_disse", f"fala jarvis, bora resolver isso rapidão {i}")
    assert A.ciclo(lambda n, t: None) == 10 and A.ciclo(lambda n, t: None) == 10 and A.ciclo(lambda n, t: None) == 6
    assert len(A.DIARIO.read_text(encoding="utf-8").splitlines()) == 26
    assert A.aprender_estilo(lambda s, h, u: "Tom direto e informal, usa 'bora' e 'rapidão', frases curtas e objetivas, sem rodeios.", MANHA)
    assert "bora" in A.ESTILO.read_text(encoding="utf-8") and not A.aprender_estilo(lambda s, h, u: "x" * 80, MANHA)   # so 1x por dia


def test_compasso_acompanha_status_dos_agentes():
    B.enviar("Correio", "Compasso", "status", "conferi a caixa: 2 aviso(s)")
    assert "Correio" in compasso.painel_agentes() and "2 aviso" in compasso.painel_agentes()["Correio"]["texto"]
