# -*- coding: utf-8 -*-
import sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from braniac_seed import email_diario as E


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("BRANIAC_HOME", str(tmp_path))
    cofre = {}
    monkeypatch.setattr(E.cofre, "guardar", lambda k, v: cofre.__setitem__(k, v))
    monkeypatch.setattr(E.cofre, "tem", lambda k: k in cofre)
    monkeypatch.setattr(E.cofre, "ler", lambda k: cofre.get(k))
    monkeypatch.setattr(E.cofre, "remover", lambda k: cofre.pop(k, None) is not None)
    return cofre


def msg(i, de, assunto, nao_lida=True, ts=None):
    import time
    return {"id": i, "internalDate": str(int((ts or time.time()) * 1000)), "labelIds": ["UNREAD"] if nao_lida else [],
            "payload": {"headers": [{"name": "From", "value": de}, {"name": "Subject", "value": assunto}]}}


def get_falso(mensagens):
    def get(caminho, params):
        if caminho == "/messages":
            return {"messages": [{"id": m["id"]} for m in mensagens]}
        return next(m for m in mensagens if caminho.endswith(m["id"]))
    return get


def logar(cofre):
    E.configurar(client_id="id.apps.googleusercontent.com", client_secret="segredo")
    cofre["gmail_token"] = "{}"


def test_estado_comeca_desconectado_e_nada_e_do_carlos():
    e = E.estado()
    assert not e["configurado"] and not e["logado"] and e["hora_resumo"] == 7 and e["contatos_aviso"] == []


def test_configurar_guarda_segredo_no_cofre_e_nunca_no_arquivo(ambiente):
    E.configurar(client_id="abc", client_secret="SEGREDO-XYZ", hora_resumo=9)
    assert ambiente["gmail_secret"] == "SEGREDO-XYZ" and "SEGREDO-XYZ" not in E._arq().read_text(encoding="utf-8")
    assert E.estado()["configurado"] and E.estado()["hora_resumo"] == 9
    with pytest.raises(E.EmailErro):
        E.configurar(hora_resumo=30)


def test_login_exige_config_e_so_conclui_com_o_mesmo_state(ambiente):
    with pytest.raises(E.EmailErro):
        E.url_login("http://127.0.0.1:8777/email/callback")
    E.configurar(client_id="abc", client_secret="s")
    url = E.url_login("http://127.0.0.1:8777/email/callback")
    assert "gmail.readonly" in url and "code_challenge_method=S256" in url and "gmail.send" not in url
    with pytest.raises(E.EmailErro):
        E.concluir_login("codigo", "state-errado", post=lambda u, d: {})
    estado = E._PENDENTE["estado"]
    E.concluir_login("codigo", estado, post=lambda u, d: {"access_token": "a", "refresh_token": "r", "expires_in": 3600})
    assert E.estado()["logado"]


def test_promissor_precisa_de_trabalho_e_prazo():
    assert E.promissor("Vaga remota de TI - inscrições até 20/10")[0]
    assert not E.promissor("Vaga remota de TI")[0] and not E.promissor("Promoção: oferta até 20/10 vaga no shopping")[0]


def test_resumo_e_aviso_uma_vez_so_para_a_pessoa(ambiente):
    logar(ambiente)
    ms = [msg("1", "RH Acme <rh@acme.com>", "Vaga remota - inscrições até 20/10"), msg("2", "Loja", "Cupom de desconto", False)]
    g = get_falso(ms)
    r = E.resumo_emails(get=g)
    assert "2 e-mails" in r and "RH Acme" in r and "inscrições até" in r
    avisos = []
    assert E.verificar_promissores(avisos.append, get=g) == 1 and E.verificar_promissores(avisos.append, get=g) == 0
    assert "E-mail de trabalho com prazo" in avisos[0]


def test_tick_so_roda_conectado_na_hora_da_pessoa_e_uma_vez_por_dia(ambiente):
    ms = [msg("1", "Fulano", "Reunião amanhã")]
    saidas = []
    E.tick(datetime(2026, 10, 8, 8), saidas.append, get=get_falso(ms))
    assert not saidas                                                    # desconectado: nada
    logar(ambiente)
    E.configurar(hora_resumo=8)
    E.tick(datetime(2026, 10, 8, 7, 30), saidas.append, get=get_falso(ms))
    assert not saidas                                                    # antes da hora dela
    E.tick(datetime(2026, 10, 8, 8, 5), saidas.append, get=get_falso(ms))
    E.tick(datetime(2026, 10, 8, 9, 5), saidas.append, get=get_falso(ms))
    assert sum("Resumo dos seus e-mails" in s for s in saidas) == 1


def test_modulo_nao_contem_nada_do_carlos_nem_ia_online():
    import inspect
    fonte = inspect.getsource(E).lower()
    assert "carlos" not in fonte.replace("do carlos", "") and "janaina" not in fonte and "groq" not in fonte and "gemini" not in fonte and "openai" not in fonte
