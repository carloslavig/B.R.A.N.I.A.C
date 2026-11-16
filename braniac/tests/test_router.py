# -*- coding: utf-8 -*-
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import pytest
from braniac.providers import ProviderError
from braniac.router import Router, TodosFalharam
from braniac.store import Store

CFG = json.loads((Path(__file__).resolve().parents[1] / "providers.json").read_text(encoding="utf-8-sig"))
# a ORDEM da cadeia em producao muda (o mais rapido primeiro); estes testes cobrem a mecanica com uma ordem fixa
_ORDEM_TESTE = ["gemini", "gemini-lite", "gemini-b", "gemini-lite-b", "groq", "groq-20b", "openrouter", "openrouter-gemma", "cerebras", "mistral", "ollama", "claude"]
CFG["roteamento"] = {**CFG.get("roteamento", {}), "ativo": False}   # estes testes cobrem a mecanica com ordem fixa; o roteamento mesclado tem testes proprios
CFG["cadeia"] = sorted(CFG["cadeia"], key=lambda p: _ORDEM_TESTE.index(p["nome"]) if p["nome"] in _ORDEM_TESTE else 99)


def montar(tmp_path, monkeypatch, comportamento, chaves=("GEMINI_API_KEY", "GROQ_API_KEY")):
    import os
    for k in [k for k in os.environ if k.endswith("_API_KEY") or "_API_KEY_" in k]:   # 14/10: chaves reais (ex.: GEMINI_API_KEY_2) vazavam do Jarvis
        monkeypatch.delenv(k, raising=False)
    for k in chaves:
        monkeypatch.setenv(k, "x")
    chamados = []

    def fake(p, msgs, chave, timeout):
        chamados.append((p["nome"], list(msgs)))
        r = comportamento.get(p["nome"], comportamento.get(p["nome"].split("-")[0], "ok"))  # gemini-lite herda do gemini
        if isinstance(r, ProviderError):
            raise r
        return f"resp de {p['nome']}"
    ch = {"openai": fake, "ollama": fake, "cli": fake}
    return Router(cfg=CFG, store=Store(tmp_path / "t.db"), chamadores=ch), chamados


def test_usa_primeiro_online(tmp_path, monkeypatch):
    r, c = montar(tmp_path, monkeypatch, {})
    assert r.responder("a", "oi")[1] == "gemini"
    assert [n for n, _ in c] == ["gemini"]


def test_cota_estourada_passa_pro_proximo_e_mantem_historico(tmp_path, monkeypatch):
    r, c = montar(tmp_path, monkeypatch, {"gemini": ProviderError("429", 900)})
    r.responder("a", "primeira")
    assert r.responder("a", "segunda")[1] == "groq"
    msgs_groq = [m for n, m in c if n == "groq"][-1]
    assert any(m["content"] == "primeira" for m in msgs_groq)  # continuidade
    assert r.store.cooldown("gemini") > 0
    # segunda chamada nem tenta o gemini (esta em descanso)
    assert [n for n, _ in c].count("gemini") == 1


def test_online_esgotado_cai_no_local_depois_claude(tmp_path, monkeypatch):
    r, _ = montar(tmp_path, monkeypatch, {"gemini": ProviderError("429", 900), "groq": ProviderError("429", 900)})
    assert r.responder("a", "oi")[1] == "ollama"
    r2, _ = montar(tmp_path, monkeypatch, {"gemini": ProviderError("429", 900), "groq": ProviderError("429", 900),
                                           "ollama": ProviderError("fora", 60)})
    assert r2.responder("b", "oi")[1] == "claude"


def test_sem_chave_ignora_online(tmp_path, monkeypatch):
    r, c = montar(tmp_path, monkeypatch, {}, chaves=())
    assert r.responder("a", "oi")[1] == "ollama"


def test_sensivel_nunca_vai_pra_online(tmp_path, monkeypatch):
    r, c = montar(tmp_path, monkeypatch, {})
    assert r.responder("a", "meu pix e 123, cpf 123.456.789-09")[1] == "ollama"
    assert all(n in ("ollama", "claude") for n, _ in c)


def test_teto_diario_do_claude(tmp_path, monkeypatch):
    f = ProviderError("x", 60)
    r, _ = montar(tmp_path, monkeypatch, {"gemini": f, "groq": f, "ollama": f})
    r.cfg = dict(CFG, claude_max_por_dia=1)
    assert r.responder("a", "1")[1] == "claude"
    r.store.clear_cooldown("gemini"); r.store.clear_cooldown("groq"); r.store.clear_cooldown("ollama")
    with pytest.raises(TodosFalharam):
        r.responder("a", "2")


