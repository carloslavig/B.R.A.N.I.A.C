from braniac import zelo


def _t(nome, msgs, resp="Claro, minha tia."):
    out = {"texto": [], "audio": [], "aviso": []}
    r = zelo.tratar(nome, msgs, lambda n, t: out["texto"].append(t) or "✅", lambda n, t: out["audio"].append(t) or "✅",
                    resumir=lambda t: resp, avisar=lambda f, t: out["aviso"].append((f, t)))
    return r, out


def test_quem():
    assert zelo.quem("Pai") == "pai" and zelo.quem("mainha") == "mae" and zelo.quem("Fulano") is None


def test_pai_so_audio_nunca_texto():
    r, o = _t("Pai", ["bom dia, tudo bem?"], "Tudo bem, Pai!")
    assert o["audio"] and not o["texto"] and r.startswith("✓")


def test_mae_texto():
    r, o = _t("mainha", ["que horas o hóspede chega?"])
    assert o["texto"] == ["Claro, minha tia."] and not o["audio"]


def test_grave_avisa_dono_e_nao_decide():
    r, o = _t("mainha", ["preciso pagar um boleto, pode fazer um pix?"])
    assert o["aviso"] and "Dono" in o["texto"][0] and "avisou o Dono" in r


def test_resposta_com_dado_de_conta_vira_pergunta_ao_dono():
    _, o = _t("mainha", ["oi"], "Manda a senha do banco")
    assert "perguntar ao Dono" in o["texto"][0]


def test_sem_texto_ou_desconhecido_segue_normal():
    assert _t("mainha", ["[ÁUDIO não compreendido]"])[0] is None and _t("Fulano", ["oi"])[0] is None


def test_audio_do_pai_responde_em_audio_e_grave_avisa():
    r, o = _t("Pai", ["🎙 tô bem, graças a Deus"], "Que bom, Pai!")
    assert o["audio"] == ["Que bom, Pai!"] and not o["texto"] and not o["aviso"]
    r, o = _t("Pai", ["🎙 tô com dor no peito"])
    assert o["aviso"] and o["audio"] and not o["texto"]


def test_lembrete_so_do_dono():
    env = lambda n, t: "✅"
    assert zelo.lembrete("mae", "tomar o remédio às 8h", "dono", env).startswith("✅")
    assert zelo.lembrete("mae", "tomar o remédio", "alma", env).startswith("recusado")


def test_audio_ao_pai_que_falhou_nao_marca_tratado(monkeypatch):
    """16/11: o audio do pai deu erro e a vigia marcou 'tratado'; ele ficou sem resposta. Falhou -> a vigia tenta de novo."""
    from braniac import atender, guia_pai
    item = {"nome": "Pai", "nl": 1, "msgs": ["🎙 oi filho"], "ctx": [], "autores": {"Pai"}, "midia": False}
    monkeypatch.setattr(atender, "coletar", lambda *a, **k: [item])
    monkeypatch.setattr(atender.time, "sleep", lambda s: None)
    for linha, marca in (("⚠️ audio do Zelo falhou", False), ("✓ Pai (áudio)", True)):
        monkeypatch.setattr(guia_pai, "tratar", lambda n, it, l=linha: l)
        monkeypatch.setattr(zelo, "tratar", lambda *a, l=linha, **k: l)
        atender.atender(espaco_s=(0, 0), relatar=False)
        assert ("Pai" in atender.ULTIMO["tratados"]) is marca
