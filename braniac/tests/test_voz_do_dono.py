import json

from braniac import voz_do_dono as V

FALAS = ["bora ver isso rapidão", "me manda o link do site", "tá, pode fazer", "vê o saldo pra mim", "cria a vaquinha", "olha a agenda de hoje", "valeu cara",
         "coloca a meta de 1600", "e aí jarvis, como tá o braniac?", "beleza, manda ver", "pra quando fica pronto?", "abre o airbnb pra mim"] * 3


def _gravar(textos):
    V.PASTA.mkdir(parents=True, exist_ok=True)
    V.AMOSTRAS.write_text("\n".join(json.dumps({"texto": t}) for t in textos), encoding="utf-8")


def test_estatisticas_e_descricao_nao_vazam_as_frases():
    e = V.estatisticas(FALAS)
    assert e["amostras"] == 36 and e["palavras_por_mensagem"] < 8 and "bora" in e["girias"] and e["comeca_minuscula"] > .9
    d = V.descricao_abstrata(e)
    assert "link do site" not in d and "airbnb" not in d.lower() and "bora" in d          # so tracos, nunca frases


def test_guia_local_e_refinamento_semanal_pelo_conselho():
    _gravar(FALAS)
    assert "frases curtas" in V.guia() and "informal" in V.guia()
    pedidos = []
    ok = V.refinar(lambda ia, p: pedidos.append((ia, p)) or "1. Frases curtas.\n2. Tom informal.\n3. Vai direto ao ponto e confirma em uma frase.\n4. Sem ponto final nas frases curtas.", agora=1_000_000.0)
    assert ok and pedidos[0][0] == "chatgpt" and "link do site" not in pedidos[0][1] and "airbnb" not in pedidos[0][1].lower()
    assert "Vai direto ao ponto" in V.guia()
    assert not V.refinar(lambda ia, p: "x" * 200, agora=1_000_000.0 + 3600)                       # 1x por semana
    assert V.refinar(lambda ia, p: "y" * 200, agora=1_000_000.0 + 8 * 86400)


def test_roteador_anexa_o_guia_ao_prompt():
    from braniac import router
    _gravar(FALAS)
    assert "COMO O DONO FALA" in router._voz() and "frases curtas" in router._voz()
