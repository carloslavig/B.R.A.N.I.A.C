# -*- coding: utf-8 -*-
import base64, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import pytest
from braniac import gmail, jarvis, power


def b64(t):
    return base64.urlsafe_b64encode(t.encode("utf-8")).decode().rstrip("=")


class Resp:
    def __init__(self, status=200, corpo=None, texto=""):
        self.status_code, self._c, self.text = status, corpo if corpo is not None else {}, texto

    def json(self):
        return self._c


class FakeHTTP:
    """Simula o Google: guarda as chamadas e responde por rota."""
    def __init__(self):
        self.chamadas, self.msgs, self.token_status, self.lista = [], {}, 200, []

    def post(self, url, data=None, timeout=0):
        self.chamadas.append(("POST", url, data))
        if self.token_status != 200:
            return Resp(self.token_status)
        return Resp(200, {"access_token": "AT" + str(len(self.chamadas)), "expires_in": 3600, "refresh_token": "RT"})

    def get(self, url, params=None, headers=None, timeout=0):
        self.chamadas.append(("GET", url, params))
        if url.endswith("/profile"):
            return Resp(200, {"emailAddress": "dono@exemplo.com"})
        if url.endswith("/messages"):
            return Resp(200, {"messages": [{"id": i} for i in self.lista]})
        return Resp(200, self.msgs[url.rsplit("/", 1)[1]])


@pytest.fixture(autouse=True)
def casa(tmp_path, monkeypatch):
    monkeypatch.setattr(gmail, "ARQ", tmp_path / "gmail.json")
    monkeypatch.setattr(gmail, "DATA", tmp_path)
    fake = FakeHTTP()
    monkeypatch.setattr(gmail, "HTTP", fake)
    gmail.ULTIMA_LISTA.clear()
    return fake


def conectar():
    gmail.definir_cliente("123-abc.apps.googleusercontent.com", "segredo-bem-longo")
    gmail._guardar_token({"access_token": "AT0", "expires_in": 3600, "refresh_token": "RT0"})


def msg(id_, de, assunto, data="Mon, 05 Oct 2026 10:30:00 -0300", rotulos=("UNREAD",), payload_extra=None):
    p = {"headers": [{"name": "From", "value": de}, {"name": "Subject", "value": assunto}, {"name": "Date", "value": data}]}
    p.update(payload_extra or {})
    return {"id": id_, "labelIds": list(rotulos), "payload": p}


# ---------- cliente e login ----------

def test_cliente_invalido_e_recusado():
    with pytest.raises(gmail.GmailErro):
        gmail.definir_cliente("abc", "curto")
    assert not gmail.estado()["cliente"]


def test_url_de_login_e_so_leitura_com_pkce_e_state():
    with pytest.raises(gmail.GmailErro):
        gmail.url_login()
    gmail.definir_cliente("123-abc.apps.googleusercontent.com", "segredo-bem-longo")
    u = gmail.url_login()
    assert "gmail.readonly" in u and "code_challenge_method=S256" in u and "state=" in u and "access_type=offline" in u
    assert "gmail.send" not in u and "gmail.modify" not in u and "mail.google.com" not in u


def test_login_troca_o_codigo_e_guarda_a_conta(casa):
    gmail.definir_cliente("123-abc.apps.googleusercontent.com", "segredo-bem-longo")
    gmail.url_login()
    est = gmail._ler()["estado"]
    gmail.concluir_login("codigo", est)
    e = gmail.estado()
    assert e["logado"] and e["conta"] == "dono@exemplo.com"
    with pytest.raises(gmail.GmailErro):
        gmail.concluir_login("codigo", "estado-errado")        # outro site nao consegue concluir o login


def test_token_vencido_e_renovado_e_falha_vira_mensagem_clara(casa):
    conectar()
    d = gmail._ler()
    d["expira"] = time.time() - 5
    gmail._gravar(d)
    assert gmail._token().startswith("AT")
    d = gmail._ler()
    d["expira"] = time.time() - 5
    gmail._gravar(d)
    casa.token_status = 400
    with pytest.raises(gmail.GmailErro) as e:
        gmail._token()
    assert "expirou" in str(e.value) and "Publicar" in str(e.value)