def test_todos_falham(tmp_path, monkeypatch):
    f = ProviderError("x", 60)
    r, _ = montar(tmp_path, monkeypatch, {"gemini": f, "groq": f, "ollama": f, "claude": f})
    with pytest.raises(TodosFalharam):
        r.responder("a", "oi")


# ---------- disputa entre provedores (hedging): o lento nao trava o resto ----------

def test_provedor_lento_nao_trava_o_proximo_corre_junto(tmp_path, monkeypatch):
    import time as _t
    r, _ = montar(tmp_path, monkeypatch, {})
    def chamar(p):
        if p["nome"] == "gemini":
            _t.sleep(2.0)                      # lento
            return "lento"
        return "rapido de " + p["nome"]
    t0 = _t.time()
    res, nome = r._disputar(r.cadeia_para(False), chamar, hedge_s=0.1)
    assert res.startswith("rapido") and _t.time() - t0 < 1.0


def test_falha_rapida_passa_ao_proximo_sem_esperar_o_hedge(tmp_path, monkeypatch):
    import time as _t
    r, _ = montar(tmp_path, monkeypatch, {})
    def chamar(p):
        if p["nome"] == "gemini":
            raise ProviderError("503", 300)
        return "ok " + p["nome"]
    t0 = _t.time()
    res, nome = r._disputar(r.cadeia_para(False), chamar, hedge_s=5.0)
    assert nome != "gemini" and _t.time() - t0 < 1.0 and r.store.cooldown("gemini") > 0


def test_todos_falham_levanta_com_o_motivo_de_cada_um(tmp_path, monkeypatch):
    r, _ = montar(tmp_path, monkeypatch, {})
    with pytest.raises(TodosFalharam) as e:
        r._disputar(r.cadeia_para(True), lambda p: (_ for _ in ()).throw(ProviderError("fora", 0)), hedge_s=0.05)
    assert "ollama" in str(e.value)


def test_a_cadeia_de_producao_comeca_pelos_provedores_rapidos():
    real = json.loads((Path(__file__).resolve().parents[1] / "providers.json").read_text(encoding="utf-8-sig"))
    nomes = [p["nome"] for p in real["cadeia"]]
    assert nomes[0].startswith("groq") and nomes.index("groq") < nomes.index("gemini") and real["timeout_s"] <= 20


def test_roteamento_mesclado_pedido_simples_vai_para_modelo_rapido(tmp_path, monkeypatch):
    cfg = {**CFG, "roteamento": {**CFG["roteamento"], "ativo": True}}
    r, c = montar(tmp_path, monkeypatch, {}, chaves=("GEMINI_API_KEY", "GROQ_API_KEY", "CEREBRAS_API_KEY"))
    r.cfg = cfg
    nome = r.responder("s", "que horas sao?")[1]
    assert next(p for p in cfg["cadeia"] if p["nome"] == nome)["classe"] == "rapido"


def test_roteamento_mesclado_pedido_complexo_vai_para_modelo_forte(tmp_path, monkeypatch):
    cfg = {**CFG, "roteamento": {**CFG["roteamento"], "ativo": True}}
    r, c = montar(tmp_path, monkeypatch, {}, chaves=("GEMINI_API_KEY", "GROQ_API_KEY", "CEREBRAS_API_KEY"))
    r.cfg = cfg
    nome = r.responder("s", "analisa pra mim as vantagens e desvantagens de abrir uma segunda loja")[1]
    assert next(p for p in cfg["cadeia"] if p["nome"] == nome)["classe"] == "forte"


def test_roteamento_espalha_o_uso_entre_provedores(tmp_path, monkeypatch):
    cfg = {**CFG, "roteamento": {**CFG["roteamento"], "ativo": True, "limite_dia": 5}}
    r, c = montar(tmp_path, monkeypatch, {}, chaves=("GEMINI_API_KEY", "GROQ_API_KEY", "CEREBRAS_API_KEY"))
    r.cfg = cfg
    usados = {r.responder("s", f"oi {i}")[1] for i in range(8)}
    assert len(usados) >= 2     # nao queima sempre o mesmo provedor gratis


# ---------- latencia por provedor (data/latencia.jsonl) ----------

