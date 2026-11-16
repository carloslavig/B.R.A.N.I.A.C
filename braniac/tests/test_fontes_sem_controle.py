import glob
import os


def test_nenhum_fonte_tem_caractere_de_controle_backspace():
    """Um \b mal escapado vira backspace dentro de regex/caminho e quebra a trava em silencio (aconteceu em wpp_arquivo, rotina e gratis)."""
    pasta = os.path.dirname(os.path.dirname(__file__))
    ruins = [f for f in glob.glob(os.path.join(pasta, "*.py")) if chr(8) in open(f, encoding="utf-8", errors="replace").read()]
    assert not ruins, ruins
