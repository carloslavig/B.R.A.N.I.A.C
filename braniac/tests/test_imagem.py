# -*- coding: utf-8 -*-
"""Ler e criar imagens: Gemini com plano B, atendimento que 've' o print antes de responder."""
import base64
import pytest
from braniac import atender, imagem, telegram_bot, voz, whatsapp, wpp_voz

PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 50


class Resp:
    def __init__(self, status=200, corpo=None):
        self.status_code, self._c = status, corpo or {}
        self.headers = {"content-type": "image/jpeg"}
        self.content = b"J" * 3000

    def json(self):
        return self._c


def _texto(t):
    return {"candidates": [{"content": {"parts": [{"text": t}]}}]}


def _img(b):
    return {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "image/png", "data": base64.b64encode(b).decode()}}]}}]}


@pytest.fixture(autouse=True)
def _ambiente(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setattr(imagem.store, "DATA", tmp_path)
    imagem._cooldown.clear()


def test_descrever_usa_o_primeiro_modelo_com_cota(monkeypatch):
    chamados = []

    def post(modelo, corpo, timeout):
        chamados.append(modelo)
        return Resp(429) if len(chamados) == 1 else Resp(200, _texto("Print do iFood: esfiha R$ 11,90"))
    monkeypatch.setattr(imagem, "_post", post)
    assert imagem.descrever(PNG) == "Print do iFood: esfiha R$ 11,90"
    assert chamados == imagem.MODELOS_VISAO[:2] and imagem.ULTIMO_MOTOR == "gemini:" + imagem.MODELOS_VISAO[1]
    chamados.clear()
    imagem.descrever(PNG)
    assert chamados[0] == imagem.MODELOS_VISAO[1]            # o modelo sem cota fica em descanso e nao e tentado de novo


def test_descrever_cai_para_o_ollama_local_sem_gemini(monkeypatch):
    monkeypatch.setattr(imagem, "_post", lambda *a, **k: Resp(429))
    monkeypatch.setattr(imagem, "_descrever_local", lambda d, i, t: "foto de uma esfiha")
    assert imagem.descrever(PNG) == "foto de uma esfiha"


def test_descrever_sem_nenhum_motor_levanta_erro_claro(monkeypatch):
    monkeypatch.setattr(imagem, "_post", lambda *a, **k: Resp(500))
    monkeypatch.setattr(imagem, "_descrever_local", lambda d, i, t: (_ for _ in ()).throw(imagem.SemImagem("ollama indisponivel")))
    with pytest.raises(imagem.SemImagem) as e:
        imagem.descrever(PNG)
    assert "HTTP 500" in str(e.value) and "ollama" in str(e.value)
    with pytest.raises(imagem.SemImagem):
        imagem.descrever(b"")


def test_prompt_de_leitura_proibe_repetir_dados_financeiros():
    assert "NAO escreva numeros de cartao" in imagem.PROMPT_LER and "transcreva fielmente" in imagem.PROMPT_LER


def test_gerar_salva_o_arquivo_do_gemini(monkeypatch, tmp_path):
    monkeypatch.setattr(imagem, "_post", lambda *a, **k: Resp(200, _img(PNG)))
    img, caminho = imagem.gerar("esfihas no forno")
    assert img == PNG and caminho.exists() and caminho.parent == tmp_path / "imagens" and caminho.suffix == ".png"


def test_gerar_sem_cota_do_gemini_usa_o_plano_b_gratis(monkeypatch):
    monkeypatch.setattr(imagem, "_post", lambda *a, **k: Resp(429))
    monkeypatch.setattr("requests.get", lambda *a, **k: Resp(200))
    img, caminho = imagem.gerar("esfihas no forno")
    assert caminho.exists() and imagem.ULTIMO_MOTOR == "pollinations:flux"


def test_editar_com_referencia_nao_usa_o_plano_b(monkeypatch):
    monkeypatch.setattr(imagem, "_post", lambda *a, **k: Resp(429))
    monkeypatch.setattr("requests.get", lambda *a, **k: pytest.fail("plano B nao edita imagem"))
    with pytest.raises(imagem.SemImagem):
        imagem.gerar("tira o fundo", referencia=PNG)


def test_gerar_sem_descricao_ou_sem_chave():
    with pytest.raises(imagem.SemImagem):
        imagem.gerar("  ")


def test_foto_ao_dono_sem_telegram_configurado(monkeypatch, tmp_path):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert "não configurado" in telegram_bot.mandar_foto_ao_dono(tmp_path / "a.png")


# ---------- atendimento ----------

@pytest.fixture
def envios(monkeypatch):
    saidas = []
    monkeypatch.setattr(whatsapp, "enviar", lambda n, x: saidas.append(("texto", n, x)) or f"✅ texto {n}")
    monkeypatch.setattr(voz, "falar_wav", lambda t, permitir_nuvem=True: ("WAV:" + t).encode())
    monkeypatch.setattr(wpp_voz, "enviar_voz", lambda n, w: saidas.append(("voz", n, w.decode())) or f"✅ Áudio enviado para {n}.")
    monkeypatch.setattr(atender.time, "sleep", lambda s: None)
    return saidas


def _item(msgs):
    return {"nome": "Maria", "nl": 1, "msgs": list(msgs), "ctx": [], "autores": {"Maria"}, "midia": True}


def test_atendimento_ve_o_print_antes_de_decidir(monkeypatch, envios):
    vistos = []
    monkeypatch.setattr(atender, "coletar", lambda *a, **k: [_item(["[IMAGEM]"])])
    monkeypatch.setattr(atender, "decidir", lambda it, fl, esp=0: vistos.append((list(it["msgs"]), fl)) or ("E", "Recebi o print, obrigado!"))
    atender.atender(espaco_s=(0, 0), relatar=False, ver_imagem=lambda n: ("Print: taxa de entrega R$ 9", None))
    assert vistos[0][0] == ["🖼 Print: taxa de entrega R$ 9"]
    assert "A" not in vistos[0][1]                                    # a imagem foi entendida: nao e mais 'midia misteriosa'
    assert envios and "Recebi o print" in envios[0][2]


def test_imagem_que_nao_deu_para_ver_continua_marcada_como_midia(monkeypatch, envios):
    vistos = []
    monkeypatch.setattr(atender, "coletar", lambda *a, **k: [_item(["[IMAGEM]"])])
    monkeypatch.setattr(atender, "decidir", lambda it, fl, esp=0: vistos.append((list(it["msgs"]), fl)) or ("P", "Não consigo ver a imagem"))
    atender.atender(espaco_s=(0, 0), relatar=False, ver_imagem=lambda n: (None, "sem cota"))
    assert vistos[0][0] == ["[IMAGEM não compreendida]"] and "A" in vistos[0][1]


def test_comprovante_com_tema_sensivel_continua_sendo_respondido(monkeypatch, envios):
    decididos = []
    monkeypatch.setattr(atender, "coletar", lambda *a, **k: [_item(["[IMAGEM]"])])
    monkeypatch.setattr(atender, "decidir", lambda it, fl, esp=0: decididos.append(fl) or ("E", "ok"))
    rel = atender.atender(espaco_s=(0, 0), relatar=False, ver_imagem=lambda n: ("Comprovante de pix de R$ 150, senha do banco no verso", None))
    assert decididos and "S" in decididos[0] and envios and "NÃO respondi" not in rel      # 06/10: nao existe assunto que impeca a resposta


def test_segunda_chave_do_gemini_so_entra_quando_a_primeira_estoura(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY_2", "y")
    usadas = []

    def post(url, headers, json, timeout):
        usadas.append(headers["x-goog-api-key"])
        return Resp(429) if headers["x-goog-api-key"] == "x" else Resp(200, _texto("ok"))
    monkeypatch.setattr("requests.post", post)
    assert imagem.descrever(PNG) == "ok" and usadas == ["x", "y"]


def test_modelo_local_recebe_pedido_curto_em_ingles_e_vem_marcado_como_aproximado(monkeypatch):
    corpos = []

    class R:
        status_code = 200

        def json(self):
            return {"response": "a red logo"}
    monkeypatch.setattr("requests.post", lambda url, json=None, timeout=0: corpos.append(json) or R())
    monkeypatch.setattr(imagem, "_instalados", lambda: {"moondream:latest"})
    txt = imagem._descrever_local(PNG, imagem.PROMPT_LER, 5)
    assert txt.startswith("(leitura local") and corpos[0]["prompt"] == imagem.PROMPT_LOCAL
    monkeypatch.setattr(imagem, "_instalados", lambda: {"qwen2.5vl:3b", "moondream:latest"})   # o forte vence: pedido em portugues, sem prefixo de aproximado
    txt = imagem._descrever_local(PNG, "Descreva em portugues", 5)
    assert txt == "a red logo" and corpos[1]["model"] == "qwen2.5vl:3b" and corpos[1]["prompt"] == "Descreva em portugues"
    monkeypatch.setattr(imagem, "_instalados", lambda: set())
    with pytest.raises(imagem.SemImagem):
        imagem._descrever_local(PNG, "x", 5)


# ---------- delegacao ao Claude: nunca perder o resultado ----------

def test_delegacao_sem_canal_avisa_o_dono_e_registra_log(monkeypatch, tmp_path):
    from braniac import claude_agent
    monkeypatch.setattr(claude_agent, "DATA", tmp_path)
    avisos = []
    monkeypatch.setattr(claude_agent, "_avisar_dono", lambda t: avisos.append(t) or True)

    from braniac import agente_dev
    monkeypatch.setattr(agente_dev, "rodar", lambda *a, **k: (0, "feito: 3 roteiros"))
    claude_agent.executar_em_segundo_plano("fazer roteiros", None).join(5)
    assert avisos and "feito: 3 roteiros" in avisos[0]
    log = (tmp_path / "delegacoes.log").read_text(encoding="utf-8")
    assert "INICIO | fazer roteiros" in log and "FIM | feito: 3 roteiros" in log
