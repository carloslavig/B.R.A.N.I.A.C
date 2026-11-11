# -*- coding: utf-8 -*-
"""Isolamento: nenhum teste le ou escreve no cofre REAL da pessoa (Gerenciador de Credenciais / Keychain). Sem isto, quem ja tem chaves salvas
veria testes como 'sem chave -> 503' falharem. So o teste que exercita o cofre de verdade (com nome proprio e limpeza) usa o cofre do sistema."""
import pytest
from braniac_seed import cofre

USA_COFRE_REAL = {"test_cofre_guarda_le_e_remove"}


@pytest.fixture(autouse=True)
def cofre_em_memoria(request, monkeypatch):
    if request.node.name in USA_COFRE_REAL:
        return
    memoria = {}
    monkeypatch.setattr(cofre, "guardar", lambda p, k: memoria.__setitem__(p, k))
    monkeypatch.setattr(cofre, "ler", lambda p: memoria.get(p))
    monkeypatch.setattr(cofre, "tem", lambda p: p in memoria)
    monkeypatch.setattr(cofre, "remover", lambda p: memoria.pop(p, None) is not None)
