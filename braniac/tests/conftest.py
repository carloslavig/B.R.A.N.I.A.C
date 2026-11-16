# -*- coding: utf-8 -*-
"""Nenhum teste pode tocar nos arquivos reais do Jarvis (logs de auditoria, estado, base de conhecimento, fila, pendencias)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import socket

import pytest

_CONNECT = socket.socket.connect
_CONNECT_EX = socket.socket.connect_ex


def _bloquear(endereco):
    """14/10: um teste chegou a tentar o WhatsApp REAL (so nao enviou porque o Chrome estava fechado) -- e a manutencao das 03h roda a suite
    com o Chrome aberto. Agora NENHUM teste fala com o Chrome do agente (9222), o servidor (8765), o Ollama (11434) ou a internet."""
    host, porta = (endereco[0], endereco[1]) if isinstance(endereco, tuple) else (str(endereco), 0)
    if porta in (9222, 8765, 11434) or host not in ("127.0.0.1", "localhost", "::1"):
        raise ConnectionRefusedError(f"[teste] conexao real bloqueada: {host}:{porta}")


def _connect(self, endereco):
    _bloquear(endereco)
    return _CONNECT(self, endereco)


def _connect_ex(self, endereco):
    try:
        _bloquear(endereco)
    except ConnectionRefusedError:
        return 10061
    return _CONNECT_EX(self, endereco)


@pytest.fixture(autouse=True)
def _sem_rede_real(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", _connect)
    monkeypatch.setattr(socket.socket, "connect_ex", _connect_ex)


@pytest.fixture(autouse=True)
def _dados_isolados(tmp_path, monkeypatch):
    from braniac import atender, canal, contexto, dono, memoria, power, revisao, telegram_bot, vigia, whatsapp
    d = tmp_path / "data"
    d.mkdir()
    monkeypatch.setattr(atender, "DATA", d)
    monkeypatch.setattr(atender, "LOG", d / "atendimentos.log")
    monkeypatch.setattr(dono, "DATA", d)
    monkeypatch.setattr(dono, "ARQ", d / "dono_estado.json")
    monkeypatch.setattr(dono, "LOG", d / "dono.log")
    monkeypatch.setattr(whatsapp, "DATA", d)
    monkeypatch.setattr(whatsapp, "PEND_ARQ", d / "wpp_pendentes.json")
    monkeypatch.setattr(canal, "PASTA", d / "canal")
    monkeypatch.setattr(canal, "BATIMENTO", d / "canal" / "claude_presente")
    monkeypatch.setattr(contexto, "ARQ", d / "contexto.json")
    monkeypatch.setattr(telegram_bot, "DATA", d)
    monkeypatch.setattr(power, "DATA", d)
    monkeypatch.setattr(power, "ARQ", d / "estado.json")
    monkeypatch.setattr(memoria, "ARQ", d / "memoria.db")  # banco de memoria isolado em cada teste
    from braniac import recados, rotina
    monkeypatch.setattr(recados, "ARQ", d / "recados.json")   # a fila de recados dos testes nunca toca a real
    monkeypatch.setattr(rotina, "ESTADO", d / "rotina.json")
    from braniac import funil
    monkeypatch.setattr(funil, "ARQ", d / "funil_dono.json")   # fila/resumo dos avisos ao Dono nunca toca a real
    monkeypatch.setattr(funil, "CFG", d / "funil_config.json")
    from braniac import agenda
    monkeypatch.setattr(agenda, "ARQ", d / "agenda.json")      # agenda dos testes nunca toca a real
    monkeypatch.setattr(agenda, "DATA", d)
    from braniac import financeiro
    monkeypatch.setattr(financeiro, "ESTADO", d / "financeiro.json")   # o agente financeiro dos testes nunca toca a conta nem o estado real
    from braniac import vaquinha
    monkeypatch.setattr(vaquinha, "ESTADO", d / "vaquinha.json")
    monkeypatch.setattr(vaquinha, "SITE", d / "vaquinha-site")    # testes nunca tocam o site real nem o banco
    monkeypatch.setattr(vaquinha, "MIN_ENTRE_DEPLOYS_S", 0)
    from braniac import sauraki
    monkeypatch.setattr(sauraki, "DATA", d)            # o escritorio le a pasta de teste, nunca a real
    from braniac import voz_do_dono
    monkeypatch.setattr(voz_do_dono, "PASTA", d / "alma")
    monkeypatch.setattr(voz_do_dono, "AMOSTRAS", d / "alma" / "estilo_amostras.jsonl")
    monkeypatch.setattr(voz_do_dono, "GUIA", d / "alma" / "guia_de_voz.md")
    monkeypatch.setattr(voz_do_dono, "ESTADO", d / "alma" / "voz_estado.json")
    from braniac import automelhoria
    monkeypatch.setattr(automelhoria, "ESTADO", d / "automelhoria.json")
    monkeypatch.setattr(vigia, "FOTO_NA_HORA", False)  # testes nunca leem o WhatsApp real
    monkeypatch.setattr(vigia, "DATA", d)
    monkeypatch.setattr(vigia, "ARQ", d / "vigia_estado.json")
    monkeypatch.setattr(vigia, "LOG", d / "vigia.log")
    monkeypatch.setattr(revisao, "DATA", d)
    from braniac import store
    monkeypatch.setattr(store, "DATA", d)  # voz.log etc. dos testes nao poluem o log real
    monkeypatch.setattr(revisao, "LOG", d / "revisoes.log")
    monkeypatch.setattr(power, "PAUSE_MONITOR", d / "PAUSE")  # os testes nao pausam o monitor de verdade
    # nada de rede/Chrome nos testes: voz e envio de audio viram stubs (o que ja existia cai no fallback de texto)
    from braniac import voz, wpp_voz
    from braniac import ia_web, escuta, sentinela
    monkeypatch.setattr(escuta, "LOG", d / "escuta.log")
    monkeypatch.setattr(escuta, "MODO_ARQ", d / "ui_voz.json")     # modo da tela de voz isolado
    monkeypatch.setattr(escuta, "_janela_voz", lambda: None)       # testes nunca mexem nas janelas reais
    monkeypatch.setattr(sentinela, "LOG", d / "sentinela.log")
    def _sem_ia_real(*a, **k):
        raise ia_web.IAWebErro("testes nunca falam com ChatGPT/Gemini/Grok de verdade")
    monkeypatch.setattr(ia_web, "perguntar", _sem_ia_real)
    monkeypatch.setattr(contexto, "decidir_claude", lambda *a, **k: None)  # testes nunca chamam o Claude de verdade (revisor/decisor de fundo)
    monkeypatch.setattr(voz, "falar_wav", lambda t, permitir_nuvem=True: b"wav")
    monkeypatch.setattr(wpp_voz, "enviar_voz", lambda n, w: "stub: sem envio real")
    from braniac import compasso   # rotinas reais da A.L.M.A. nunca disparam nem sao gravadas nos testes
    monkeypatch.setattr(compasso, "PASTA", d / "compasso")
    monkeypatch.setattr(compasso, "ARQ", d / "compasso" / "rotinas.json")
    monkeypatch.setattr(compasso, "PEDIDOS", d / "compasso" / "pedidos.jsonl")
    from braniac import alma_cuida, barramento, rotina as _rotina   # barramento/Alma/Compasso isolados; nenhum teste manda mensagem de verdade
    monkeypatch.setattr(barramento, "DB", d / "agentes.db")
    monkeypatch.setattr(compasso, "SITUACAO", d / "compasso" / "agentes.json")
    for _n in ("PASTA", "DIARIO", "AMOSTRAS", "ESTILO", "ESTADO"):
        monkeypatch.setattr(alma_cuida, _n, d / "alma" / getattr(alma_cuida, _n).name if _n != "PASTA" else d / "alma")
    monkeypatch.setattr(_rotina, "_enviar", lambda nome, texto: "stub: sem envio real")
    from braniac import jarvis
    jarvis.PENDENTE.clear()  # nenhum teste herda confirmacao/duvida pendente de outro
    yield
    jarvis.PENDENTE.clear()
