"""Braniac. Na copia publica, padrao/ traz a configuracao inicial (equipes do predio, modelos gratis) sem dado de ninguem."""
import shutil as _shutil
from pathlib import Path as _Path

_aqui = _Path(__file__).resolve().parent
if (_aqui / "padrao").is_dir():   # so cria o que falta: nunca sobrescreve o data/ de quem ja usa
    for _f in (_aqui / "padrao").rglob("*"):
        _alvo = _aqui / "data" / _f.relative_to(_aqui / "padrao")
        if _f.is_file() and not _alvo.exists():
            _alvo.parent.mkdir(parents=True, exist_ok=True)
            _shutil.copy2(_f, _alvo)
