# -*- coding: utf-8 -*-
"""Atualizacao automatica pelas releases: so instala com versao maior, hash conferido e host confiavel."""
import hashlib, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from braniac_seed import assistente, auto_update, perfil

EXE = b"MZ-instalador-falso"
URL = "https://github.com/carloslavig/B.R.A.N.I.A.C/releases/download/v9.9.9/BRANIAC_9.9.9_x64-setup.exe"


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("BRANIAC_HOME", str(tmp_path))
    perfil.atualizar(nome_assistente="Aurora", nome_pessoa="Ana", voz="feminina", concluido=True)


def release(tag="v9.9.9", sha=None, asset=True, corpo=True):
    sha = sha or hashlib.sha256(EXE).hexdigest()
    return {"tag_name": tag, "body": f"Notas\nSHA256: {sha}" if corpo else "Notas",
            "assets": [{"name": f"BRANIAC_{tag.lstrip('v')}_x64-setup.exe", "browser_download_url": URL}] if asset else []}


def baixador(rel, exe=EXE):
    return lambda url: json.dumps(rel).encode() if url == auto_update.API else exe


def test_versao_maior_com_hash_certo_instala():
    rodou = []
    r = auto_update.checar_e_atualizar(baixador(release()), executar=rodou.append)
    assert "9.9.9" in r and len(rodou) == 1 and rodou[0].read_bytes() == EXE


def test_mesma_versao_ou_menor_nao_faz_nada():
    rodou = []
    assert "mais nova" in auto_update.checar_e_atualizar(baixador(release(tag="v" + auto_update.__version__)), executar=rodou.append)
    assert not rodou


def test_hash_errado_ou_ausente_nao_instala():
    rodou = []
    assert "SHA-256" in auto_update.checar_e_atualizar(baixador(release(sha="0" * 64)), executar=rodou.append)
    assert "SHA-256" in auto_update.checar_e_atualizar(baixador(release(corpo=False)), executar=rodou.append)
    assert "instalador" in auto_update.checar_e_atualizar(baixador(release(asset=False)), executar=rodou.append)
    assert not rodou


def test_host_nao_confiavel_e_recusado():
    with pytest.raises(auto_update.UpdateErro):
        auto_update._get("https://evil.example.com/BRANIAC_9.9.9_x64-setup.exe")


def test_comandos_de_voz_ligam_e_desligam():
    assert auto_update.ativa()
    assert "desliguei" in assistente.conversar("desligue a atualização automática", planejar=lambda t: pytest.fail("sem IA"))["resposta"]
    assert not auto_update.ativa()
    assert "ligada" in assistente.conversar("ligue a atualização automática", planejar=lambda t: pytest.fail("sem IA"))["resposta"]
    assert auto_update.ativa()
