# -*- coding: utf-8 -*-
"""v1.1: modulos de agente (financeiro, programacao, loja, saude): escolha na instalacao, banco proprio, detecao local, ferramentas fixas e seguranca."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from braniac_seed import assistente, modulos, perfil


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("BRANIAC_HOME", str(tmp_path))
    assistente.HISTORICO.clear()
    perfil.atualizar(nome_assistente="Luna", nome_pessoa="Ana", voz="feminina", concluido=True)
    yield tmp_path


def plano(acao="nenhuma", args=None, resposta="oi"):
    return lambda texto: {"acao": acao, "args": args or {}, "resposta": resposta}


def test_catalogo_traz_os_quatro_modulos_e_so_os_escolhidos_ficam_ativos():
    ids = {m["id"] for m in modulos.catalogo()}
    assert {"financeiro", "programacao", "loja", "saude"} <= ids
    assert modulos.instalados() == []                       # de fabrica: nenhum (a pessoa escolhe na instalacao)
    modulos.escolher(["financeiro", "saude", "nao-existe"])
    assert [m["id"] for m in modulos.instalados()] == ["financeiro", "saude"]
    assert perfil.carregar()["modulos_escolhidos"] is True
    modulos.desinstalar("saude")
    assert [m["id"] for m in modulos.instalados()] == ["financeiro"]


def test_detecta_so_entre_os_instalados_e_o_contexto_e_curto():
    modulos.escolher(["financeiro"])
    assert modulos.detectar("gastei 35 no mercado")[0][0] == "financeiro"
    assert modulos.detectar("preciso corrigir um bug em python") == []         # programacao nao esta instalado: nao gasta nada
    assert modulos.contexto_para("qual o preco do cardapio") == ""
    ctx = modulos.contexto_para("quanto gastei no mercado?")
    assert "agente Moeda" in ctx and len(ctx) <= 1100


def test_financeiro_anota_resume_meta_desfaz_e_aceita_formatos_brasileiros():
    modulos.escolher(["financeiro"])
    assert "R$ 1.234,56" in modulos.executar("financeiro_registrar", {"valor": "R$ 1.234,56", "categoria": "Aluguel"})
    assert "R$ 35,50" in modulos.executar("financeiro_registrar", {"valor": "35,5", "categoria": "mercado"})
    modulos.executar("financeiro_registrar", {"tipo": "receita", "valor": 3000, "categoria": "salario"})
    r = modulos.executar("financeiro_resumo", {"periodo": "mes"})
    assert "gastos R$ 1.270,06" in r and "receitas R$ 3.000,00" in r and "saldo R$ 1.729,94" in r
    assert "Meta 'viagem'" in modulos.executar("financeiro_meta", {"nome": "viagem", "valor": "3000", "prazo": "2026-12-20"})
    assert "Desfeito" in modulos.executar("financeiro_desfazer", {}) and "gastos R$ 1.270,06" in modulos.executar("financeiro_resumo", {})


def test_financeiro_nunca_guarda_cartao_senha_cpf_e_nao_roda_sem_estar_instalado():
    assert "não está instalado" in modulos.executar("financeiro_registrar", {"valor": "10"})
    modulos.escolher(["financeiro"])
    for ruim in ("cartão 4111 1111 1111 1111", "minha senha é 1234", "cpf 123.456.789-09"):
        assert "não guardo" in modulos.executar("financeiro_registrar", {"valor": "10", "descricao": ruim})
    assert "Não consegui" in modulos.executar("financeiro_registrar", {"valor": "abc"})


def test_modulo_de_terceiros_e_so_dados_sem_codigo_e_sem_ferramenta_inventada(ambiente):
    base = ambiente / "modulos_usuario" / "pets"
    base.mkdir(parents=True)
    ok = {"id": "pets", "nome": "Pets", "agente": "Rex", "descricao": "cuidar dos pets", "instrucao": "Você é o Rex.", "palavras": ["cachorro", "gato", "veterinario"]}
    (base / "manifest.json").write_text(json.dumps(ok), encoding="utf-8")
    assert "pets" in {m["id"] for m in modulos.catalogo()}
    for ruim in ({**ok, "script": "rm -rf /"}, {**ok, "ferramentas": ["apagar_tudo"]}, {**ok, "palavras": ["a"]}, {**ok, "id": "Pets Ruim!"}):
        with pytest.raises(ValueError):
            modulos.validar_manifest(ruim)
    clone = {**ok, "id": "financeiro"}                          # nao substitui um embutido
    (ambiente / "modulos_usuario" / "fin2").mkdir()
    (ambiente / "modulos_usuario" / "fin2" / "manifest.json").write_text(json.dumps(clone), encoding="utf-8")
    assert next(m for m in modulos.catalogo() if m["id"] == "financeiro")["origem"] == "embutido"


def test_assistente_usa_o_agente_certo_e_executa_a_ferramenta_do_modulo(monkeypatch):
    modulos.escolher(["financeiro"])
    r = assistente.conversar("gastei 40 na farmácia", planejar=plano("financeiro_registrar", {"valor": "40", "categoria": "farmacia"}))
    assert "Anotado: gasto de R$ 40,00 em farmacia" in r["resposta"]
    assert "financeiro_registrar" in assistente.sistema() and "Moeda" not in assistente.sistema()   # so a ferramenta; o agente entra por mensagem
    modulos.desinstalar("financeiro")
    assert "financeiro_registrar" not in assistente.sistema()
    r2 = assistente.conversar("gastei 40 na farmácia", planejar=plano("financeiro_registrar", {"valor": "40"}, "ok"))
    assert r2["resposta"] == "ok"                               # sem o modulo, a acao nao executa


def test_validade_e_backup_do_modulo(ambiente):
    from datetime import datetime
    modulos.escolher(["loja"])
    modulos.lembrar("loja", "a", "Hoje não temos refrigerante, só por hoje", agora=datetime(2026, 10, 25, 18, 0))
    modulos.lembrar("loja", "b", "A pizza grande custa 50 reais", agora=datetime(2026, 10, 25, 18, 0))
    c = modulos._db("loja")
    assert c.execute("SELECT validade FROM fatos WHERE chave='a'").fetchone()[0] == datetime(2026, 10, 26, 5, 0).timestamp()
    c.close()
    assert modulos.backup("loja") and list((ambiente / "modulos" / "backup").glob("loja-*.db"))
