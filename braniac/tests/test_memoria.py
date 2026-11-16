# -*- coding: utf-8 -*-
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from braniac import atender, canal, contexto, dono, jarvis, memoria, telegram_bot, whatsapp


# ---------- o banco em si ----------

def test_mensagens_ficam_guardadas_sem_duplicar():
    assert memoria.registrar_msg("Maria", "E", "tem vaga pra novembro?")
    assert not memoria.registrar_msg("Maria", "E", "tem vaga pra novembro?")     # a conversa e lida varias vezes: nao duplica
    memoria.registrar_msg("Maria", "C", "Tem sim, qual a data?")
    assert memoria.historico("Maria") == [("E", "tem vaga pra novembro?"), ("C", "Tem sim, qual a data?")]
    assert memoria.historico("Joao") == []


def test_resposta_ja_conhecida_e_reaproveitada_mesmo_com_outras_palavras():
    memoria.guardar_resposta("Qual é o preço da diária do Studio?", "Varia por data; o Dono informa.", "claude")
    assert memoria.buscar_resposta("qual o preco da diaria do studio") == "Varia por data; o Dono informa."
    assert memoria.buscar_resposta("quem é o Irmao?") is None


def test_esquecer_apaga_o_que_estava_errado():
    memoria.guardar_resposta("quem é o Irmao?", "Irmao é primo do Dono", "claude")
    assert memoria.esquecer("irmao") == 1 and memoria.buscar_resposta("quem é o Irmao?") is None


def test_decisao_repetida_so_reaproveita_ignorar_e_avisar_nunca_resposta():
    memoria.registrar_decisao("Ana", "Bom dia, gente!", "I")
    memoria.registrar_decisao("Ana", "tem vaga?", "E", "Tem sim!")
    assert memoria.decisao_repetida("Ana", "bom dia gente") == "I"                  # mesma mensagem ja ignorada
    assert memoria.decisao_repetida("Ana", "tem vaga?", ("I",)) is None             # uma RESPOSTA nao e reaproveitada
    assert memoria.decisao_repetida("Outra", "bom dia gente") is None               # e so para a mesma pessoa
    memoria.registrar_decisao("Ana", "preciso falar urgente", "A", "avisar")
    assert memoria.decisao_repetida("Ana", "preciso falar urgente", ("A",), dias=1) == "A"


def test_ficha_junta_fatos_decisoes_e_ultimas_mensagens():
    memoria.aprender_fato("Maria", "prefere áudio")
    memoria.registrar_decisao("Maria", "tem vaga?", "E", "Tem sim!")
    memoria.registrar_msg("Maria", "E", "tem vaga?")
    f = memoria.ficha("Maria")
    assert "prefere áudio" in f and "DECISOES RECENTES" in f and "ELE: tem vaga?" in f


# ---------- nao pergunta de novo ao Claude ----------

def test_segunda_pergunta_igual_nao_chega_ao_claude(monkeypatch):
    chamadas = []
    monkeypatch.setattr(canal, "presente", lambda: False)
    monkeypatch.setattr(contexto, "perguntar_claude", lambda p, extra="": chamadas.append(p) or "Irmao é o irmão do Dono.")
    assert contexto.consultar("quem é o Irmao?") == ("resp", "Irmao é o irmão do Dono.")
    assert contexto.consultar("Quem é o Irmao?") == ("resp", "Irmao é o irmão do Dono.")     # veio do banco
    assert len(chamadas) == 1


def test_resposta_do_claude_ao_vivo_tambem_e_gravada(monkeypatch):
    monkeypatch.setattr(canal, "presente", lambda: True)
    perguntas = []
    monkeypatch.setattr(canal, "perguntar_k", lambda p, espera_s=120, id_=None: perguntas.append(p) or ("k", "T", "A Parceira é a Parceira."))
    contexto.consultar("quem é a Parceira?")
    contexto.consultar("quem é a Parceira?")
    assert len(perguntas) == 1 and memoria.buscar_resposta("quem é a Parceira?") == "A Parceira é a Parceira."


