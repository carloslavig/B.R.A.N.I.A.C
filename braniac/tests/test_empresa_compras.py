from braniac import empresa_compras as c

TOKENS = ["Pirelli", "Formula", "175/70R13"]
PAG = {"titulo": "Pneu Pirelli Formula 175/70 R13", "texto": "Pneu aro 13. Por R$ 389,90 à vista. 10x R$ 41,00", "url": "https://loja.exemplo/p1"}


def _isolar(tmp_path, monkeypatch):
    monkeypatch.setattr(c, "PASTA", tmp_path)
    monkeypatch.setattr(c, "PEDIDOS_JSON", tmp_path / "p.json")
    monkeypatch.setattr(c, "USO_JSON", tmp_path / "u.json")


def test_confere_exige_modelo_e_preco():
    assert c.confere(PAG["titulo"] + PAG["texto"], TOKENS, 389.90)[0]
    ok, m = c.confere("Pneu Pirelli Cinturato 175/70 R13 R$ 389,90", TOKENS, 389.90)   # outro modelo
    assert not ok and "Formula" in m
    assert not c.confere(PAG["titulo"] + PAG["texto"], TOKENS, 300.0)[0]                 # preco inventado


def test_fluxo_completo_link_antes_do_motivo(tmp_path, monkeypatch):
    _isolar(tmp_path, monkeypatch)
    resp = iter([
        '{"requisitos":"carga alta","candidatos":[{"marca":"Pirelli","modelo":"Formula","tokens":["Pirelli","Formula","175/70R13"],"motivo":"Carcaça reforçada."}]}',
        '[{"i":0,"loja":"LojaA","preco":389.90},{"i":1,"loja":"LojaB","preco":199.0}]'])
    monkeypatch.setattr(c, "_ia_fn", lambda s, p: next(resp))
    monkeypatch.setattr(c, "_pesquisar_fn", lambda q, n: [PAG, {"titulo": "Outro", "texto": "Pneu Pirelli Cinturato R$ 199,00", "url": "https://loja.exemplo/p2"}])
    monkeypatch.setattr(c, "_pagina_fn", lambda u: next(x for x in [PAG, {"titulo": "Outro", "texto": "Pneu Pirelli Cinturato R$ 199,00", "url": "https://loja.exemplo/p2"}] if x["url"] == u))
    p, _ = c.abrir("pneu 175/70R13", "carretinha de carga", canal="whatsapp")
    for _ in range(4):
        c.trabalhar(1, ignorar_teto=True)
    assert c._pedidos()[0]["estado"] == "pronto"
    assert c._pedidos()[0]["escolha"]["url"] == "https://loja.exemplo/p1"     # a de R$199 era outro modelo: descartada
    enviados = []
    c.entregar_prontos(enviados.append)
    assert enviados[0] == "https://loja.exemplo/p1" and "Carcaça" in enviados[1]
    assert c.entregar_prontos(enviados.append) == []                          # nao repete


def test_recusa_segredo_e_pedido_vazio(tmp_path, monkeypatch):
    _isolar(tmp_path, monkeypatch)
    assert c.abrir("cartão de crédito", "")[0] is None and c.abrir("", "")[0] is None


def test_sabi_pergunta_em_vez_de_chutar(tmp_path, monkeypatch):
    _isolar(tmp_path, monkeypatch)
    monkeypatch.setattr(c, "_ia_fn", lambda s, p: '{"perguntas": ["Qual a medida do pneu?"]}')
    monkeypatch.setattr(c, "_pesquisar_fn", lambda q, n: [PAG])
    p, _ = c.abrir("pneu de carretinha", "carga")
    c.trabalhar(1, ignorar_teto=True)
    assert c._pedidos()[0]["estado"] == "precisa_info"
    enviados = []
    c.entregar_prontos(enviados.append)
    c.entregar_prontos(enviados.append)
    assert len(enviados) == 1 and "medida" in enviados[0]                      # pergunta so uma vez
    assert "segue" in c.responder(p["id"], "175/70R13") and c._pedidos()[0]["estado"] == "novo"
    assert "175/70R13" in c._pedidos()[0]["uso"]
