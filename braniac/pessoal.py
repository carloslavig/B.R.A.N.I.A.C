"""Dados pessoais do dono (nome completo, numeros, e-mail, meta de conta, dossie): ficam SO em data/pessoal.json (fora do Git).
O codigo traz apenas padroes genericos; sem o arquivo, o Braniac funciona sem esses detalhes."""
import json
from pathlib import Path

ARQUIVO = Path(__file__).parent / "data" / "pessoal.json"


def _ler():
    try:
        return json.loads(ARQUIVO.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get(chave, padrao=None):
    v = _ler().get(chave)
    return padrao if v is None else v
