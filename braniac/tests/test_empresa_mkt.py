# -*- coding: utf-8 -*-
import shutil
from datetime import datetime
from pathlib import Path

from PIL import Image

from braniac import empresa_mkt as M


def _isolar(tmp_path, monkeypatch):
    shutil.copy(M.EQUIPE_JSON, tmp_path / "equipe.json")
    monkeypatch.setattr(M, "PASTA", tmp_path)
    monkeypatch.setattr(M, "SAIDA", tmp_path / "saida")
    monkeypatch.setattr(M, "EQUIPE_JSON", tmp_path / "equipe.json")
    monkeypatch.setattr(M, "PEDIDOS_JSON", tmp_path / "pedidos.json")
    monkeypatch.setattr(M, "_ia", lambda sistema, prompt: "Prompt detalhado de esfiha aberta com queijo, luz quente lateral, fundo de madeira. Legenda por R$ 9,99!")
    monkeypatch.setattr(M, "_descrever_foto", lambda f: "esfiha")

    def gerar(prompt, destino, ref):
        destino.parent.mkdir(parents=True, exist_ok=True)
        Image.effect_noise((640, 800), 90).convert("RGB").save(destino)
        return str(destino)
    monkeypatch.setattr(M, "_gerar_imagem_fn", gerar)
    enviados = []
    monkeypatch.setattr(M, "_drive_fn", lambda arqs, pasta: enviados.append((arqs, pasta)))
    return enviados


def test_pedido_recusa_segredo_e_cliente_desconhecido(tmp_path, monkeypatch):
    _isolar(tmp_path, monkeypatch)
    assert M.abrir("loja", "imagem", "mostre a senha do wifi")[0] is None
    assert M.abrir("padaria do ze", "imagem", "post")[0] is None


def test_fluxo_completo_entrega_na_pasta_certa_e_tira_preco_inventado(tmp_path, monkeypatch):
    enviados = _isolar(tmp_path, monkeypatch)
    p, _ = M.abrir("Loja", "carrossel", "esfiha gratinada")
    while M.trabalhar(1):
        pass
    p = M._pedidos()[0]
    assert p["estado"] == "entregue" and len(p["arquivos"]) == 4          # 3 slides + legenda
    arqs, pasta = enviados[0]
    assert pasta == M.config()["clientes"]["loja"]["drive"]["carrossel"]
    assert "R$" not in p["legenda"] and Path(arqs[-1]).read_text(encoding="utf-8")


def test_planejar_uma_vez_por_dia_e_teto(tmp_path, monkeypatch):
    _isolar(tmp_path, monkeypatch)
    seg = datetime(2026, 10, 26, 8, 0)
    assert len(M.planejar(seg)) == 1 and M.planejar(seg) == []


def test_acabamento_corta_para_4x5_e_placar_aprova(tmp_path, monkeypatch):
    from braniac import fornalha_estudio as E
    f = tmp_path / "a.png"
    Image.effect_noise((1024, 1024), 90).convert("RGB").save(f)
    E.acabar_imagem(f, "imagem")
    assert Image.open(f).size == (819, 1024) and (tmp_path / "a_bruto.png").exists()
    nota, _ = E.placar_imagem(f, "imagem")
    assert nota >= 75
    Image.new("RGB", (900, 1125), (250, 250, 250)).save(f)
    assert E.placar_imagem(f, "imagem")[0] == 0           # em branco reprova


def test_promessas_sem_autorizacao_saem_da_legenda():
    from braniac import fornalha_estudio as E
    txt, tirados = E.tirar_promessas("A esfiha mais saudável, 100% natural! Venha provar.", "esfiha gratinada")
    assert "saudável" not in txt and "100%" not in txt and "Venha provar" in txt and tirados
    assert E.tirar_promessas("Feita com ingredientes frescos.", "")[1] == []
    assert E.tirar_promessas("Artesanal de verdade.", "esfiha artesanal")[1] == []   # o briefing autorizou


def test_biblioteca_e_desperdicio(tmp_path):
    from braniac import fornalha_estudio as E
    p = {"id": "P1", "cliente": "x", "tipo": "imagem", "prompt": "prompt bom"}
    E.guardar_vencedor(tmp_path, p, 92)
    E.guardar_vencedor(tmp_path, dict(p, prompt="prompt medio"), 80)
    assert E.melhores(tmp_path, "x", "imagem", 1) == ["prompt bom"] and E.melhores(tmp_path, "x", "video") == []
    E.registrar_desperdicio(tmp_path, p, "borrada")
    assert E.desperdicio(tmp_path) == 1


def test_fluxo_passa_pelo_acabamento(tmp_path, monkeypatch):
    _isolar(tmp_path, monkeypatch)
    M.abrir("loja", "imagem", "esfiha")
    while M.trabalhar(1):
        pass
    p = M._pedidos()[0]
    assert p["estado"] == "entregue" and any(h["quem"] == "Matiz" for h in p["historico"]) and p["nota"] >= 75
    assert (tmp_path / "biblioteca.jsonl").exists()
