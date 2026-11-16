# -*- coding: utf-8 -*-
import time

from braniac import atender, claudinho, contexto, memoria


def test_agradecimento_so_quando_e_so_agradecimento():
    assert contexto.agradecimento("valeu") and contexto.agradecimento("Muito obrigado! 🙏") and contexto.agradecimento("vlw mesmo")
    assert contexto.agradecimento("valeu, quanto custa?") is None
    assert contexto.agradecimento("obrigado, mas preciso do orçamento") is None
    assert contexto.agradecimento("fechado") is None   # 'fechado' pode ser aceite de venda: nunca e so agradecimento


def test_sem_reapresentacao_tira_so_a_apresentacao():
    t = "Sou o Jarvis, assistente de IA do Dono. A landing page custa R$ 150."
    assert contexto.sem_reapresentacao(t) == "A landing page custa R$ 150."
    assert contexto.sem_reapresentacao(t, "quem é você?") == t            # perguntou quem e: explica
    assert contexto.sem_reapresentacao("Oi! Eu sou o Jarvis, assistente de IA do Dono.") == "Oi!"
    assert contexto.sem_reapresentacao("Aqui é o Jarvis, assistente do Dono.") == "Claro! Posso ajudar em mais alguma coisa?"
    assert contexto.sem_reapresentacao("Pode ser amanhã às 10h.") == "Pode ser amanhã às 10h."


def test_com_apresentacao_nao_repete_para_quem_ja_foi_apresentado(tmp_path, monkeypatch):
    monkeypatch.setattr(memoria, "ARQ", tmp_path / "m.db")
    monkeypatch.setattr(contexto, "apresentado", lambda c: False)
    memoria.registrar_msg("+55 66 9999-0000", "C", "Oi! Aqui é o Jarvis, assistente do Dono. Como posso ajudar?")
    assert atender.com_apresentacao("+55 66 9999-0000", "Sou o Jarvis, assistente de IA do Dono. Obrigado!") == "Obrigado!"
    assert "Jarvis" in atender.com_apresentacao("Contato Novo", "Posso ajudar.")   # contato novo continua recebendo a abertura


def test_auditoria_acha_os_erros_do_dia(tmp_path, monkeypatch):
    monkeypatch.setattr(memoria, "ARQ", tmp_path / "m.db")
    agora = time.time()
    c = "+55 66 9000-0004"
    memoria.registrar_msg(c, "C", "Oi! Sou o Jarvis, assistente do Dono. Como posso ajudar?", ts=agora - 3000)
    memoria.registrar_msg(c, "E", "valeu", ts=agora - 2000)
    memoria.registrar_msg(c, "C", "Eu sou o Jarvis, assistente de IA do Dono, uso o Braniac que consulta o Claude e " + "x" * 300, ts=agora - 1000)
    tipos = {a["tipo"] for a in claudinho.auditar(6, agora)}
    assert {"reapresentou", "vazou_interno", "exagerou", "respondeu_agradecimento"} <= tipos
    assert not claudinho.auditar(6, agora + 90000)    # fora da janela de horas: nada novo


def test_registrar_nao_duplica_e_guia_tem_regras(tmp_path, monkeypatch):
    monkeypatch.setattr(claudinho, "DIR", tmp_path)
    monkeypatch.setattr(claudinho, "ACHADOS", tmp_path / "achados.jsonl")
    a = {"id": "x1", "tipo": "repetiu", "contato": "p", "texto": "t", "ts": time.time()}
    assert claudinho.registrar([a]) == [a] and claudinho.registrar([a]) == []
    assert claudinho.resumo(1) == {"repetiu": 1}
    assert "não diga de novo" in claudinho.guia()


def test_aprender_anonimiza_e_so_aceita_linhas_de_regra(tmp_path, monkeypatch):
    monkeypatch.setattr(claudinho, "DIR", tmp_path)
    monkeypatch.setattr(claudinho, "GUIA", tmp_path / "guia.md")
    vistos = []
    novas = claudinho.aprender([{"tipo": "repetiu", "contato": "Maria Silva", "texto": "oi 66999990000"}],
                               chamar=lambda p: vistos.append(p) or "blá\n- Não repita a mesma pergunta duas vezes seguidas.\n- curta")
    assert novas == ["Não repita a mesma pergunta duas vezes seguidas."]
    assert "Maria" not in vistos[0] and "66999990000" not in vistos[0] and "pessoa-1" in vistos[0]
    assert "duas vezes seguidas" in claudinho.guia()


def test_tick_respeita_janela_e_teto_diario(tmp_path, monkeypatch):
    monkeypatch.setattr(claudinho, "DIR", tmp_path)
    monkeypatch.setattr(claudinho, "ESTADO", tmp_path / "estado.json")
    monkeypatch.setattr(claudinho, "ACHADOS", tmp_path / "achados.jsonl")
    from braniac import barramento
    monkeypatch.setattr(barramento, "DB", tmp_path / "agentes.db")
    chamadas = []
    achado = lambda i: {"id": f"i{i}", "tipo": "repetiu", "contato": "p", "texto": "t", "ts": time.time()}
    monkeypatch.setattr(claudinho, "auditar", lambda h, agora: [achado(i) for i in range(int(agora) % 1000, int(agora) % 1000 + 3)])
    monkeypatch.setattr(claudinho.threading, "Thread", lambda target, **k: type("T", (), {"start": staticmethod(target)})())
    monkeypatch.setattr(claudinho, "ESTADO", tmp_path / "estado.json")
    t0 = time.time()
    claudinho.tick(t0, aprender_fn=lambda a: chamadas.append(1))
    assert chamadas == [1]                                      # 3 achados novos: o Claude e chamado
    claudinho.tick(t0 + 2000, aprender_fn=lambda a: chamadas.append(1))
    assert chamadas == [1]                                      # menos de 4 h depois: nao chama de novo
    claudinho.tick(t0 + 49 * 3600, aprender_fn=lambda a: chamadas.append(1))
    assert chamadas == [1]                                      # fora da janela de 48 h: so audita
