import importlib.util
import pathlib

_p = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "varrer_pessoal.py"
_spec = importlib.util.spec_from_file_location("varrer_pessoal", _p)
vp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vp)


def test_acha_caminho_telefone_chave_e_termo(tmp_path):
    (tmp_path / "a.py").write_text(
        'P = r"C:\\Users\\fulano\\x"\nTEL = "66 99181-2345"\nK = "sk-' + "a" * 24 + '"\nNOME = "Beltrano"\n',  # varredura: ok
        encoding="utf-8")
    tipos = {a[2] for a in vp.varrer([tmp_path], ["beltrano"])}
    assert tipos == {"caminho de usuario", "telefone", "chave de API", "termo pessoal"}


def test_codigo_generico_passa(tmp_path):
    (tmp_path / "b.py").write_text(
        'p = os.path.join(os.environ["USERPROFILE"], "x")\nurl = "https://github.com/carloslavig/B.R.A.N.I.A.C"\n'
        'modelo = "%USERPROFILE%\\\\Apps"\n', encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "c.js").write_text('x = "C:\\\\Users\\\\fulano"', encoding="utf-8")  # varredura: ok
    (tmp_path / "d.py").write_text('assert ok("+55 11 99999-0000")\n', encoding="utf-8")   # numero de exemplo nao barra
    assert vp.varrer([tmp_path], ["beltrano"]) == []
