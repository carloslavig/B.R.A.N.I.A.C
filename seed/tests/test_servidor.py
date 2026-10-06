# -*- coding: utf-8 -*-
import http.client, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from braniac_seed import onboarding, perfil, permissoes, servidor


@pytest.fixture()
def srv(tmp_path, monkeypatch):
    monkeypatch.setenv("BRANIAC_HOME", str(tmp_path))
    s, porta = servidor.servir(porta=servidor.porta_livre(8900), bloquear=False)
    yield porta
    s.shutdown()


def req(porta, metodo, caminho, corpo=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", porta, timeout=10)
    h = {"Content-Type": "application/json", **(headers or {})}
    c.request(metodo, caminho, json.dumps(corpo).encode() if corpo is not None else None, h)
    r = c.getresponse()
    dados = r.read()
    c.close()
    try:
        return r.status, json.loads(dados)
    except ValueError:
        return r.status, dados


def test_serve_a_tela_e_o_estado(srv):
    st, html = req(srv, "GET", "/")
    assert st == 200 and b"BRANIAC" in html
    st, e = req(srv, "GET", "/api/estado")
    assert st == 200 and e["etapas"][0] == "boas_vindas" and e["perfil"]["concluido"] is False and e["chaves"] == []


def test_so_o_proprio_pc_acessa(srv):
    assert req(srv, "GET", "/api/estado", headers={"Host": "evil.com"})[0] == 403
    assert req(srv, "POST", "/api/emergencia", {}, headers={"Origin": "https://evil.com"})[0] == 403


def test_nao_le_arquivos_fora_da_pasta_da_tela(srv):
    assert req(srv, "GET", "/..%2f..%2fperfil.json")[0] == 404 and req(srv, "GET", "/../servidor.py")[0] in (404, 400)


def test_consentimento_e_permissoes_pela_api(srv):
    assert req(srv, "POST", "/api/consentimento", {"modo": "granular"})[0] == 200
    req(srv, "POST", "/api/permissao", {"chave": "arquivos.ler", "ativo": True})
    assert permissoes.permitido("arquivos.ler") and not permissoes.permitido("arquivos.apagar")
    req(srv, "POST", "/api/permissao", {"chave": "arquivos", "ativo": False})
    assert not permissoes.permitido("arquivos.ler")
    req(srv, "POST", "/api/emergencia", {})
    assert perfil.carregar()["consentimento_acesso_pc"] == "granular" and not permissoes.liberadas()


def test_chave_curta_nunca_volta_nem_e_guardada(srv):
    st, r = req(srv, "POST", "/api/chave", {"provedor": "google", "chave": "curta"})
    assert st == 200 and r["ok"] is False and "curta" not in json.dumps(r["motivo"]).replace("curta demais", "")


def test_nome_e_voz_obrigatorios_e_concluir_exige_tudo(srv):
    st, r = req(srv, "POST", "/api/nome", {"nome": "Alexa", "voz": "feminina"})
    assert r["ok"] is False
    st, r = req(srv, "POST", "/api/nome", {"nome": "Aurora", "voz": "feminina"})
    assert r["ok"] is True and r["frase"] == "Aurora, tá acordado?"
    st, r = req(srv, "POST", "/api/concluir", {})
    assert r["ok"] is False and "chave" in r["motivo"]          # falta chave e consentimento


def test_sugestao_de_nomes_pela_api(srv):
    st, r = req(srv, "POST", "/api/nome/sugerir", {"gostos": "adoro jogar videogame", "voz": "masculina"})
    assert "Link" in r["nomes"]


def test_rota_desconhecida(srv):
    assert req(srv, "POST", "/api/nao-existe", {})[0] == 404


def test_reuniao_exige_conta_conectada(srv, monkeypatch):
    from braniac_seed import ias_web
    monkeypatch.setattr(ias_web, "logado", lambda ia: False)
    st, r = req(srv, "POST", "/api/reuniao", {})
    assert st == 400 and "conta" in r["erro"].lower()


def test_telegram_pela_api_token_ruim_codigo_e_armar(srv, monkeypatch):
    from braniac_seed import cofre, remoto
    monkeypatch.setattr(cofre, "guardar", lambda p, k: None)
    st, r = req(srv, "POST", "/api/telegram/token", {"token": "lixo"})
    assert r["ok"] is False
    st, r = req(srv, "POST", "/api/remoto/armar", {"minutos": 60})
    assert r["ok"] is False and "pareie" in r["motivo"]          # nao arma sem dono pareado
    st, c = req(srv, "POST", "/api/telegram/codigo", {})
    assert len(c["codigo"]) == 6
    st, e = req(srv, "POST", "/api/telegram/estado", {})
    assert e["pareado"] is False and e["armado"] is False and e["codigo"] == c["codigo"]
    remoto.parar()


def test_estado_geral_inclui_remoto_e_nova_etapa(srv):
    st, e = req(srv, "GET", "/api/estado")
    assert "remoto" in e["etapas"] and e["remoto"]["armado"] is False and "autostart" in e


def test_whatsapp_e_telegram_vem_cedo_e_sao_opcionais(srv):
    st, e = req(srv, "GET", "/api/estado")
    ordem = e["etapas"]
    assert ordem[1] == "chaves" and ordem.index("remoto") <= 3 and ordem.index("remoto") < ordem.index("hardware")
    assert "remoto" in e["opcionais"] and "chaves" not in e["opcionais"] and "nome_voz" not in e["opcionais"]
    # obrigatorios continuam: nada de WhatsApp/Telegram impede concluir
    assert all("whatsapp" not in f.lower() and "telegram" not in f.lower() for f in e["faltando"])