# ---------- leitura ----------

def test_nao_lidas_mostra_remetente_assunto_e_numera(casa):
    conectar()
    casa.lista = ["a1", "a2"]
    casa.msgs = {"a1": msg("a1", "=?UTF-8?B?Q29uY2VudHJpeA==?= <rh@concentrix.com>", "=?UTF-8?Q?Proposta_de_vaga?="),
                 "a2": msg("a2", "Sebrae <no-reply@sebrae.com.br>", "Curso gratuito", rotulos=())}
    t = gmail.nao_lidas()
    assert "1) 🔵" in t and "Concentrix" in t and "Proposta de vaga" in t and "2) " in t and "Sebrae" in t
    assert gmail.ULTIMA_LISTA == ["a1", "a2"]
    assert "q" in casa.chamadas[0][2] and casa.chamadas[0][2]["q"] == "is:unread in:inbox"


def test_ler_pelo_numero_da_lista_e_texto_simples(casa):
    conectar()
    casa.lista = ["a1"]
    casa.msgs = {"a1": msg("a1", "RH <rh@x.com>", "Vaga", payload_extra={"mimeType": "text/plain", "body": {"data": b64("Olá Dono, temos uma vaga.")}})}
    gmail.nao_lidas()
    t = gmail.ler(1)
    assert "De: RH" in t and "Assunto: Vaga" in t and "temos uma vaga" in t
    with pytest.raises(gmail.GmailErro):
        gmail.ler(7)                        # numero fora da lista


def test_email_em_html_vira_texto_e_mostra_anexos(casa):
    conectar()
    html_ = "<html><style>x{}</style><body><p>Oi <b>Dono</b></p><br>Segue o contrato.</body></html>"
    casa.msgs = {"m9": msg("m9", "Fulano <f@x.com>", "Contrato", payload_extra={
        "mimeType": "multipart/mixed", "parts": [{"mimeType": "text/html", "body": {"data": b64(html_)}}, {"mimeType": "application/pdf", "filename": "contrato.pdf", "body": {}}]})}
    t = gmail.ler("m9")
    assert "Oi Dono" in t and "Segue o contrato" in t and "<b>" not in t and "contrato.pdf" in t


def test_email_longo_e_cortado(casa):
    conectar()
    casa.msgs = {"m1": msg("m1", "A <a@x.com>", "Longo", payload_extra={"mimeType": "text/plain", "body": {"data": b64("palavra " * 1000)}})}
    assert "cortado" in gmail.ler("m1", max_chars=200)


def test_buscar_exige_consulta_e_sem_resultado_avisa(casa):
    conectar()
    with pytest.raises(gmail.GmailErro):
        gmail.buscar("  ")
    casa.lista = []
    assert "nada encontrado" in gmail.buscar("from:ninguem")


def test_sem_login_manda_conectar():
    with pytest.raises(gmail.GmailErro) as e:
        gmail.nao_lidas()
    assert "/email" in str(e.value)


# ---------- o Jarvis ----------

def _fake_gmail(monkeypatch, conectado=True):
    chamadas = []
    monkeypatch.setattr(gmail, "configurado", lambda: conectado)
    monkeypatch.setattr(gmail, "nao_lidas", lambda n=8: chamadas.append(("novos",)) or "E-mails não lidos (1): ...")
    monkeypatch.setattr(gmail, "buscar", lambda q, n=8: chamadas.append(("busca", q)) or f"achei {q}")
    monkeypatch.setattr(gmail, "ler", lambda r, max_chars=2500: chamadas.append(("ler", str(r))) or "De: x")
    return chamadas