def test_latencia_mediana_ordena_mesma_classe_e_ordem_desempata(tmp_path, monkeypatch):
    from collections import deque
    cfg = {**CFG, "roteamento": {**CFG["roteamento"], "ativo": True}}
    r, _ = montar(tmp_path, monkeypatch, {})
    r.cfg = cfg
    cadeia = [{"nome": n, "tipo": "online", "classe": "rapido"} for n in ("a", "b", "c", "d")]
    r.lat_ms = {"a": deque([3000, 3000, 100]), "b": deque([900, 1000, 50000]), "c": deque([500]), "d": deque([500])}
    # mediana: c=d=0.5s (empate -> ordem atual), b=1s, a=3s (um pico isolado nao conta)
    assert [p["nome"] for p in r._ordenar(cadeia, "oi")] == ["c", "d", "b", "a"]


def test_latencia_registra_falha_e_fallback_sem_gravar_texto(tmp_path, monkeypatch):
    from braniac import latencia, store
    r, _ = montar(tmp_path, monkeypatch, {"gemini": ProviderError("429", 900)})
    assert r.responder("a", "pergunta secreta do teste xyz")[1] == "groq"
    bruto = (store.DATA / "latencia.jsonl").read_text(encoding="utf-8")
    linhas = [json.loads(l) for l in bruto.splitlines()]
    assert (linhas[0]["provedor"], linhas[0]["ok"]) == ("gemini", False) and (linhas[-1]["provedor"], linhas[-1]["ok"]) == ("groq", True)
    assert all(d["provedor"].startswith("gemini") and not d["ok"] for d in linhas[:-1])   # gemini-lite herda a falha no fake
    assert all(set(d) == {"t", "provedor", "ms", "ok"} for d in linhas)
    assert "secreta" not in bruto and "xyz" not in bruto
    assert "groq" in latencia.carregar() and "gemini" not in latencia.carregar()   # so chamada certa entra na mediana
    assert "groq" in latencia.relatorio()


# ---------- ferramenta escrita como texto pela IA ----------

def test_chamada_de_ferramenta_em_texto_e_reconhecida():
    from braniac.router import chamada_em_texto
    assert chamada_em_texto('{"tool": "resumo_whatsapp", "arguments": {"horas": 3}}') == ("resumo_whatsapp", {"horas": 3})
    assert chamada_em_texto('```json\n{"name": "email", "parameters": {"acao": "nao_lidas"}}\n```') == ("email", {"acao": "nao_lidas"})
    assert chamada_em_texto("Oi, tudo bem?") is None and chamada_em_texto('{"x": 1}') is None
    assert chamada_em_texto('{"tool": "desconhecida", "arguments": {}}', {"resumo_whatsapp"}) is None


def test_json_de_ferramenta_vira_execucao_e_nunca_chega_ao_dono(tmp_path, monkeypatch):
    import os
    for k in [k for k in os.environ if k.endswith("_API_KEY") or "_API_KEY_" in k]:   # 14/10: chaves reais (ex.: GEMINI_API_KEY_2) vazavam do Jarvis
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    passos = []

    def tools_fake(p, msgs, chave, timeout, tools):
        passos.append(len(msgs))
        if len(passos) == 1:      # 1o passo: o modelo escreve a ferramenta como TEXTO
            return {"role": "assistant", "content": '{"tool": "resumo_whatsapp", "arguments": {"horas": 2}}'}
        return {"role": "assistant", "content": "Aqui está o resumo que você pediu."}
    r = Router(cfg=CFG, store=Store(tmp_path / "t.db"), chamadores={"openai": lambda *a, **k: "x"}, chamadores_tools={"openai": tools_fake, "ollama": tools_fake})
    feitos = []
    resp, _ = r.responder_agente("c", "resume o whatsapp", [{"type": "function", "function": {"name": "resumo_whatsapp"}}],
                                 lambda nome, args: feitos.append((nome, args)) or "(mostrado)")
    assert feitos == [("resumo_whatsapp", {"horas": 2})] and resp == "Aqui está o resumo que você pediu." and "{" not in resp


def test_modelo_que_so_repete_json_recebe_resposta_neutra_em_vez_do_json(tmp_path, monkeypatch):
    for k in ("GEMINI_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    tools_fake = lambda p, msgs, chave, timeout, tools: {"role": "assistant", "content": '{"tool": "resumo_whatsapp", "arguments": {}}'}
    r = Router(cfg=CFG, store=Store(tmp_path / "t.db"), chamadores={"openai": lambda *a, **k: "x"}, chamadores_tools={"openai": tools_fake, "ollama": tools_fake})
    resp, _ = r.responder_agente("c", "oi", [{"type": "function", "function": {"name": "resumo_whatsapp"}}], lambda n, a: "ok", max_passos=6)
    assert "tool" not in resp and "{" not in resp
