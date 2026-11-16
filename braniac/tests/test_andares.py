import json
import re
from pathlib import Path

import pytest

from braniac import andares


def test_sem_arquivo_e_o_predio_todo_e_construir_acrescenta_na_ordem(tmp_path, monkeypatch):
    monkeypatch.setattr(andares, "ARQ", tmp_path / "predio.json")
    monkeypatch.setattr(andares, "_indisponiveis", lambda: ["esteira"])
    assert andares.estado()["andares"] is None
    (tmp_path / "predio.json").write_text(json.dumps({"andares": ["terreo", "escritorio", "cobertura"]}), encoding="utf-8")
    assert andares.construir("nexodev")["andares"] == ["terreo", "nexodev", "escritorio", "cobertura"]
    with pytest.raises(ValueError):
        andares.construir("esteira")
    with pytest.raises(ValueError):
        andares.construir("<script>")


def test_lista_igual_a_do_predio_3d():
    html = (Path(andares.__file__).parent / "ui" / "sauraki-real.html").read_text(encoding="utf-8")
    ordem = json.loads(re.search(r"var ORDEM=(\[[^\]]+\])", html).group(1))
    assert ordem == andares.TODOS
    assert json.loads((Path(andares.__file__).parent / "padrao" / "predio.json").read_text(encoding="utf-8"))["andares"] == list(andares.FIXOS)
