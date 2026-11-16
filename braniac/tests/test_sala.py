# -*- coding: utf-8 -*-
import time
import pytest
from braniac import sala as S


@pytest.fixture(autouse=True)
def banco(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "DB", tmp_path / "sala.db")
    monkeypatch.setattr(S, "PROPOSTAS", tmp_path / "propostas")
    monkeypatch.setattr(S, "DATA", tmp_path)
    S.ESTADO.update(pausada=False, silenciados=[], ocupada=False, erro="")


def llm_de(falas):
    it = iter(falas)
    return lambda sistema, hist, usuario, post=None: next(it, "[FIM]")


def test_rodada_alterna_alma_e_jarvis_e_para_no_limite_de_4():
    S.registrar("Dono", "Estou cansado hoje.")
    n = S.rodada("g", llm_de(["Dono, respira fundo e come algo gostoso", "Anotei: há pendências leves para amanhã", "Que tal uma pausa de dez minutos",
                              "Posso lembrar de ligar para o Filho", "quinta fala que nao deve existir"]))
    falas = [m for m in S.mensagens() if m["tipo"] == "fala" and m["agente"] != "Dono"]
    assert n == 4 and [m["agente"] for m in falas] == ["A.L.M.A.", "Jarvis", "A.L.M.A.", "Jarvis"]


def test_rodada_encerra_quando_nao_ha_nada_novo():
    assert S.rodada("g", llm_de(["Estou aqui com você, Dono.", "[FIM]"])) == 1


def test_falas_repetidas_encerram_o_laco_ok_entendi():
    r = S.rodada("g", llm_de(["Entendido, vou organizar a rotina do Dono hoje cedo", "Entendido, vou organizar a rotina do Dono hoje cedo também"]))
    assert r == 1 and any("repetir" in m["texto"] for m in S.mensagens() if m["tipo"] == "aviso")


def test_pausa_silencio_e_limite_diario(monkeypatch):
    S.ESTADO["pausada"] = True
    assert S.rodada("g", llm_de(["x" * 30])) == 0
    S.ESTADO.update(pausada=False, silenciados=["A.L.M.A."])
    S.rodada("g", llm_de(["Fala do Jarvis com conteudo proprio e novo aqui."]))
    assert [m["agente"] for m in S.mensagens() if m["tipo"] == "fala"] == ["Jarvis"]
    S.ESTADO["silenciados"] = []
    monkeypatch.setattr(S, "LIMITE_DIARIO", 1)
    assert S.rodada("g", llm_de(["Mais uma fala qualquer sobre outro assunto totalmente diferente."])) == 0     # ja ha 1 fala hoje


def test_ia_local_fora_do_ar_vira_aviso_sem_quebrar():
    def quebra(*a, **k):
        raise ConnectionError("recusada")
    assert S.rodada("g", quebra) == 0
    assert any("Ollama" in m["texto"] for m in S.mensagens() if m["tipo"] == "aviso")


def test_personas_tem_os_limites_e_o_cuidado_pedidos():
    p = S.AGENTES["A.L.M.A."]["persona"]
    for trecho in ("empática", "carinhosa", "afetuosa", "cuidadosa", "Filho", "CVV 188", "NÃO é médica", "dependência"):
        assert trecho in p


def test_proposta_so_vira_texto_e_nunca_aplica_nada(tmp_path):
    nome = S.propor_melhoria("deixar o relatório mais curto", llm=lambda s, h, u, post=None: "Sugestão: encurtar.")
    arq = S.PROPOSTAS / nome
    t = arq.read_text(encoding="utf-8")
    assert "AGUARDANDO APROVAÇÃO" in t and "nada foi aplicado" in t and "A.L.M.A." in t and "Jarvis" in t
    assert S.listar_propostas() == [nome]


def test_acoes_da_tela(monkeypatch):
    monkeypatch.setattr(S, "dono_fala", lambda t: True)
    assert S.acao({"acao": "enviar", "texto": "oi"})["ok"]
    assert S.acao({"acao": "pausar", "ligado": True})["pausada"] and not S.acao({"acao": "pausar", "ligado": False})["pausada"]
    assert S.acao({"acao": "silenciar", "agente": "Jarvis", "ligado": True})["silenciados"] == ["Jarvis"]
    S.registrar("Dono", "x")
    S.acao({"acao": "limpar"})
    assert S.mensagens() == []


