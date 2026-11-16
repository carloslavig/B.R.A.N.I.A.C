# -*- coding: utf-8 -*-
from braniac import pendencias


def test_painel_junta_ok_e_erros(monkeypatch):
    monkeypatch.setattr(pendencias, "_prop", lambda: [{"agente": "Alma/Forja", "tipo": "ok", "titulo": "x"}])
    monkeypatch.setattr(pendencias, "_reservas", lambda: [])
    monkeypatch.setattr(pendencias, "_so_dono", lambda: [])
    monkeypatch.setattr(pendencias, "_erros", lambda: [{"agente": "Forja", "tipo": "erro", "titulo": "y"}])
    p = pendencias.painel()
    assert p["total"] == 2 and len(p["aguardando"]) == 1 and p["erros"][0]["agente"] == "Forja"


def test_nenhuma_rotina_manda_pendencia_sozinha():
    """Regra do Dono (15/11/2026): pendência só quando ele pergunta. Fora do painel/consulta, ninguém chama fala()."""
    from pathlib import Path
    assert not hasattr(pendencias, "cobrar")
    raiz = Path(pendencias.__file__).parent
    for f in raiz.rglob("*.py"):
        if "tests" in f.parts or "bak" in f.name or f.name in ("pendencias.py", "delegacao.py", "server.py"):
            continue
        txt = f.read_text(encoding="utf-8", errors="replace")
        assert "pendencias.fala" not in txt and "pendencias.cobrar" not in txt, f.name


def test_pergunta_devolve_a_lista_em_audio(monkeypatch):
    from braniac import delegacao
    monkeypatch.setattr(pendencias, "painel", lambda: {"so_dono": [{"agente": "Gmail", "titulo": "Conectar (uma vez)"}], "aguardando": [], "total": 1})
    for pergunta in ("tem alguma pendência?", "o que tá pendente?"):
        r = delegacao.atender(pergunta)
        assert r["agentes"] == ["Mapa"] and "Gmail: Conectar" in r["texto"] and r["local_only"], pergunta
    assert "Mapa" in delegacao.DIRETOS     # jarvis.processar manda os DIRETOS também em áudio


def test_sem_pendencia_responde_que_nao_tem(monkeypatch):
    monkeypatch.setattr(pendencias, "painel", lambda: {"so_dono": [], "aguardando": [], "total": 0})
    assert "Nenhuma pendência" in pendencias.fala()


def test_so_dono_le_lista(monkeypatch, tmp_path):
    (tmp_path / "pendencias_dono.md").write_text("# t\n- [Gmail] Conectar o Gmail\ntexto solto\n", encoding="utf-8")
    monkeypatch.setattr(pendencias, "DATA", tmp_path)
    assert pendencias._so_dono() == [{"agente": "Gmail", "tipo": "dono", "titulo": "Conectar o Gmail", "detalhe": "", "ts": 0}]
