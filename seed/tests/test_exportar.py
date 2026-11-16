import importlib.util
import pathlib
import subprocess

_p = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "exportar.py"
_spec = importlib.util.spec_from_file_location("exportar", _p)
ex = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ex)


def test_troca_igual_em_codigo_e_nome_de_arquivo_e_respeita_gitignore(tmp_path):
    fonte = tmp_path / "fonte"
    fonte.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=fonte, check=True)
    (fonte / ".gitignore").write_text("data/\n", encoding="utf-8")
    (fonte / "data").mkdir()
    (fonte / "data" / "segredo.txt").write_text("x", encoding="utf-8")
    (fonte / "fulano.py").write_text('DONO = "Fulano"\nX = "fulano"\nY = "Fulanoso"\nZ = "Tia Beltrana e TIA BELTRANA"\ndef avisar_fulano(): pass\n', encoding="utf-8")
    (fonte / "pessoal.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=fonte, check=True)
    n = ex.exportar(fonte, tmp_path / "out", [["Fulano", "Dono"], ["Tia Beltrana", "Mae"]], ["pessoal.py"])
    out = tmp_path / "out"
    assert n == 2 and not (out / "data").exists() and not (out / "pessoal.py").exists()
    (fonte / "data" / "eq.json").write_text('{"agentes": ["Fulano"], "clientes": {"loja": 1}}', encoding="utf-8")
    assert ex.exportar_padrao(fonte, out, {"eq.json": ["clientes"], "falta.json": []}, ex.montar_regra([["Fulano", "Dono"]])) == 1
    assert (out / "padrao" / "eq.json").read_text(encoding="utf-8").replace(" ", "").replace("\n", "") == '{"agentes":["Dono"],"clientes":{}}'
    assert (out / "dono.py").read_text(encoding="utf-8") == 'DONO = "Dono"\nX = "dono"\nY = "Fulanoso"\nZ = "Mae e MAE"\ndef avisar_dono(): pass\n'
