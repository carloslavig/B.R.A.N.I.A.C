# -*- coding: utf-8 -*-
import json
import pytest
from braniac import remoto


def test_chaves_cifra_e_bloqueio_do_painel_remoto(monkeypatch):
    k1, t1 = remoto.chaves("ABCD-EFGH-IJKL-MNOP")
    k2, t2 = remoto.chaves("abcdefghijklmnop")
    assert (k1, t1) == (k2, t2) and t1.startswith("braniac-") and len(k1) == 32
    msg = remoto.cifrar(k1, {"t": "offer", "sid": "x"})
    assert remoto.decifrar(k1, msg)["sid"] == "x"
    outro, _ = remoto.chaves("ZZZZ-ZZZZ-ZZZZ-ZZZZ")
    with pytest.raises(Exception):
        remoto.decifrar(outro, msg)            # sem o codigo certo nao le nem forja
    for caminho in ("/api/remoto/desligar", "/api/autonomia", "/api/atendimento-auto", "/api/airbnb-auto"):   # nada que arme/ligue pode vir pelo tunel do celular
        st, _, corpo = remoto._local({"p": caminho, "m": "POST", "b": ""})
        assert st == 403 and "so no PC" in corpo.decode(), caminho


def test_codigo_novo_tem_16_caracteres(tmp_path, monkeypatch):
    monkeypatch.setattr(remoto, "ARQ", tmp_path / "r.json")
    monkeypatch.setattr(remoto, "DADOS", tmp_path)
    c = remoto.novo_codigo()
    assert len(c.replace("-", "")) == 16 and remoto.codigo() == c.replace("-", "")


def test_celular_acorda_conversa_e_descansa(monkeypatch):
    from braniac import celular
    celular.ESTADO.update(acordado=False, ultima=0.0)
    monkeypatch.setattr(celular, "_tocar_texto", lambda r: "AUDIO")
    ouvido = {"t": ""}
    tr = lambda b: ouvido["t"]
    ouvido["t"] = "que dia bonito hoje"
    assert celular.fala(None, "x", transcrever=tr)["estado"] == "dormindo"
    ouvido["t"] = "Jarvis, tá acordado?"
    r = celular.fala(None, "x", transcrever=tr)
    assert r["acordou"] and r["audio"] == "AUDIO" and r["estado"] == "acordado"
    ouvido["t"] = "quanto é dois mais dois"
    assert celular.fala(None, "x", transcrever=tr, tratar=lambda t: "quatro")["resposta"] == "quatro"
    ouvido["t"] = "pode descansar"
    assert celular.fala(None, "x", transcrever=tr)["estado"] == "dormindo"


def test_caminho_relativo_da_ia_vira_busca_pelo_nome(monkeypatch, tmp_path):
    from braniac import wpp_arquivo as A
    f = tmp_path / "meu_curriculo.pdf"
    f.write_bytes(b"x")
    monkeypatch.setattr(A, "_bloqueado", lambda p: False)   # a pasta temporaria do pytest fica em AppData (area protegida)
    monkeypatch.setattr(A, "buscar", lambda nome, limite=1, **k: [f] if nome == "meu_curriculo.pdf" else [])
    assert A.resolver_caminho("curriculos/meu_curriculo.pdf") == str(f.resolve())
    with pytest.raises(A.ArquivoErro):
        A.resolver_caminho("pasta/nao_existe.pdf")


