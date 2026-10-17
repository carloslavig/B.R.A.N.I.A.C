# -*- coding: utf-8 -*-
"""Rede de Braniacs: pareamento por convite, permissao do dono, mensagens assinadas, replay e limites. Dois Braniacs em 127.0.0.1."""
import json, sys, time, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from braniac_seed import rede


@pytest.fixture
def par(tmp_path):
    ouvidas = []
    a = rede.Rede(tmp_path / "a", lambda: "Jarvis", lambda de, t: ouvidas.append(("a", de, t)) or f"Jarvis responde a {de}: {t}", "1.0", porta=18791)
    b = rede.Rede(tmp_path / "b", lambda: "Analisa", lambda de, t: ouvidas.append(("b", de, t)) or f"Analisa responde a {de}: {t}", "1.0", porta=18792)
    assert a.iniciar("127.0.0.1") == "127.0.0.1" and b.iniciar("127.0.0.1") == "127.0.0.1"
    yield a, b, ouvidas
    a.parar()
    b.parar()


def parear(a, b):
    b.aceitar(a.convidar())     # a convida, b aceita


def test_pareado_mas_sem_permissao_nao_conversa(par):
    a, b, _ = par
    parear(a, b)
    with pytest.raises(rede.RedeErro, match="ainda não permitiu"):
        b.falar("Jarvis", "oi")                      # o dono de A ainda nao liberou o B


def test_com_permissao_conversa_e_revogar_corta(par):
    a, b, ouvidas = par
    parear(a, b)
    a.permitir("Analisa")                            # dono de A libera B... (B->A funciona)
    assert b.falar("Jarvis", "olá").startswith("Jarvis responde a Analisa: olá")
    assert ouvidas == [("a", "Analisa", "olá")]
    a.permitir("Analisa", False)
    with pytest.raises(rede.RedeErro, match="ainda não permitiu"):
        b.falar("Jarvis", "oi de novo")


def test_convite_e_de_uso_unico_e_expira(par, tmp_path):
    a, b, _ = par
    codigo = a.convidar()
    b.aceitar(codigo)
    c = rede.Rede(tmp_path / "c", lambda: "Intruso", lambda d, t: "x", porta=18793)
    with pytest.raises(rede.RedeErro, match="inválido ou expirado"):
        c.aceitar(codigo)                            # o mesmo convite nao serve duas vezes
    d = json.loads(a.arq.read_text())
    for conv in d["convites"].values():
        conv["ate"] = 0
    a.arq.write_text(json.dumps(d))
    with pytest.raises(rede.RedeErro):
        c.aceitar(a.convidar().replace("BRN1.", "BRN1.x"))   # lixo nao passa


def test_mensagem_forjada_ou_repetida_e_recusada(par):
    a, b, _ = par
    parear(a, b)
    a.permitir("Analisa")
    pid_b = b._ler()["id"]
    seg = a._ler()["pares"][pid_b]["segredo"]
    ts, nonce = int(time.time()), "n1"

    def enviar(texto, mac, nonce=nonce, ts=ts):
        req = urllib.request.Request("http://127.0.0.1:18791/rede/mensagem", data=json.dumps({"de": pid_b, "ts": ts, "nonce": nonce, "texto": texto, "mac": mac}).encode(), method="POST")
        try:
            return urllib.request.urlopen(req, timeout=5).status
        except urllib.error.HTTPError as e:
            return e.code
    assert enviar("oi", rede._mac(seg, pid_b, ts, nonce, "oi")) == 200
    assert enviar("oi", rede._mac(seg, pid_b, ts, nonce, "oi")) == 403           # repetida (replay)
    assert enviar("outro texto", rede._mac(seg, pid_b, ts, "n2", "oi"), nonce="n2") == 403   # texto trocado
    assert enviar("oi", "0" * 64, nonce="n3") == 403                              # assinatura falsa
    assert enviar("oi", rede._mac(seg, pid_b, ts - 999, "n4", "oi"), nonce="n4", ts=ts - 999) == 403   # antiga


def test_limite_por_minuto(par, monkeypatch):
    a, b, _ = par
    parear(a, b)
    a.permitir("Analisa")
    monkeypatch.setattr(rede, "LIMITE_POR_MIN", 3)
    for i in range(3):
        b.falar("Jarvis", f"m{i}")
    with pytest.raises(rede.RedeErro, match="muitas mensagens"):
        b.falar("Jarvis", "m4")


def test_sem_radmin_nao_abre_porta(tmp_path, monkeypatch):
    monkeypatch.delenv("BRANIAC_REDE_IP", raising=False)
    monkeypatch.setattr(rede, "ip_radmin", lambda: None)
    r = rede.Rede(tmp_path, lambda: "X", lambda d, t: "", porta=18795)
    assert r.iniciar() is None and r.servidor is None
    with pytest.raises(rede.RedeErro, match="Radmin"):
        r.convidar()


def test_ferramentas_do_assistente_de_ponta_a_ponta(tmp_path, monkeypatch):
    """Dois 'computadores' usando as ferramentas reais (rede_local) e a permissao rede.conversar."""
    from braniac_seed import pc_tools, perfil, permissoes, rede_local, llm
    monkeypatch.setenv("BRANIAC_HOME", str(tmp_path / "a"))
    monkeypatch.setenv("BRANIAC_REDE_IP", "127.0.0.1")
    perfil.atualizar(nome_assistente="Jarvis", consentimento_acesso_pc="total")
    permissoes.aplicar_modo("total")
    monkeypatch.setattr(llm, "responder", lambda t, sistema="": (f"eco: {t}", "x"))
    rede_local._R = None
    ra = rede_local.instancia()
    ra.porta = 18801
    # segundo Braniac (Analisa), sem passar pelo estado do primeiro
    rb = rede.Rede(tmp_path / "b", lambda: "Analisa", lambda de, t: "oi do Analisa", "1.0", porta=18802)
    assert rede_local.garantir_servico().servidor is not None and rb.iniciar("127.0.0.1")
    try:
        convite = pc_tools.executar_ferramenta("rede_convidar", {})[0].split("\n")[-1]
        assert convite.startswith("BRN1.")
        rb.aceitar(convite)
        assert "NÃO pode" in pc_tools.executar_ferramenta("rede_listar", {})[0]
        with pytest.raises(rede.RedeErro, match="ainda não permitiu"):
            rb.falar("Jarvis", "oi")
        assert "atualizado" in pc_tools.executar_ferramenta("rede_permitir", {"nome": "Analisa"})[0]
        assert rb.falar("Jarvis", "bom dia") == "eco: bom dia"
        assert pc_tools.precisa_confirmar("rede_falar") and pc_tools.precisa_confirmar("rede_permitir")
    finally:
        ra.parar()
        rb.parar()
        rede_local._R = None
