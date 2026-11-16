import time

import pytest

from braniac import taxa_sepique as T

DEV = "3f020bc7-6a96-4d0b-800b-e86596be97d9"


@pytest.fixture(autouse=True)
def estado_isolado(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "ESTADO", tmp_path / "taxa_sepique.json")


def pedido(**kw):
    return {"aparelho": DEV, "nome": "Maria da Silva", "valor_centavos": 1234, **kw}


def pix(desc, valor, data=None, hora="10:00"):
    data = data or time.strftime("%Y-%m-%d")      # fixo vencia: o pedido so aceita Pix de ontem em diante
    return {"data": data, "desc": desc, "valor": valor, "hora": hora}


def test_nome_confere_ignora_acento_caixa_e_particulas():
    assert T.nome_confere("Maria da Silva", "Pix MARIA SILVA")
    assert T.nome_confere("José  Antônio", "Pix Jose Antonio Souza")
    assert not T.nome_confere("Maria Silva", "Pix Maria Souza")
    assert not T.nome_confere("Maria", "Pix Maria Silva")          # uma parte so nao basta


def test_validar_recusa_pedido_ruim():
    assert T.validar(pedido())[2] == 1234
    for ruim in (pedido(valor_centavos=999), pedido(valor_centavos=True), pedido(valor_centavos="1234"), pedido(nome="Maria"),
                 pedido(nome="Maria <script>"), pedido(aparelho="x y"), pedido(valor_centavos=10**9)):
        with pytest.raises(ValueError):
            T.validar(ruim)
    with pytest.raises(ValueError):
        T.validar("texto")


def test_reivindicar_e_idempotente_e_status():
    r, code = T.reivindicar(pedido())
    assert code == 200 and r["estado"] == "pendente"
    assert T.reivindicar(pedido())[0]["id"] == r["id"]
    assert T.status(r["id"])[0] == {"estado": "pendente", "valor_centavos": 1234}
    assert T.status("nao-existe")[1] == 404
    assert T.reivindicar(pedido(valor_centavos=50))[1] == 400


def test_limite_de_pendentes_por_aparelho():
    for v in (1000, 1100, 1200):
        assert T.reivindicar(pedido(valor_centavos=v))[1] == 200
    assert T.reivindicar(pedido(valor_centavos=1300))[1] == 429


def test_ciclo_confirma_pix_com_mesmo_nome_e_valor_uma_unica_vez():
    avisos = []
    id_ = T.reivindicar(pedido())[0]["id"]
    movs = [pix("Pix Joao Pereira", 12.34), pix("Pix Maria da Silva Souza", 12.34), pix("Vendas", 12.34)]
    assert T.ciclo(avisos.append, ler=lambda: movs, agora=time.time() + 400) == 1
    assert T.status(id_)[0]["estado"] == "confirmada"
    assert "R$ 12,34" in avisos[0] and "Maria da Silva" in avisos[0]
    # mesmo Pix nao serve a uma segunda solicitacao
    id2 = T.reivindicar(pedido(aparelho="b" * 8))[0]["id"]
    assert T.ciclo(avisos.append, ler=lambda: movs, agora=time.time() + 900) == 0
    assert T.status(id2)[0]["estado"] == "pendente"


def test_valor_diferente_ou_saida_ou_data_antiga_nao_confirma():
    id_ = T.reivindicar(pedido())[0]["id"]
    movs = [pix("Pix Maria da Silva", 12.35), pix("Pix Maria da Silva", -12.34), pix("Pix Maria da Silva", 12.34, data="2026-01-01")]
    assert T.ciclo(None, ler=lambda: movs, agora=time.time() + 400) == 0
    assert T.status(id_)[0]["estado"] == "pendente"


def test_sem_pendente_nao_le_o_banco_e_leitura_tem_intervalo():
    chamadas = []
    assert T.ciclo(None, ler=lambda: chamadas.append(1) or []) == 0 and not chamadas
    T.reivindicar(pedido())
    T.ciclo(None, ler=lambda: chamadas.append(1) or [], agora=time.time() + 10)
    T.ciclo(None, ler=lambda: chamadas.append(1) or [], agora=time.time() + 20)       # < 3 min: nao le de novo
    assert len(chamadas) == 1


def test_expira_sem_pix_em_72h():
    id_ = T.reivindicar(pedido())[0]["id"]
    T.ciclo(None, ler=lambda: [], agora=time.time() + T.EXPIRA_S + 60)
    assert T.status(id_)[0]["estado"] == "nao_encontrada"


def test_falha_na_leitura_nao_derruba_nem_confirma():
    id_ = T.reivindicar(pedido())[0]["id"]

    def quebra():
        raise RuntimeError("sessao caiu")
    assert T.ciclo(None, ler=quebra, agora=time.time() + 400) == 0
    assert T.status(id_)[0]["estado"] == "pendente"


def test_http_real_responde_so_as_rotas_da_taxa(monkeypatch):
    import json
    import urllib.error
    import urllib.request
    monkeypatch.setattr(T, "PORTA", 0)
    srv = T.ThreadingHTTPServer(("127.0.0.1", 0), T._H)
    import threading
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        req = urllib.request.Request(base + "/sepique/taxa/reivindicar", json.dumps(pedido()).encode(), {"Content-Type": "application/json"})
        id_ = json.load(urllib.request.urlopen(req))["id"]
        assert json.load(urllib.request.urlopen(f"{base}/sepique/taxa/status?id={id_}"))["estado"] == "pendente"
        assert json.load(urllib.request.urlopen(base + "/sepique/taxa/saude")) == {"ok": True}
        for caminho in ("/api/status", "/"):
            with pytest.raises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(base + caminho)
            assert e.value.code == 404
        ruim = urllib.request.Request(base + "/sepique/taxa/reivindicar", b"nao e json", {"Content-Type": "application/json"})
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(ruim)
        assert e.value.code == 400
    finally:
        srv.shutdown()
