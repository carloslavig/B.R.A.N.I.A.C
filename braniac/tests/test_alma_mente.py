# -*- coding: utf-8 -*-
"""Alma (16/11): nao inventa (checagem local depois do modelo) e puxa conversa sozinha com teto proprio."""
import json
from datetime import datetime

import pytest

from braniac import alma_cuida, alma_mente as am


@pytest.fixture(autouse=True)
def _alma_isolada(tmp_path, monkeypatch):
    for m in (am, alma_cuida):
        monkeypatch.setattr(m, "PASTA", tmp_path / "alma")
    for nome in ("PERFIL", "HUMOR", "LOOPS", "PARAMS"):
        monkeypatch.setattr(am, nome, tmp_path / "alma" / nome.lower())
    monkeypatch.setattr(alma_cuida, "ESTADO", tmp_path / "alma" / "cuida.json")
    monkeypatch.setattr(alma_cuida, "_nome", lambda a: a)
    monkeypatch.setattr(alma_cuida, "_audio_da_alma", lambda *a, **k: None)
    monkeypatch.setattr(alma_cuida.barramento, "enviar", lambda *a, **k: None)


def test_checagem_pega_o_que_nao_veio_do_contexto():
    assert set(am.inventado("Boa sorte na reunião com o Pedro às 15h!", "estou cansado")) >= {"reunião", "Pedro", "15"}
    assert am.inventado("Que bom que a entrevista deu certo, meu bem!", "tenho entrevista amanhã") == ["deu certo"]   # resultado nao contado
    assert am.inventado("E a entrevista de sexta, deu certo?", "tenho entrevista sexta") == []                     # perguntar pode
    assert am.inventado("Ei, querido, respira fundo. Como você está agora, Chefe?", "") == []
    assert am.inventado("Graças a Deus, meu amor. Fala com a Parceira também.", "") == []


def test_compor_descarta_mensagem_inventada():
    inventa = lambda s, u: "Parabéns, meu bem! Amanhã tem a festa da Maria no sábado, aproveita!"
    msg = am.compor("dono", "estou muito estressado", "estresse", llm=inventa)
    assert "Maria" not in msg and "sábado" not in msg and msg            # caiu no texto pronto, que so fala do momento
    bom = "Ei, querido, senti o peso. Respira comigo um pouquinho. O que está pesando mais?"
    assert am.compor("dono", "estou muito estressado", "estresse", llm=lambda s, u: bom) == bom
    assert "Ana" not in am.compor("parceira", "Dono está cansado", "cansaco", llm=lambda s, u: "Oi, a Ana disse que ele está cansado.", quem="Parceira")


def test_mensagem_livre_tambem_e_checada():
    assert "Rio" not in am.mensagem_livre(llm=lambda s, u: "Oi, amor! E aquela viagem pro Rio, como foi?", agora=datetime(2026, 11, 16, 15))


def test_iniciativa_pergunta_como_foi_o_dia_sem_repetir_e_com_teto():
    env = []
    enviar = lambda n, t: env.append((n, t))
    noite = datetime(2026, 11, 16, 19, 0)
    assert am.iniciativa(enviar, noite, llm=lambda s, u: "Oi, meu bem! Como foi o seu dia hoje? Me conta 💗") == ["iniciativa:dia->dono"]
    assert env[0][0] == "dono" and "dia" in env[0][1]
    assert am.iniciativa(enviar, noite.replace(hour=21)) == []                       # intervalo minimo / 'dia' ja perguntado
    assert am.iniciativa(enviar, datetime(2026, 11, 17, 2, 0)) == []                 # madrugada: nunca
    assert am.iniciativa(enviar, datetime(2026, 11, 17, 9, 30), llm=lambda s, u: "x") == ["iniciativa:sono->dono"]   # dia novo: zera; modelo fraco -> texto pronto
    assert "dormiu" in env[-1][1].lower() or "noite" in env[-1][1].lower()
    am.PARAMS.write_text(json.dumps({"iniciativas_dia": 1}), encoding="utf-8")
    assert am.iniciativa(enviar, datetime(2026, 11, 17, 13, 0)) == []                # teto configuravel em parametros.json


def test_iniciativa_retoma_assunto_em_aberto_uma_vez_so():
    am.registrar("tenho entrevista de emprego amanhã e estou ansioso", agora=datetime(2026, 11, 15, 20, 0))
    env = []
    inventa = lambda s, u: "Oi, querido! Que bom que você passou na entrevista, parabéns!"
    fez = am.iniciativa(lambda n, t: env.append(t), datetime(2026, 11, 16, 10, 0), llm=inventa)
    assert fez == ["iniciativa:loop->dono"] and "passou" not in env[0] and "entrevista" in env[0] and "?" in env[0]   # inventou o resultado -> pergunta pronta
    assert am.iniciativa(lambda n, t: env.append(t), datetime(2026, 11, 16, 13, 0)) == ["iniciativa:comida->dono"]   # assunto ja retomado nao volta


def test_perfil_so_guarda_fato_apoiado_nas_frases():
    base = am._plano("hoje fiz um ensaio de fotografia e editei as fotos")
    assert am.apoiado("Faz ensaios de fotografia", base)
    assert not am.apoiado("Joga futebol aos domingos", base)


def test_conquista_e_tarefa_concluida_sempre_tem_resposta(monkeypatch):
    from braniac import alma_cuida
    for frase in ("terminei o site da Cliente", "concluí a tarefa", "entreguei o vídeo", "consegui!", "acabei o relatório"):
        assert am.detectar_estado(frase)["estado"] == "conquista", frase
    assert am.detectar_estado("acabei de chegar em casa")["estado"] != "conquista"
    estado, saidas = {"mente_ultima": __import__("time").time()}, []     # acabou de reagir a outra coisa: o intervalo de 90 min esta valendo
    monkeypatch.setattr(alma_cuida, "_estado", lambda: estado)
    monkeypatch.setattr(alma_cuida, "_salvar", lambda e: None)
    monkeypatch.setattr(alma_cuida, "_mandar", lambda enviar, ap, texto, *a: saidas.append(texto))
    madrugada = __import__("datetime").datetime(2026, 11, 16, 23, 40)
    llm = lambda s, u: "Parabéns, meu bem, você terminou! Estou orgulhosa."
    for _ in range(2):      # duas conquistas seguidas: as duas tem resposta, mesmo fora de hora e dentro do intervalo
        assert am.reagir({"texto": "terminei o site"}, am.detectar_estado("terminei o site"), None, madrugada, llm) == ["conquista->dono"]
    assert len(saidas) == 2
    assert am.reagir({"texto": "to cansado"}, am.detectar_estado("to cansado"), None, madrugada.replace(hour=15), llm) == []   # o resto continua respeitando o intervalo
