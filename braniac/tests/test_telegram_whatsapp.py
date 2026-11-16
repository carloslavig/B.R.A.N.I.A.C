# -*- coding: utf-8 -*-
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import pytest
from braniac import contexto, jarvis as t, whatsapp

NOMES = ["Parceira 🤍", "mainha", "Asaas", "Eduarda"]


class R:
    """Router de mentira: responde 'ia' (ou o que for programado) e conta usos do Claude."""
    cfg = {"cadeia": [], "claude_max_por_dia": 20}

    def __init__(self, uso=0, respostas=None):
        self._uso, self.respostas, self.vistos = uso, list(respostas or []), []
        outer = self

        class S:
            def uso_hoje(s, n): return outer._uso
            def add_uso(s, n): outer._uso += 1
        self.store = S()

    def responder(self, c, x):
        self.vistos.append(x)
        return (self.respostas.pop(0) if self.respostas else "ia"), None


@pytest.fixture(autouse=True)
def limpo(tmp_path, monkeypatch):
    t.PENDENTE.clear()
    monkeypatch.setattr(contexto, "ARQ", tmp_path / "contexto.json")  # nao suja a base real
    monkeypatch.setattr(t.power, "pausado", lambda: False)
    monkeypatch.setattr(whatsapp, "listar_nomes", lambda: NOMES)
    monkeypatch.setattr(contexto, "perguntar_claude", lambda *a, **k: None)  # por padrao o Claude "nao sabe"
    yield
    t.PENDENTE.clear()


def test_apelidos_e_busca_sem_acento():
    assert whatsapp.resolver_nome("Parceira", NOMES) == ["Parceira 🤍"]
    assert whatsapp.resolver_nome("parceira", NOMES) == ["Parceira 🤍"]
    assert whatsapp.resolver_nome("Mãe", NOMES) == ["mainha"]
    assert whatsapp.resolver_nome("zzz", NOMES) == []


def test_envio_sai_na_hora_sem_confirmacao(monkeypatch):
    enviados = []
    monkeypatch.setattr(whatsapp, "enviar", lambda n, x: enviados.append((n, x)) or "✅ ok")
    r = t.processar(R(), "manda uma mensagem pra Parceira dizendo que cheguei", "c")[0]
    assert r.startswith("✅") and enviados == [("Parceira 🤍", "cheguei")] and not t.PENDENTE
    t.processar(R(), "/enviar mainha | oi mãe", "c")
    assert enviados[-1] == ("mainha", "oi mãe")


def test_sim_sem_pendencia_vira_conversa_normal():
    assert t.processar(R(), "sim", "c") == ("ia", True)


def test_linguagem_natural_le_whatsapp_sem_ia(monkeypatch):
    monkeypatch.setattr(whatsapp, "nao_lidas", lambda *a: "LISTA")
    monkeypatch.setattr(whatsapp, "ler_conversa", lambda n, *a: f"CONV:{n}")
    for frase in ["Jarvis, olha meu whatsapp pra mim", "tem mensagem nova no zap?", "vê o wpp"]:
        assert t.processar(R(), frase, "c") == ("LISTA", False), frase
    assert t.processar(R(), "lê a conversa da Parceira no whatsapp", "c")[0] == "CONV:Parceira 🤍"
    assert t.processar(R(), "oi, tudo bem?", "c") == ("ia", True)


def test_claude_aciona_direto_sem_pedir_sim(monkeypatch):
    from braniac import claude_agent
    chamadas = []
    monkeypatch.setattr(claude_agent, "executar_em_segundo_plano", lambda tarefa, cb, timeout=600: chamadas.append(tarefa))
    r = R()
    resp = t.processar(r, "pede pro Claude abrir o Airbnb e ver as reservas de hoje", "c")[0]
    assert "Acionei o Claude" in resp and "Confirma?" not in resp     # Dono (07/10): sem pedir sim/nao
    assert chamadas == ["abrir o Airbnb e ver as reservas de hoje"]


def test_claude_respeita_teto():
    assert "teto" in t.processar(R(uso=20), "/claude faz algo", "c")[0]
    assert not t.PENDENTE