def test_pergunta_que_o_claude_manda_levar_ao_dono_nao_e_cacheada(monkeypatch):
    monkeypatch.setattr(canal, "presente", lambda: True)
    monkeypatch.setattr(canal, "perguntar_k", lambda p, espera_s=120, id_=None: ("k", "P", "Qual valor passo à Ana?"))
    assert contexto.consultar("quanto é a diária?") == ("perguntar", "Qual valor passo à Ana?")
    assert memoria.buscar_resposta("quanto é a diária?") is None                          # decisao do Dono, nunca vira regra


def test_comandos_memoria_e_esquecer(monkeypatch):
    monkeypatch.setattr(jarvis.power, "pausado", lambda: False)

    class R:
        cfg = {"cadeia": []}
    memoria.guardar_resposta("quem é o Irmao?", "primo", "claude")
    assert "1 respostas aprendidas" in jarvis.processar(R(), "/memoria", "c")[0]
    assert "Apaguei 1" in jarvis.processar(R(), "/esquecer Irmao", "c")[0]
    assert "Não achei" in jarvis.processar(R(), "/esquecer zzz", "c")[0]


# ---------- atendimento usa e alimenta a memoria ----------

def _item(nome="Maria", msgs=("tem vaga?",), ctx=()):
    return {"nome": nome, "nl": len(msgs), "msgs": list(msgs), "ctx": list(ctx), "autores": {nome}, "midia": False}


@pytest.fixture
def base(monkeypatch):
    enviados = []
    monkeypatch.setattr(whatsapp, "enviar", lambda n, x: enviados.append(x) or "✅ ok")
    monkeypatch.setattr(atender.time, "sleep", lambda s: None)
    return enviados


def test_atendimento_grava_mensagens_decisao_e_resposta(monkeypatch, base):
    monkeypatch.setattr(atender, "coletar", lambda *a, **k: [_item()])
    monkeypatch.setattr(atender, "decidir", lambda it, fl, esp=0: ("E", "Tem sim! Qual data?"))
    atender.atender(espaco_s=(0, 0), relatar=False)
    h = memoria.historico("Maria")
    assert ("E", "tem vaga?") in h and any(d == "C" and "Tem sim! Qual data?" in t for d, t in h)
    assert memoria.resumo()["decisoes"] == 1


def test_mensagem_igual_a_uma_ja_ignorada_nao_pergunta_ao_claude(monkeypatch, base):
    perguntas = []
    memoria.registrar_msg("Rafa", "C", "Oi, Rafa! Eu sou o Jarvis.")      # contato ja conhecido (nao e o 1o contato)
    monkeypatch.setattr(atender, "decidir", lambda it, fl, esp=0: perguntas.append(1) or ("I", ""))
    monkeypatch.setattr(atender, "coletar", lambda *a, **k: [_item("Rafa", ("bom dia grupo!",))])
    atender.atender(espaco_s=(0, 0), relatar=False)
    monkeypatch.setattr(atender, "coletar", lambda *a, **k: [_item("Rafa", ("Bom dia, grupo",))])
    rel = atender.atender(espaco_s=(0, 0), relatar=False)
    assert len(perguntas) == 1 and "sem nova pergunta" in rel                           # 2a vez: o banco ja sabia


def test_uma_resposta_E_nunca_e_reaproveitada_para_nova_mensagem(monkeypatch, base):
    perguntas = []
    monkeypatch.setattr(atender, "decidir", lambda it, fl, esp=0: perguntas.append(1) or ("E", "Tem sim!"))
    for _ in range(2):
        monkeypatch.setattr(atender, "coletar", lambda *a, **k: [_item("Maria", ("tem vaga?",))])
        atender.atender(espaco_s=(0, 0), relatar=False)
    assert len(perguntas) == 2                                                          # cada resposta e decidida de novo


