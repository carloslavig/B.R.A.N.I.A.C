# -*- coding: utf-8 -*-
import os
import time

from braniac import organizador


def test_organiza_sem_apagar_e_separa_duplicado(tmp_path, monkeypatch):
    monkeypatch.setattr(organizador, "LOG", tmp_path / "log.json")
    velho = time.time() - 3600
    for nome, txt in (("a.pdf", "x"), ("a (1).pdf", "x"), ("setup.exe", "y"), ("novo.jpg", "z"), ("desktop.ini", "i")):
        p = tmp_path / nome
        p.write_text(txt)
        os.utime(p, (velho, velho))
    (tmp_path / "novo.jpg").touch()          # baixado agora: fica quieto
    (tmp_path / "pasta").mkdir()
    movidos = organizador.organizar(tmp_path)
    assert len(movidos) == 3
    assert (tmp_path / "Documentos" / "a.pdf").exists() and (tmp_path / "Duplicados" / "a (1).pdf").exists()
    assert (tmp_path / "Instaladores" / "setup.exe").exists() and (tmp_path / "novo.jpg").exists() and (tmp_path / "desktop.ini").exists()
