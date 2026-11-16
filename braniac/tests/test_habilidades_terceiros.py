import io
import json
import zipfile

from braniac import habilidades_terceiros as ht


def _zip(arquivos):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for nome, conteudo in arquivos.items():
            z.writestr("autor-repo-abc123/" + nome, conteudo)
    return buf.getvalue()


def _preparar(tmp_path, monkeypatch, itens):
    cat = tmp_path / "cat.json"
    cat.write_text(json.dumps(itens), encoding="utf-8")
    monkeypatch.setattr(ht, "CATALOGO", cat)
    monkeypatch.setattr(ht, "SKILLS", tmp_path / "skills")
    monkeypatch.setattr(ht, "ESTADO", tmp_path / "estado.json")
    (tmp_path / "skills").mkdir()


def test_instala_so_as_marcadas_e_so_a_pasta_certa(tmp_path, monkeypatch):
    _preparar(tmp_path, monkeypatch, [
        {"id": "ig-reel", "repo": "a/b", "caminho": "skills/ig-reel", "licenca": "MIT", "grupo": "g"},
        {"id": "ig-dm", "repo": "a/b", "caminho": "skills/ig-dm", "licenca": "MIT", "grupo": "g"}])
    z = _zip({"skills/ig-reel/SKILL.md": "x", "skills/ig-reel/s.py": "y", "skills/ig-dm/SKILL.md": "z", "README.md": "r",
              "skills/ig-reel/../../fuga.txt": "nao"})
    chamadas = []
    r = ht.instalar(["ig-reel", "inventada"], baixar=lambda repo: chamadas.append(repo) or z)
    assert r["ok"] == ["ig-reel"] and "inventada" in r["falhou"] and chamadas == ["a/b"]
    assert sorted(p.name for p in (tmp_path / "skills" / "ig-reel").iterdir()) == ["SKILL.md", "s.py"]
    assert not (tmp_path / "skills" / "ig-dm").exists() and not (tmp_path / "fuga.txt").exists()
    st = ht.status()
    assert st["perguntado"] and [i["instalada"] for i in st["itens"]] == [True, False]


def test_pasta_sem_skill_falha_sem_apagar_a_que_existia_e_recusar_marca_perguntado(tmp_path, monkeypatch):
    _preparar(tmp_path, monkeypatch, [{"id": "x", "repo": "a/b", "caminho": "nada", "licenca": "MIT", "grupo": "g"}])
    (tmp_path / "skills" / "x").mkdir()
    (tmp_path / "skills" / "x" / "SKILL.md").write_text("antiga", encoding="utf-8")
    r = ht.instalar(["x"], baixar=lambda repo: _zip({"outra/SKILL.md": "x"}))
    assert "x" in r["falhou"] and (tmp_path / "skills" / "x" / "SKILL.md").read_text(encoding="utf-8") == "antiga"
    assert ht.recusar()["perguntado"] is True


def test_catalogo_real_bem_formado():
    itens = ht.catalogo()
    assert len({i["id"] for i in itens}) == len(itens) >= 50
    assert all(i["repo"].count("/") == 1 and i["licenca"] and i["grupo"] for i in itens)