def test_contexto_da_pergunta_ganha_o_historico_antigo_do_banco(monkeypatch, base):
    for i in range(6):
        memoria.registrar_msg("Maria", "E" if i % 2 == 0 else "C", f"mensagem antiga {i}")
    vistos = []
    monkeypatch.setattr(atender, "coletar", lambda *a, **k: [_item("Maria", ("e agora?",), ctx=["E: e agora?"])])
    monkeypatch.setattr(atender, "decidir", lambda it, fl, esp=0: vistos.append(list(it["ctx"])) or ("I", ""))
    atender.atender(espaco_s=(0, 0), relatar=False)
    assert any("mensagem antiga" in c for c in vistos[0]) and vistos[0][-1] == "E: e agora?"


def test_claude_de_fundo_recebe_a_ficha_da_pessoa(monkeypatch):
    memoria.aprender_fato("Maria", "é hóspede recorrente do Studio")
    capturado = {}
    monkeypatch.setattr(canal, "presente", lambda: False)
    monkeypatch.setattr(contexto, "decidir_claude", lambda linha, timeout=150, memoria_txt="": capturado.update(m=memoria_txt) or ("x", "I", ""))
    atender.decidir(_item(), "-")
    assert "hóspede recorrente do Studio" in capturado["m"]


# ---------- vigia do Dono grava o que conversam ----------

def test_conversa_com_o_dono_fica_no_banco():
    msgs = [{"d": "ELE", "t": "me lembra de ligar pra mainha", "c": "[10:00, 01/10/2026] Eu: "}]
    dono.tratar_dono(None, ler=lambda n, a: {"msgs": msgs, "midias": [], "lista_sig": "1"},
                     responder=lambda p: "Lembrete anotado.", falar=lambda n, t: True, enviar=lambda n, x: "✅")
    h = memoria.historico("Dono(dono)")
    assert h[0][0] == "E" and "ligar pra mainha" in h[0][1] and h[1] == ("C", "Lembrete anotado.")


# ---------- nao repetir o que a pessoa disse ----------

def _audio_telegram(monkeypatch, cfg):
    enviados = []
    monkeypatch.setattr(telegram_bot, "_baixar_audio", lambda tok, fid: str(Path(__file__)))   # existe; sera 'apagado' abaixo
    monkeypatch.setattr(telegram_bot.os, "unlink", lambda p: None)
    from braniac import voz
    monkeypatch.setattr(voz, "transcrever", lambda p: "quero saber das reservas")
    monkeypatch.setattr(telegram_bot, "_api", lambda tok, m, **kw: enviados.append(kw.get("text")) or {})
    monkeypatch.setattr(telegram_bot, "processar", lambda *a, **k: ("Tem duas reservas hoje.", False))
    telegram_bot._responder_audio("tok", SimpleNamespace(cfg=cfg), 1, "fid")
    return enviados


def test_telegram_nao_repete_o_que_o_dono_falou(monkeypatch):
    out = _audio_telegram(monkeypatch, {})
    assert out == ["Tem duas reservas hoje."]                                    # sem o "Entendi: ..." (decisao do Dono)
    assert any("Entendi" in (x or "") for x in _audio_telegram(monkeypatch, {"eco_transcricao": True}))   # opcional, desligado por padrao


def test_regras_de_nao_repetir_e_de_memoria_estao_nos_prompts():
    base = Path(jarvis.__file__).parent
    cfg = json.loads((base / "providers.json").read_text(encoding="utf-8-sig"))
    assert "NAO REPITA o que a pessoa" in cfg["system"] and cfg["eco_transcricao"] is False
    assert "Memoria local" in (base / "PROTOCOLO.md").read_text(encoding="utf-8")
    assert "NÃO repita o que a pessoa" in contexto.dossie_para("oi")
