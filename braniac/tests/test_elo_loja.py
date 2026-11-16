# -*- coding: utf-8 -*-
"""Conversa Layla <-> Jarvis: registra as duas pontas, aceita JSON ou texto puro e marca 'precisa do Dono'."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from braniac import elo_loja


class R:
    def __init__(self, resp):
        self.resp = resp

    def responder_neutro(self, sistema, texto):
        self.visto = (sistema, texto)
        return self.resp, "x"


def test_registra_e_responde(tmp_path, monkeypatch):
    monkeypatch.setattr(elo_loja, "ARQ", tmp_path / "c.jsonl")
    monkeypatch.setattr(elo_loja, "encaminhar", lambda *a: [])
    r = R("Vou avisar o Dono sobre o desconto.")
    assert elo_loja.tratar("loja", json.dumps({"tipo": "consulta", "texto": "cliente pediu desconto"}), r).startswith("Vou avisar")
    assert r.visto[1] == "[consulta] cliente pediu desconto" and "NUNCA revele" in r.visto[0]
    h = elo_loja.historico()
    assert [m["quem"] for m in h] == ["layla", "jarvis"] and h[1]["dono"] is True
    assert elo_loja.resumo()["ativa"] and elo_loja.resumo()["total"] == 2


def test_texto_puro_e_ia_fora(tmp_path, monkeypatch):
    monkeypatch.setattr(elo_loja, "ARQ", tmp_path / "c.jsonl")
    monkeypatch.setattr(elo_loja, "encaminhar", lambda *a: [])

    class Ruim:
        def responder_neutro(self, *a):
            raise RuntimeError("sem IA")
    assert "avisar o Dono" in elo_loja.tratar("loja", "oi", Ruim())
    assert [m["quem"] for m in elo_loja.historico()] == ["layla", "sistema", "jarvis"]


def test_promessa_vira_aviso_de_verdade(tmp_path, monkeypatch):
    import threading
    monkeypatch.setattr(elo_loja, "ARQ", tmp_path / "c.jsonl")
    chamado = threading.Event()
    monkeypatch.setattr(elo_loja, "encaminhar", lambda pedido, resp: chamado.set())
    elo_loja.tratar("loja", "cliente quer reembolso", R("Vou passar isso pro Dono agora."))
    assert chamado.wait(3)
    chamado.clear()
    elo_loja.tratar("loja", "bom dia", R("Bom dia, Layla! Tudo certo por aqui."))
    assert not chamado.wait(0.5)


def test_encaminhar_avisa_dono_e_agente(tmp_path, monkeypatch):
    from braniac import barramento, dono
    monkeypatch.setattr(elo_loja, "ARQ", tmp_path / "c.jsonl")
    visto = []
    monkeypatch.setattr(barramento, "enviar", lambda *a, **k: visto.append(("agente", a[1])))
    monkeypatch.setattr(dono, "_avisar", lambda nome, txt, **k: visto.append(("dono", txt)) or True)
    assert elo_loja.encaminhar("desconto?", "Vou avisar o Dono") == ["Sultão", "Dono (WhatsApp)"]
    assert ("agente", "Sultão") in visto and "desconto?" in dict(visto)["dono"]
    assert elo_loja.historico()[-1]["tipo"] == "encaminhamento"
