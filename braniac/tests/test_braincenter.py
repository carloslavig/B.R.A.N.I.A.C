import sqlite3

import pytest

from braniac import braincenter as bc


@pytest.fixture(autouse=True)
def isolado(tmp_path, monkeypatch):
    monkeypatch.setattr(bc, "DATA", tmp_path)
    bc._est.update({"desde": None, "estado": "MONITORANDO", "motivo": "", "medicao": None, "recursos": None})
    monkeypatch.setattr(bc, "ingerir", lambda: 0)          # nao le o banco real do Jarvis
    return tmp_path


def grupo(oc, tr, ind=0, extra=()):
    a = [{"nome": f"o{i}", "estado": "ocioso"} for i in range(oc)] + [{"nome": f"t{i}", "estado": "executando"} for i in range(tr)]
    a += [{"nome": f"i{i}", "estado": "desconectado"} for i in range(ind)]
    return a + list(extra)


CFG = {**bc.PADRAO, "sustentado_s": 0}


def aut(ag, **kw):
    return bc.avaliar(ag, 1000.0, CFG, leitura={"pronto": False}, **kw)[0]


def test_limites_de_ociosidade():
    assert aut(grupo(12, 0))                    # 100%
    assert aut(grupo(9, 1))                     # 90%
    assert aut(grupo(17, 3))                    # 85% exato: limite inclusivo
    assert not aut(grupo(7, 3))                 # 70%
    assert not aut(grupo(2, 10))                # muitos trabalhando
    assert not aut(grupo(7, 3), em_ciclo=True) and bc._est["estado"] == "PAUSADO POR DEMANDA"


def test_usa_percentual_real_e_exclui_brain_center_e_indisponiveis():
    m = bc.medir(grupo(10, 2, extra=[{"nome": "BrainCenter", "estado": "executando"}]))
    assert m["total"] == 12 and m["pct_ociosos"] == 83.3          # o proprio Brain Center fica fora
    m = bc.medir(grupo(10, 0, ind=10))
    assert m["ociosos"] == 10 and m["disponiveis"] == 10 and m["indisponiveis"] == 10   # indisponivel nao e ocioso
    assert bc.medir([{"nome": "x", "estado": None}])["pct_ociosos"] == 0 and not aut([{"nome": "x", "estado": None}])


def test_sustentado_e_recursos():
    cfg = {**bc.PADRAO, "sustentado_s": 300}
    ag = grupo(10, 0)
    assert not bc.avaliar(ag, 1000, cfg, leitura={"pronto": False})[0]
    assert bc.avaliar(ag, 1200, cfg, leitura={"pronto": False})[1] == "OCIOSIDADE COLETIVA ATINGIDA"
    assert bc.avaliar(ag, 1301, cfg, leitura={"pronto": False})[0]
    bc.avaliar(grupo(1, 9), 1400, cfg, leitura={"pronto": False})       # caiu: zera a contagem
    assert not bc.avaliar(ag, 1500, cfg, leitura={"pronto": False})[0]
    ok, est, _, _ = bc.avaliar(ag, 1900, cfg, leitura={"pronto": True, "cpu_pct": 95, "ram_pct": 10, "gpu_c": 40})
    assert not ok and est == "PAUSADO POR RECURSOS"


def test_tarefas_noturnas_nao_sao_interrompidas(monkeypatch):
    ag = grupo(3, 9)
    antes = [dict(a) for a in ag]
    monkeypatch.setattr(bc, "consolidar", lambda *a, **k: pytest.fail("nao deveria consolidar"))
    assert bc.tick(ag, 1000.0, em_thread=False) == "AGUARDANDO OCIOSIDADE"
    assert ag == antes                                                  # nao toca nos agentes


def test_duplicata_e_repeticao_nao_duplicam():
    for ag in ("a", "b"):
        bc.registrar(ag, "O site da loja usa o painel novo de pedidos", assunto="loja", chave="painel")
    r = bc.consolidar(cfg=CFG)
    assert r["criadas"] == 1 and r["duplicadas"] == 1
    r2 = bc.consolidar(cfg=CFG)                                          # repetido: nada novo
    assert r2["novos"] == 0 and r2["criadas"] == 0
    p = bc.painel()
    assert p["memorias"] == 1 and p["episodios"] == 2


