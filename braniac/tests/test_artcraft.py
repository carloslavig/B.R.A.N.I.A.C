# -*- coding: utf-8 -*-
"""ArtCraft no Jarvis: nomes de saida seguros, erros claros e (com os apps instalados) execucao real de foto, vetor e PDF."""
import pytest
from pathlib import Path
from braniac import artcraft


@pytest.fixture(autouse=True)
def trabalho(tmp_path, monkeypatch):
    monkeypatch.setattr(artcraft, "TRABALHO", tmp_path / "trab")
    yield tmp_path / "trab"


def _tem(*apps):
    return all(list(artcraft.APPS.glob(f"{a}/*/{a}-cli.exe")) for a in apps)


def test_saida_fica_na_pasta_de_trabalho_com_nome_simples(trabalho):
    assert Path(artcraft._saida("..\\..\\Windows\\x.png", ".png")) == trabalho / "x.png"
    assert Path(artcraft._saida("a.exe", ".png")).name == "a.png"


def test_erros_claros(tmp_path):
    with pytest.raises(artcraft.ArtCraftErro, match="desconhecida"):
        artcraft.executar("hackear", "x")
    with pytest.raises(artcraft.ArtCraftErro, match="Não achei"):
        artcraft.executar("pdf_texto", str(tmp_path / "nao-existe.pdf"))
    with pytest.raises(artcraft.ArtCraftErro, match="protegido"):
        artcraft.executar("pdf_texto", str(tmp_path / ".ssh" / "id_rsa"))


@pytest.mark.skipif(not _tem("vectorcraft", "photocraft", "pdfcraft"), reason="ArtCraft nao instalado")
def test_cartaz_foto_e_pdf_reais(trabalho):
    assert "Pronto" in artcraft.executar("vetor_cartaz", "Oi", "c.png", "#000000 #ffffff #ff0000")
    c = str(trabalho / "c.png")
    assert "300" in str(artcraft.executar("foto_redimensionar", c, "p.png", "300")) or (trabalho / "p.png").is_file()
    with pytest.raises(artcraft.ArtCraftErro, match="90, 180"):
        artcraft.executar("foto_girar", c, "g.png", "45")
    artcraft.executar("vetor_converter", c, "c.pdf")
    artcraft.executar("pdf_juntar", f"{trabalho / 'c.pdf'};{trabalho / 'c.pdf'}", "dois.pdf")
    artcraft.executar("pdf_dividir", str(trabalho / "dois.pdf"), "partes.pdf", "1")
    assert len(list((trabalho / "partes").glob("*.pdf"))) == 2


def test_nome_de_acao_parecido_e_aceito(trabalho):
    for errado in ("desenhar", "vetor_desenho", "Vetor Desenhar"):
        with pytest.raises(artcraft.ArtCraftErro, match="JSON"):     # chegou em vetor_desenhar (falha so por o JSON ser invalido)
            artcraft.executar(errado, "isto não é json")
    with pytest.raises(artcraft.ArtCraftErro, match="desconhecida"):
        artcraft.executar("xyzzy", "x")


def test_desenho_por_descricao_tenta_de_novo_e_valida():
    respostas = iter(["desculpe, aqui vai um desenho!", 'Claro: [{"t":"rect","x":0,"y":0,"w":10,"h":10,"cor":"#112233"}] pronto'])
    formas = artcraft.formas_de_descricao("um quadrado", lambda p: next(respostas))
    assert formas[0]["t"] == "rect"
    with pytest.raises(artcraft.ArtCraftErro, match="não conseguiu"):
        artcraft.formas_de_descricao("x", lambda p: "nada de json")


@pytest.mark.skipif(not _tem("vectorcraft"), reason="ArtCraft nao instalado")
def test_desenhar_de_ponta_a_ponta_com_ia_falsa(trabalho):
    out = artcraft.desenhar("sol", lambda p: '[{"t":"rect","x":0,"y":0,"w":612,"h":792,"cor":"#87ceeb"},{"t":"elipse","x":200,"y":200,"w":200,"cor":"#ffd700"}]')
    assert Path(out).is_file() and Path(out).parent == trabalho
