from pathlib import Path

UI = Path(__file__).resolve().parent.parent / "ui"


def test_escritorio_3d_mantem_os_contratos_do_2d():
    h = (UI / "sauraki3d.html").read_text(encoding="utf-8")
    for marca in ("/api/sauraki", "function detalhe", "function painel", "abrirJarvis", "setEco", "?plano=1", 'a:["Jarvis"'):   # a sala central (Gerencia) tem o Jarvis e o Claudinho
        assert marca in h, marca
    assert not any(c in h for c in "\x08\x0c\x00")          # \b/\f virando caractere de controle (licao de 27/10)


def test_todos_os_agentes_do_registro_tem_sala():
    from braniac import assuntos
    h = (UI / "sauraki3d.html").read_text(encoding="utf-8")
    nomes = {a[2] for a in assuntos.SEMENTES}
    assert len(nomes) >= 10
    faltam = [n for n in nomes if f'"{n}"' not in h and n not in ("Sultão",)]
    assert not faltam, faltam