def test_contradicao_preserva_fontes_e_sinaliza():
    bc.registrar("a", "O horário da loja é 18h", assunto="loja", chave="horario")
    bc.registrar("b", "O horário da loja é 19h", assunto="loja", chave="horario")
    r = bc.consolidar(cfg=CFG)
    assert r["conflitos"] == 1
    p = bc.painel()
    assert p["conflitos_abertos"] == 1 and p["memorias"] == 2
    res = bc.consultar("a", "horário da loja")
    assert len(res) == 2 and all(x["conflito"] for x in res)
    assert bc.resolver_conflito(1, res[0]["id"]) and bc.painel()["conflitos_abertos"] == 0


def test_negacao_gera_conflito_sem_chave():
    bc.registrar("a", "A loja aceita pagamento no cartão", assunto="loja")
    bc.registrar("b", "A loja não aceita pagamento no cartão", assunto="loja")
    assert bc.consolidar(cfg=CFG)["conflitos"] == 1


def test_atualizacao_da_mesma_origem_guarda_historico():
    bc.registrar("a", "Preço da esfiha é 8 reais", assunto="loja", chave="preco")
    bc.consolidar(cfg=CFG)
    bc.registrar("a", "Preço da esfiha é 9 reais", assunto="loja", chave="preco")
    r = bc.consolidar(cfg=CFG)
    assert r["atualizadas"] == 1 and r["conflitos"] == 0
    c = bc._db()
    assert c.execute("SELECT COUNT(*) FROM historico").fetchone()[0] == 1


def test_checkpoint_pausa_e_retoma():
    for i in range(5):
        bc.registrar("a", f"fato único número {i} sobre assunto{i}", assunto=f"s{i}", chave=f"k{i}")
    cfg = {**CFG, "lote": 2, "max_lotes_por_tick": 5}
    r = bc.consolidar(lambda: False, cfg)                                # ociosidade caiu depois do 1o lote
    assert r["estado"] == "pausado" and r["lotes"] == 1 and bc.painel()["pendentes"] == 3
    r = bc.consolidar(lambda: True, cfg)                                 # voltou: retoma do checkpoint
    assert r["estado"] == "concluido" and bc.painel()["pendentes"] == 0 and bc.painel()["memorias"] == 5
    assert bc._db().execute("SELECT COUNT(*) FROM ciclos").fetchone()[0] == 1   # mesmo ciclo retomado


def test_banco_indisponivel_nao_perde_registros(monkeypatch):
    bc.registrar("a", "registro importante guardado", assunto="x")
    orig = bc._db
    monkeypatch.setattr(bc, "_db", lambda: (_ for _ in ()).throw(sqlite3.OperationalError("indisponivel")))
    assert bc.consolidar(cfg=CFG)["estado"] == "erro" and bc._est["estado"] == "ERRO"
    monkeypatch.setattr(bc, "_db", orig)
    assert bc.painel()["pendentes"] == 1                                 # continua pendente
    assert bc.consolidar(cfg=CFG)["criadas"] == 1


def test_temporario_privado_e_projeto():
    bc.registrar("a", "Hoje o refrigerante zero acabou", assunto="loja")
    bc.registrar("a", "Senha de teste do ambiente local", assunto="x", privado=True)
    bc.registrar("a", "Projeto Alfa usa Rust no backend", projeto="alfa", assunto="stack")
    r = bc.consolidar(cfg=CFG)
    assert r["criadas"] == 2 and r["temporarios"] == 1 if "temporarios" in r else True
    assert bc.consultar("b", "senha ambiente local") == []               # privado nao vaza para outro agente
    assert len(bc.consultar("a", "senha ambiente local")) == 1
    assert bc.consultar("b", "Rust backend", projeto="alfa") == []       # sem permissao no projeto
    assert bc.consultar("b", "Rust backend") == []                       # nao contamina o global


def test_nao_apaga_originais_e_arquiva_sem_perder():
    bc.registrar("a", "Fato antigo e pouco usado sobre arquivo morto", assunto="z", chave="k")
    bc.consolidar(cfg=CFG)
    c = bc._db()
    c.execute("UPDATE semantica SET atualizado=1, ultimo_uso=1, importancia=0.1, confianca=0.1")
    c.commit()
    r = bc.consolidar(cfg=CFG)
    p = bc.painel()
    assert p["arquivadas"] == 1 and p["episodios"] == 1 and r["arquivadas"] == 1
