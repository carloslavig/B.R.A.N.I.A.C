from braniac import avaliar_jarvis as A


def test_avaliador_pega_eco_e_aceita_resposta_boa():
    ruim = A.avaliar(lambda m, c: "Dono disse em 27/10 12:50 (familia): vou mandar", [("eco", "x", r".{20,}", r"^Dono disse em")])
    assert ruim[0][1] is False
    bom = A.avaliar(lambda m, c: "O site da vaquinha é https://vaquinha-exemplo.vercel.app", [("site", "x", r"vaquinha-exemplo\.vercel\.app", r"Dono disse em")])
    assert bom[0][1] is True


def test_json_de_ferramenta_nao_vira_resposta():
    from braniac.router import resposta_e_json_de_ferramenta as j
    assert j('{"name": "organizar-rotina", "arguments": {"objetivo": "x"}}')
    assert not j("Pix copia e cola é um código que você cola no app do banco.")
    assert not j('Use {"name": 1} como exemplo')


def test_lembrete_sem_assunto_nao_cria_item_e_coloque_na_agenda_nao_e_musica():
    from braniac import agenda, jarvis
    for vago in ("Lembrar Dono", "Lembrete", "me lembra amanhã", ""):
        assert agenda.titulo_vazio(vago), vago
    assert not agenda.titulo_vazio("Ligar para o Irmao") and not agenda.titulo_vazio("entrega na Loja")
    assert "pergunte" in agenda.ferramenta({"acao": "adicionar", "titulo": "Lembrar Dono", "quando": "amanhã 09:00"}).lower()
    assert agenda.listar("amanhã").count("Lembrar Dono") == 0
    assert jarvis._musica("Coloque o recado de minha mãe na agenda", "web") is None
    assert jarvis._musica("Põe o lembrete da entrega na agenda", "web") is None


class _Store:
    def __init__(self, msgs):
        self.msgs = msgs

    def historico(self, conv, n):
        return self.msgs[-n:]


class _R:
    def __init__(self, msgs):
        self.store = _Store(msgs)


def test_errou_e_seu_cu_registram_o_erro_para_o_teste_automatico(tmp_path, monkeypatch):
    import json
    from braniac import avaliar_jarvis as A, jarvis, store
    monkeypatch.setattr(store, "DATA", tmp_path)
    msgs = [{"role": "user", "content": "como está a vaquinha?\n\n[Conversa recente no WhatsApp: x]"}, {"role": "assistant", "content": "Tocando vaquinha no Spotify."}]
    for frase in ("errou", "Jarvis, errou feio", "seu cu"):
        resp, da_ia = jarvis.processar(_R(msgs), frase, "c")
        assert "Anotado" in resp and da_ia is False, frase
    linhas = [json.loads(l) for l in (tmp_path / "erros_jarvis.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(linhas) == 3 and linhas[0]["pedido"] == "como está a vaquinha?" and linhas[0]["resposta_errada"] == "Tocando vaquinha no Spotify."
    auto, manual = A.casos_dos_erros(tmp_path / "erros_jarvis.jsonl")
    assert len(auto) == 3 and not manual                                                    # pergunta = consulta segura: roda sozinha
    ok = A.avaliar(lambda m, c: "A vaquinha está em R$ 1.874,00 de R$ 6.000,00.", auto[:1])
    ruim = A.avaliar(lambda m, c: "Tocando vaquinha no Spotify.", auto[:1])
    assert ok[0][1] is True and ruim[0][1] is False                                         # repetir a resposta errada reprova


def test_erro_com_pedido_de_acao_vai_para_revisao_manual_e_frase_longa_nao_dispara(tmp_path, monkeypatch):
    from braniac import avaliar_jarvis as A, jarvis, store
    monkeypatch.setattr(store, "DATA", tmp_path)
    msgs = [{"role": "user", "content": "manda mensagem pra Parceira dizendo oi"}, {"role": "assistant", "content": "Mandei."}]
    assert "Anotado" in jarvis.processar(_R(msgs), "errou", "c")[0]
    auto, manual = A.casos_dos_erros(tmp_path / "erros_jarvis.jsonl")
    assert not auto and len(manual) == 1                                                   # acao com efeito colateral: nunca roda sozinha
    longa = "o Jarvis errou ontem na agenda mas hoje ele acertou tudo direitinho e eu gostei bastante do resultado final"
    assert not jarvis.ERRO_JARVIS.search("o resto do assunto") and jarvis.ERRO_JARVIS.search("errou") and jarvis.ERRO_JARVIS.search("SEU CU")
    assert len(longa) > 80