def test_perguntas_sobre_email_vao_direto_ao_gmail_sem_ia(monkeypatch):
    ch = _fake_gmail(monkeypatch)
    # router=None: se algum conteudo fosse para uma IA, daria erro
    assert jarvis.processar(None, "Jarvis, tenho e-mail novo?", "c")[0].startswith("E-mails não lidos")
    assert jarvis.processar(None, "procura e-mail da Concentrix", "c")[0] == "achei Concentrix"
    assert jarvis.processar(None, "tem email sobre a vaga de TI?", "c")[0] == "achei a vaga de TI"
    assert jarvis.processar(None, "lê o e-mail 2", "c")[0] == "De: x"
    assert ch == [("novos",), ("busca", "Concentrix"), ("busca", "a vaga de TI"), ("ler", "2")]


def test_so_le_nunca_envia_responde_ou_apaga(monkeypatch):
    ch = _fake_gmail(monkeypatch)
    for frase in ("manda um e-mail pro Pedro dizendo oi", "responde esse email", "apaga o e-mail 3", "encaminha o email do RH pra Parceira"):
        assert "só LEIO" in jarvis.processar(None, frase, "c")[0], frase
    assert ch == []


def test_sem_conectar_explica_como_conectar(monkeypatch):
    _fake_gmail(monkeypatch, conectado=False)
    assert "/email" in jarvis.processar(None, "tenho e-mail novo?", "c")[0]


def test_por_telegram_ou_whatsapp_so_com_a_autonomia_armada(monkeypatch):
    ch = _fake_gmail(monkeypatch)
    monkeypatch.setattr(power, "armada", lambda: False)
    for origem in ("telegram", "whatsapp"):
        assert "Por segurança" in jarvis.processar(None, "tenho e-mail novo?", "c", origem=origem)[0]
    assert ch == []
    monkeypatch.setattr(power, "armada", lambda: True)
    assert jarvis.processar(None, "tenho e-mail novo?", "c", origem="telegram")[0].startswith("E-mails")


def test_email_dentro_de_um_pedido_de_envio_de_whatsapp_nao_vira_leitura(monkeypatch):
    ch = _fake_gmail(monkeypatch)
    enviados = []
    monkeypatch.setattr(jarvis, "_pedir_confirmacao", lambda router, nome, texto, original: enviados.append((nome, texto)) or "✅ enviado")
    monkeypatch.setattr(power, "armada", lambda: True)
    jarvis.processar(None, "manda uma mensagem pra Layla dizendo: confere o e-mail", "c", origem="web")
    assert ch == [] and enviados and enviados[0][0] == "Layla"


def test_ferramenta_email_manda_o_conteudo_direto_ao_dono(monkeypatch):
    ch = _fake_gmail(monkeypatch)
    ex = jarvis._Executor(None, "c", "orig", None, origem="web")
    r = ex("email", {"acao": "buscar", "consulta": "vaga"})
    assert ex.saida_direta == ["achei vaga"] and "nao repita" in r and "achei" not in r    # o texto do e-mail NAO volta para a IA
    assert ch == [("busca", "vaga")]


def test_nada_de_escopo_de_escrita_no_codigo():
    codigo = Path(gmail.__file__).read_text(encoding="utf-8")
    assert "gmail.readonly" in codigo and "gmail.send" not in codigo.replace("NAO envia", "") and "gmail.modify" not in codigo and "/messages/send" not in codigo


def test_envio_de_whatsapp_que_cita_uma_ia_no_texto_nao_vira_pergunta_a_ia(monkeypatch):
    enviados, perguntas = [], []
    monkeypatch.setattr(jarvis, "_pedir_confirmacao_audio", lambda router, nome, texto, original: enviados.append(("audio", nome, texto)) or "✅ enviado")
    monkeypatch.setattr(jarvis, "_pedir_confirmacao", lambda router, nome, texto, original: enviados.append(("texto", nome, texto)) or "✅ enviado")
    monkeypatch.setattr(jarvis, "_consultar_ia_web", lambda ia, p, reuniao=False: perguntas.append(ia) or "resp")
    monkeypatch.setattr(power, "armada", lambda: True)
    jarvis.processar(None, "manda um áudio pra Dono dizendo: o ChatGPT e o Gemini participaram do conselho", "c", origem="web")
    jarvis.processar(None, "manda uma mensagem pra Layla dizendo: pergunta pro Gemini se o site esta no ar", "c", origem="web")
    assert [e[0] for e in enviados] == ["audio", "texto"] and perguntas == []
    # e o pedido direto a uma IA continua funcionando
    jarvis.processar(None, "pergunta pro Grok que dia é hoje no Brasil e qual a data", "c", origem="web")
    assert perguntas == ["grok"]


