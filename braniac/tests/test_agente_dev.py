# -*- coding: utf-8 -*-
"""Agente de programacao plugavel: Claude (padrao), Codex, Gemini, comando proprio ou nenhum. Sem processo real: subprocess.run e falso."""
import subprocess
from types import SimpleNamespace

import pytest

from braniac import agente_dev, automelhoria, dev_livre


@pytest.fixture
def falso(monkeypatch, tmp_path):
    """Registra as chamadas; devolve ok. Isola o arquivo de configuracao e as variaveis de ambiente."""
    for v in ("BRANIAC_AGENTE", "BRANIAC_SEM_CLAUDE", "BRANIAC_AGENTE_CMD"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(agente_dev, "DATA", tmp_path)
    monkeypatch.setattr(agente_dev, "localizar", lambda nome=None: "/bin/" + (nome or agente_dev.escolhido()))
    chamadas = []

    def run(args, **kw):
        chamadas.append((args, kw))
        if "-o" in args:   # codex grava a resposta final no arquivo pedido
            open(args[args.index("-o") + 1], "w", encoding="utf-8").write("feito pelo codex")
        return SimpleNamespace(returncode=0, stdout="saida", stderr="")
    monkeypatch.setattr(agente_dev.subprocess, "run", run)
    return chamadas


def test_padrao_e_claude_e_so_leitura_nao_edita(falso):
    assert agente_dev.escolhido() == "claude"
    cod, txt = agente_dev.rodar("oi")
    args, kw = falso[0]
    assert (cod, txt) == (0, "saida")
    assert args == ["/bin/claude", "-p"] and kw["input"] == "oi"


def test_claude_editando_usa_modo_de_permissao_e_navegador(falso):
    agente_dev.rodar("faz", editar=True, navegador=True, permissao="acceptEdits")
    assert falso[0][0] == ["/bin/claude", "--chrome", "-p", "--permission-mode", "acceptEdits"]


def test_codex_por_variavel_de_ambiente(falso, monkeypatch):
    monkeypatch.setenv("BRANIAC_AGENTE", "codex")
    cod, txt = agente_dev.rodar("faz", workdir="C:/x", editar=True)
    args, kw = falso[0]
    assert (cod, txt) == (0, "feito pelo codex")
    assert args[:2] == ["/bin/codex", "exec"] and "workspace-write" in args and args[-1] == "-"
    assert "AGENTS.md" in kw["input"] and kw["input"].endswith("faz")      # agente que nao le o CLAUDE.md recebe o guia


def test_codex_so_leitura_usa_sandbox_read_only(falso, monkeypatch):
    monkeypatch.setenv("BRANIAC_AGENTE", "codex")
    agente_dev.rodar("responda")
    assert "read-only" in falso[0][0]


def test_config_em_arquivo_e_a_variavel_vence(falso, monkeypatch, tmp_path):
    (tmp_path / "agente_dev.json").write_text('{"agente": "gemini"}', encoding="utf-8")
    assert agente_dev.escolhido() == "gemini"
    monkeypatch.setenv("BRANIAC_AGENTE", "codex")
    assert agente_dev.escolhido() == "codex"
    monkeypatch.setenv("BRANIAC_AGENTE", "inventado")
    assert agente_dev.escolhido() == "claude"


def test_custom_com_placeholder_e_sem_placeholder(falso, monkeypatch):
    monkeypatch.setenv("BRANIAC_AGENTE", "custom")
    monkeypatch.setenv("BRANIAC_AGENTE_CMD", "meucli --ask {prompt}")
    agente_dev.rodar("linha1\nlinha2")
    args, kw = falso[0]
    assert args[:2] == ["meucli", "--ask"] and "\n" not in args[2] and "linha1 linha2" in args[2] and kw["input"] is None
    monkeypatch.setenv("BRANIAC_AGENTE_CMD", "meucli --stdin")
    agente_dev.rodar("oi")
    assert falso[1][1]["input"].endswith("oi")


def test_sem_agente_nao_quebra_e_diz_porque(monkeypatch, tmp_path):
    monkeypatch.setattr(agente_dev, "DATA", tmp_path)
    monkeypatch.setenv("BRANIAC_AGENTE", "nenhum")
    cod, txt = agente_dev.rodar("qualquer")
    assert cod == 127 and "segue funcionando" in txt
    assert agente_dev.perguntar("x") is None and not agente_dev.disponivel()
    monkeypatch.delenv("BRANIAC_AGENTE")
    monkeypatch.setenv("BRANIAC_SEM_CLAUDE", "1")           # compatibilidade com o interruptor antigo
    assert agente_dev.escolhido() == "nenhum"


def test_agente_nao_instalado(monkeypatch, tmp_path):
    monkeypatch.setattr(agente_dev, "DATA", tmp_path)
    monkeypatch.setattr(agente_dev, "localizar", lambda nome=None: None)
    monkeypatch.setenv("BRANIAC_AGENTE", "codex")
    cod, txt = agente_dev.rodar("x")
    assert cod == 127 and "Codex" in txt


def test_tempo_esgotado_devolve_124(falso, monkeypatch):
    def estoura(*a, **k):
        raise subprocess.TimeoutExpired("x", 1, output="parcial")
    monkeypatch.setattr(agente_dev.subprocess, "run", estoura)
    cod, txt = agente_dev.rodar("x", timeout=1)
    assert cod == 124 and "TIMEOUT" in txt


def test_automelhoria_sem_agente_programa_sozinha(monkeypatch):
    monkeypatch.setattr(agente_dev, "disponivel", lambda: False)
    monkeypatch.setattr(dev_livre, "rodar", lambda prompt, timeout=0: (0, "dev_livre fez"))
    assert automelhoria._rodar_claude_padrao("melhore") == (0, "dev_livre fez")