def test_gratis_estende_cadeia_so_com_chave_e_modelos_vivos():
    from braniac import gratis
    cfg = {"cadeia": [{"nome": "groq", "tipo": "online", "url": "https://api.groq.com/openai/v1/chat/completions", "modelo": "openai/gpt-oss-120b"},
                      {"nome": "ollama", "tipo": "local"}]}
    vivos = {"groq": {"openai/gpt-oss-120b", "llama-3.3-70b-versatile", "whisper-large-v3", "openai/gpt-oss-safeguard-20b", "qwen/qwen3.8-27b"}}
    novos = gratis.estender(cfg, env={"GROQ_API_KEY": "x"}, n=3, listar=lambda plat, d, k: vivos.get(plat, set()))
    assert "gratis:groq:openai/gpt-oss-120b" not in novos                      # ja existe na cadeia
    assert any("llama-3.3-70b-versatile" in n for n in novos) and any("qwen3.8" in n for n in novos)   # catalogo + modelo novo de familia forte
    assert not any("whisper" in n or "safeguard" in n for n in novos)         # nao e modelo de conversa
    assert [p["nome"] for p in cfg["cadeia"]][-1] == "ollama"                 # extras entram antes do local/Claude
    assert gratis.estender({"cadeia": []}, env={}, listar=lambda *a: set()) == []    # sem chave: nada
    g = next(p for p in cfg["cadeia"] if "llama-3.3" in p["nome"])
    assert g["limite_min"] == 30 and g["limite_dia"] == 1000


def test_roteador_respeita_limite_por_minuto_e_por_dia():
    from braniac.router import Router
    import time

    class S:
        def uso_hoje(self, n): return 95
        def cooldown(self, n): return 0
        def erro(self, n): return ""
    r = Router(cfg={"cadeia": []}, store=S(), chamadores={})
    ok, motivo = r.disponivel({"nome": "x", "tipo": "local", "limite_dia": 100})
    assert not ok and "diario" in motivo
    r._min["y"] = [time.time()] * 2
    ok, motivo = r.disponivel({"nome": "y", "tipo": "local", "limite_min": 2})
    assert not ok and "minuto" in motivo


def test_roteador_ordena_com_modelos_gratis_sem_limite_conhecido():
    """Regressao (25/10): limite_dia=None nos modelos extras quebrava a ordenacao e o Jarvis respondia 'tive um problema'."""
    from braniac import gratis
    from braniac.router import Router
    cfg = {"cadeia": [{"nome": "ollama", "tipo": "local", "api": "ollama"}], "roteamento": {"preferencia": "rapido"}}
    gratis.estender(cfg, env={"OPENROUTER_API_KEY": "x", "GROQ_API_KEY": "y"}, listar=lambda plat, d, k: {"qwen/qwen3.8-27b", "nvidia/nemotron-3-super-120b-a12b:free", "google/gemma-4-26b-a4b-it:free"})
    assert all(p.get("limite_dia") is not False and "limite_dia" not in p or p["limite_dia"] for p in cfg["cadeia"])
    r = Router(cfg=cfg, store=type("S", (), {"uso_hoje": lambda s, n: 0, "cooldown": lambda s, n: 0, "erro": lambda s, n: ""})(), chamadores={})
    assert r._ordenar(r.cadeia_para(False), "oi")


def test_mensagem_repetida_nos_ultimos_20_min_nao_e_reenviada():
    from datetime import datetime
    from braniac import wpp_arquivo as A
    agora = datetime(2026, 10, 26, 7, 45)
    rec = [{"h": "[07:41, 26/10/2026] Dono:", "t": "Lembrete: Levar Parceira ao trabalho — daqui a 8 min (07:50).\n\nCarro da Parceira"}]
    assert A.duplicada(rec, "Lembrete: Levar Parceira ao trabalho — daqui a 8 min (07:50).", agora)          # a mesma sem a nota
    assert A.duplicada(rec, "Lembrete: Levar Parceira ao trabalho — daqui a 8 min (07:50).\n\nCarro da Parceira", agora)
    assert not A.duplicada(rec, "Lembrete: Buscar Parceira para almoço — daqui a 10 min (13:00).", agora)    # outro assunto
    assert not A.duplicada(rec, "Lembrete: Levar Parceira ao trabalho — daqui a 8 min (07:50).", datetime(2026, 10, 26, 8, 30))   # passou de 20 min
    assert not A.duplicada(rec, "oi", agora)                                                                     # curta demais para comparar
