from braniac import contexto, recado_falado, recados


def test_roteiro_conversa_e_resume(monkeypatch):
    monkeypatch.setattr(contexto, "contato", lambda a: {"mae": "mainha", "pai": "Pai"}.get(a))
    t = recado_falado.roteiro("mainha", ["ainda tô com muita dor no braço"], ["Poxa, melhoras!"], resumir=lambda r, f, rs: "Ela disse que ainda sente muita dor no braço.")
    assert t.startswith("Oi, Dono! Tudo bom? Olha, sua mãe entrou em contato.") and "dor no braço" in t and "WhatsApp" in t
    t2 = recado_falado.roteiro("Pai", ["oi filho"], resumir=lambda *a: "")           # sem IA local: roteiro fixo, sem quebrar
    assert "seu pai" in t2 and "Ele disse assim: oi filho" in t2


def test_entrega_em_audio_agrupa_por_pessoa_e_cai_no_texto(tmp_path, monkeypatch):
    monkeypatch.setattr(recados, "ARQ", tmp_path / "r.json")
    monkeypatch.setattr(recado_falado, "_resumir_local", lambda *a, **k: "Ela está melhor.")
    recados.enfileirar("Ana", "tô melhor hoje")
    recados.enfileirar("Ana", "obrigada por perguntar")
    falas = []
    assert recados.entregar(lambda d, t: "falhou", "Eu", audio=lambda d, f: falas.append(f) or "✅ Áudio") == 2
    assert len(falas) == 1 and not recados.pendentes()                                 # 2 recados da Ana = 1 audio
    recados.enfileirar("Bia", "preciso de você")
    assert recados.entregar(lambda d, t: "✅ ok", "Eu", audio=lambda d, f: "erro") == 1   # audio falhou: texto de sempre