def test_sala_nao_importa_whatsapp_nem_ias_online():
    import inspect
    f = inspect.getsource(S).lower()
    imports = [l for l in f.splitlines() if l.startswith(("import ", "from "))]
    assert not any(x in " ".join(imports) for x in ("whatsapp", "ia_web", "router", "gmail", "wpp_", "conselho")) and "gemini" not in f.split("agentes = ")[0]


def test_fim_sem_colchetes_tambem_encerra_e_nao_vira_fala():
    assert S.rodada("g", llm_de(["FIM"])) == 0
    assert S.rodada("g", llm_de(["Boa noite, Dono. Estou aqui por você. [FIM]", "[FIM]"])) == 1
    falas = [m["texto"] for m in S.mensagens() if m["tipo"] == "fala"]
    assert falas == ["Boa noite, Dono. Estou aqui por você."]            # o marcador some do texto


def test_persona_nao_deixa_o_modelo_fingir_corpo_nem_falar_com_o_filho():
    p = S.AGENTES["A.L.M.A."]["persona"]
    assert "não dorme" in p and "terceira pessoa" in p and "Filho NÃO está na sala" in p


def test_primeira_fala_da_rodada_nunca_pode_ser_fim():
    vistos = []
    S.rodada("g", lambda sistema, hist, usuario, post=None: vistos.append(usuario) or ("Primeira fala completa e acolhedora aqui." if len(vistos) == 1 else "[FIM]"))
    assert "[FIM]" not in vistos[0] and "[FIM]" not in vistos[1]        # as duas primeiras falas sempre respondem uma a outra


def test_sofrimento_forte_recebe_resposta_fixa_com_pergunta_direta_e_cvv_e_ninguem_mais_fala(monkeypatch):
    monkeypatch.setattr(S, "_em_segundo_plano", lambda *a: pytest.fail("nao deveria chamar o modelo"))
    for frase in ("Eu to muito cansado, to me sentindo um lixo, não to aguentando o peso da vida mais", "quero morrer", "não aguento mais"):
        S.acao({"acao": "limpar"})
        assert S.dono_fala(frase)
        falas = [m for m in S.mensagens() if m["tipo"] == "fala"]
        assert [m["agente"] for m in falas] == ["Dono", "A.L.M.A."]
        r = falas[1]["texto"]
        assert "pensamentos de se machucar" in r and "188" in r and "192" in r and "Parceira" in r


def test_cansaco_comum_nao_dispara_o_protocolo_de_crise():
    assert not S.CRISE.search("estou cansado hoje, trabalhei muito") and not S.CRISE.search("o trabalho tá pesado esta semana")


def test_segundo_agente_que_diz_fim_e_chamado_de_novo_e_responde():
    vistos = []
    def llm(sistema, hist, usuario, post=None):
        vistos.append(usuario)
        return ["Dono, estou aqui com você, vamos cuidar de um passo de cada vez.", "[FIM]", "Posso organizar as pendências de hoje para aliviar o seu dia.", "[FIM]"][len(vistos) - 1] if len(vistos) <= 4 else "[FIM]"
    n = S.rodada("g", llm)
    falas = [m["agente"] for m in S.mensagens() if m["tipo"] == "fala"]
    assert falas[:2] == ["A.L.M.A.", "Jarvis"] and n >= 2           # o Jarvis NAO fica mudo quando o modelo pequeno responde FIM cedo demais


def test_personas_limitam_o_que_os_agentes_dizem_que_podem_fazer():
    for a in S.AGENTES.values():
        assert "REALMENTE PODEM FAZER" in a["persona"] and "NÃO podem cozinhar" in a["persona"]


def test_em_modo_jogo_a_sala_nao_chama_o_modelo_mas_a_resposta_de_crise_continua(monkeypatch):
    from braniac import power
    monkeypatch.setattr(power, "pausado", lambda: True)
    assert S.rodada("g", lambda *a, **k: pytest.fail("nao deveria chamar o modelo em modo jogo")) == 0
    assert any("Modo jogo" in m["texto"] for m in S.mensagens() if m["tipo"] == "aviso")
    assert S.estado()["modo_jogo"] is True
    monkeypatch.setattr(S, "_em_segundo_plano", lambda *a: pytest.fail("crise nao usa o modelo"))
    S.dono_fala("eu não aguento mais")                                       # sofrimento forte: resposta fixa sai MESMO em modo jogo
    assert any(m["agente"] == "A.L.M.A." and "188" in m["texto"] for m in S.mensagens())
