import builtins
from pathlib import Path
from braniac.skills import catalogo, listar

def test_catalogo_returns_string():
    # Ensure the function returns a string even if no skills are present
    result = catalogo(base=Path(__file__).parent / 'nonexistent')
    assert isinstance(result, str)

def test_listar_consistency():
    # Listing with the default base should return a list of tuples
    result = listar()
    assert isinstance(result, list)
    if result:
        for item in result:
            assert isinstance(item, tuple) and len(item) == 3