# ---------- vagas (so remoto, salario >= 5 mil) ----------

def test_avaliar_vaga_criterio_do_dono():
    assert gmail.avaliar_vaga("Vaga 100% remota - Dev Python - Salário: R$ 7.500,00")[0] == "ok"
    assert gmail.avaliar_vaga("Remote Support Engineer - USD 2,000/month")[0] == "ok"        # ~R$ 10 mil
    assert gmail.avaliar_vaga("Fully remote, $60,000 per year")[0] == "ok"
    assert gmail.avaliar_vaga("Remote contractor $30/hour")[0] == "ok"
    assert gmail.avaliar_vaga("Home office - R$ 5k a 6k")[0] == "ok"
    assert gmail.avaliar_vaga("Vaga remota de suporte, R$ 2.500")[0] == "fora"
    assert gmail.avaliar_vaga("Vaga presencial em Cuiabá, R$ 9.000")[0] == "fora"
    assert gmail.avaliar_vaga("Analista híbrido (remoto 2x por semana) R$ 8.000")[0] == "fora"
    assert gmail.avaliar_vaga("Vaga de TI em Cidade, R$ 6.000")[0] == "fora"         # nao diz remota
    assert gmail.avaliar_vaga("Vaga remota de analista de dados")[0] == "sem_salario"


def test_vagas_lista_so_as_boas_e_as_sem_salario(casa):
    conectar()
    corpo = lambda t: {"mimeType": "text/plain", "body": {"data": b64(t)}}
    casa.msgs = {
        "a": msg("a", "LinkedIn <jobs@linkedin.com>", "Vaga remota: Dev Python", payload_extra=corpo("100% remoto. Salário R$ 8.000")),
        "b": msg("b", "Gupy <x@gupy.io>", "Vaga presencial", payload_extra=corpo("Presencial em Cuiabá. R$ 9.000")),
        "c": msg("c", "Indeed <x@indeed.com>", "Remote job", payload_extra=corpo("Remote analyst. Apply now")),
        "d": msg("d", "Catho <x@catho.com.br>", "Vaga remota", payload_extra=corpo("Remoto, R$ 2.000")),
    }
    casa.lista = ["a", "b", "c", "d"]
    r = gmail.vagas()
    assert "Dev Python" in r and "Remote job" in r and "Vaga presencial" not in r
    assert r.index("Dev Python") < r.index("Remote job")
    assert "2 descartados" in r
    assert gmail.ULTIMA_LISTA == ["a", "c"]
    q = [c for c in casa.chamadas if c[1].endswith("/messages")][0][2]["q"]
    assert "newer_than:7d" in q and "-in:sent" in q


def test_pergunta_de_vagas_no_email_vai_direto_ao_filtro(monkeypatch):
    ch = _fake_gmail(monkeypatch)
    monkeypatch.setattr(gmail, "vagas", lambda dias=7, n=25: ch.append(("vagas",)) or "Vagas no e-mail ...")
    assert jarvis.processar(None, "tem vaga nova no meu email?", "c")[0].startswith("Vagas")
    assert jarvis.processar(None, "procura vagas no gmail", "c")[0].startswith("Vagas")
    assert jarvis.processar(None, "tem email sobre a vaga de TI?", "c")[0] == "achei a vaga de TI"
    assert ch == [("vagas",), ("vagas",), ("busca", "a vaga de TI")]