def test_desligado_so_aceita_comandos_de_energia(monkeypatch):
    monkeypatch.setattr(t.power, "pausado", lambda: True)
    monkeypatch.setattr(t.power, "estado", lambda: {"pausado": True, "motivo": "manual", "jogo": ""})
    assert "desligado" in t.processar(R(), "olha meu whatsapp", "c")[0].lower()


# ---------- duvidas: sabe -> Claude -> Dono (e aprende) ----------

def test_contato_desconhecido_claude_resolve_e_aprende(monkeypatch):
    monkeypatch.setattr(contexto, "perguntar_claude", lambda *a, **k: "Eduarda")
    monkeypatch.setattr(whatsapp, "enviar", lambda n, x: f"✅ enviado para {n}")
    r = t.processar(R(), "manda pra minha namorada dizendo oi", "c")[0]
    assert "Eduarda" in r and "Confirma?" not in r          # nao incomodou o Dono e ja enviou
    assert contexto.contato("minha namorada") == "Eduarda"  # e guardou


@pytest.fixture(autouse=True)
def _sem_busca_real(monkeypatch):
    monkeypatch.setattr(whatsapp, "buscar_contatos", lambda nome: [])   # nunca abre o WhatsApp de verdade nos testes


def test_contato_desconhecido_nao_lista_nem_pergunta(monkeypatch):
    monkeypatch.setattr(whatsapp, "enviar", lambda n, x: f"✅ enviado para {n}")
    r = t.processar(R(), "manda pro Irmao dizendo bom dia", "c")[0]
    assert "Procurei 'Irmao'" in r and "1)" not in r and "Qual destes" not in r
    assert not t.PENDENTE                                     # nada fica esperando "sim/nao" ou numero


def test_contato_fora_da_lista_e_achado_pela_busca_e_aprendido(monkeypatch):
    enviados = []
    monkeypatch.setattr(whatsapp, "buscar_contatos", lambda nome: ["Manhinha 🏍"])
    monkeypatch.setattr(whatsapp, "enviar", lambda n, x: enviados.append((n, x)) or f"✅ enviado para {n}")
    r = t.processar(R(), "manda pra manhinha dizendo oi, como você está?", "c")[0]
    assert enviados and enviados[0][0] == "Manhinha 🏍" and not t.PENDENTE
    assert contexto.contato("manhinha") == "Manhinha 🏍"       # da proxima vez e direto


def test_duvida_de_contexto_da_ia_vai_pro_claude(monkeypatch):
    monkeypatch.setattr(contexto, "perguntar_claude", lambda *a, **k: "Dono é o dono.")
    r = R(respostas=["[DUVIDA] Quem é o Dono no WhatsApp?", "Entendido, o Dono é o dono."])
    assert t.processar(r, "quem sou eu no zap?", "c") == ("Entendido, o Dono é o dono.", True)
    assert any("Contexto confirmado" in v for v in r.vistos)  # reenviou a pergunta com a resposta junto


def test_duvida_de_contexto_ate_o_dono_e_salva():
    r = R(respostas=["[DUVIDA] Quem é o Irmao?", "Certo, Irmao é seu irmão."])
    resp = t.processar(r, "fala com o Irmao", "c")[0]
    assert "Preciso de uma ajuda sua: Quem é o Irmao?" in resp
    out = t.processar(r, "é meu irmão mais novo", "c")[0]
    assert out == "Certo, Irmao é seu irmão."
    assert "irmão mais novo" in contexto.como_texto()


def test_sem_teto_do_claude_vai_direto_ao_dono():
    r = t.processar(R(uso=20), "manda pro Irmao dizendo oi", "c")[0]
    assert "Procurei 'Irmao'" in r


# ---------- agente com ferramentas ----------

