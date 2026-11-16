import json
from braniac import organiza_claude as oc


def _perfil(tmp_path):
    p = tmp_path / "Claude-X"
    pasta = p / "claude-code-sessions" / "conta" / "org"
    pasta.mkdir(parents=True)
    (p / "claude_desktop_config.json").write_text(json.dumps({"preferences": {"epitaxyPrefs": {"dframe-group-scopes": {"conta/org": {
        "groups": [{"id": "cg-1", "name": "🎬 Parceiro / Vídeos", "mode": "code"}], "assignments": {"code:local_b": "cg-1"}, "order": {"cg-1": ["code:local_b"]}}}}}}), encoding="utf-8")
    for sid, titulo in [("local_a", "Vídeo de Itatim"), ("local_b", "✅ Concluída · Esteira"), ("local_c", "▶️ Jarvis novo")]:
        (pasta / f"{sid}.json").write_text(json.dumps({"sessionId": sid, "title": titulo, "cwd": "C:\\x", "isArchived": False}), encoding="utf-8")
    return p, pasta


def test_organiza_titulo_e_secao(tmp_path, monkeypatch):
    monkeypatch.setattr(oc, "DATA", tmp_path / "bak")
    p, pasta = _perfil(tmp_path)
    oc.organizar_perfil(p)
    t = lambda sid: json.loads((pasta / f"{sid}.json").read_text(encoding="utf-8"))["title"]
    assert t("local_a") == "🟡 Parada · Vídeo de Itatim"
    assert t("local_b") == "✅ Concluída · Esteira"          # já tinha status: intocado
    assert t("local_c") == "🟡 Parada · Jarvis novo"         # app fechado: nada roda
    esc = json.loads((p / "claude_desktop_config.json").read_text(encoding="utf-8"))["preferences"]["epitaxyPrefs"]["dframe-group-scopes"]["conta/org"]
    assert esc["assignments"]["code:local_a"] == "cg-1"      # foi para a seção que já existia
    nomes = {g["id"]: g["name"] for g in esc["groups"]}
    assert nomes[esc["assignments"]["code:local_c"]] == oc.PADRAO   # seção criada
    assert list((tmp_path / "bak").glob("*.json"))           # cópia antes de gravar
    assert oc.organizar_perfil(p) == []                      # segunda vez não muda nada


def test_nao_grava_com_app_aberto(monkeypatch):
    monkeypatch.setattr(oc, "app_aberto", lambda: True)
    monkeypatch.setattr(oc, "perfis", lambda: (_ for _ in ()).throw(AssertionError("não devia ler")))
    assert oc.ciclo() == []