class RAgente(R):
    """Router de mentira com agente: executa uma sequencia pre-programada de chamadas de ferramenta."""
    def __init__(self, passos, **kw):
        super().__init__(**kw)
        self.passos = list(passos)
        self.cfg = {**R.cfg, "autonomia_claude": True}

    def responder_agente(self, conv, texto, tools, executor, max_passos=6):
        self.ferramentas = [x["function"]["name"] for x in tools]
        self.retornos = []
        for nome, args in self.passos[:-1]:
            self.retornos.append(executor(nome, args))
        return self.passos[-1], "fake"


def test_agente_expoe_ferramentas_e_cai_na_whatsapp_sem_vazar_conteudo(monkeypatch):
    monkeypatch.setattr(whatsapp, "nao_lidas", lambda *a: "CONTEUDO PRIVADO DO ZAP")
    r = RAgente([("whatsapp_nao_lidas", {}), "Pronto, é isso."])
    resp, da_ia = t.processar(r, "o que rolou de novo por la?", "c")
    assert resp == "CONTEUDO PRIVADO DO ZAP" and da_ia is False  # so o resultado real; a fala da IA e descartada
    assert "CONTEUDO PRIVADO" not in r.retornos[0]  # a IA (pode ser online) so recebe um stub
    assert {"whatsapp_enviar", "delegar_ao_claude", "consultar_conhecimento", "lembrar"} <= set(r.ferramentas)


def test_agente_envia_na_hora_sem_pedir_sim(monkeypatch):
    enviados = []
    monkeypatch.setattr(whatsapp, "enviar", lambda n, x: enviados.append((n, x)) or "✅ ok")
    r = RAgente([("whatsapp_enviar", {"nome": "Parceira", "texto": "cheguei"}), "Enviei."])
    resp = t.processar(r, "avisa a parceira que cheguei", "c")[0]
    assert enviados == [("Parceira 🤍", "cheguei")] and "Confirma?" not in resp and not t.PENDENTE


def test_agente_chama_claude_sozinho_com_autonomia(monkeypatch):
    from braniac import claude_agent
    feitos, avisos = [], []
    monkeypatch.setattr(claude_agent, "executar_em_segundo_plano", lambda tarefa, cb, timeout=600: feitos.append(tarefa))
    r = RAgente([("delegar_ao_claude", {"tarefa": "ver reservas do Airbnb"}), "Chamei o Claude."])
    resp = t.processar(r, "vê as reservas de hoje no airbnb", "c", avisos.append)[0]
    assert feitos == ["ver reservas do Airbnb"] and resp == "Chamei o Claude." and avisos and "Chamando o Claude" in avisos[0]
    assert r._uso == 1  # conta no teto diario


def test_agente_nunca_pede_confirmacao_para_o_claude(monkeypatch):
    from braniac import claude_agent
    feitos = []
    monkeypatch.setattr(claude_agent, "executar_em_segundo_plano", lambda tarefa, cb, timeout=600: feitos.append(tarefa))
    r = RAgente([("delegar_ao_claude", {"tarefa": "fazer algo"}), "ok"])
    r.cfg = {**r.cfg, "autonomia_claude": False}
    assert "Confirma?" not in t.processar(r, "faz algo", "c")[0] and feitos == ["fazer algo"]


def test_agente_respeita_teto_do_claude():
    r = RAgente([("delegar_ao_claude", {"tarefa": "x"}), "Sem Claude hoje."], uso=20)
    assert t.processar(r, "faz x", "c")[0] == "Sem Claude hoje." and r.retornos[0].startswith("teto diario")


def test_agente_barra_confirmacao_inventada():
    r = RAgente(["Preparei a mensagem para a Parceira. Confirme com /sim."])  # IA nao chamou ferramenta nenhuma
    resp, da_ia = t.processar(r, "algo", "c")
    assert "Não consegui preparar" in resp and "/sim" not in resp.split("Diga assim")[0] and da_ia is False


def test_avisa_a_parceira_que_vira_envio_deterministico(monkeypatch):
    enviados = []
    monkeypatch.setattr(whatsapp, "enviar", lambda n, x: enviados.append((n, x)) or "✅ ok")
    resp = t.processar(R(), "avisa a Parceira que eu cheguei", "c")[0]
    assert resp.startswith("✅") and enviados == [("Parceira 🤍", "eu cheguei")]