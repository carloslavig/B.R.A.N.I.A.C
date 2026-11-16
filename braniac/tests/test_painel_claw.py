import json

from braniac import painel_claw as P


def test_dados_tem_todas_as_secoes_e_nao_vaza_segredo():
    d = P.dados()
    for k in ("agenda_hoje", "rotinas", "assuntos", "manutencao", "propostas_pendentes", "plugins", "financeiro", "vaquinha"):
        assert k in d
    assert d["plugins"] == [] or any(p["nome"] == "photocraft" for p in d["plugins"])      # sem .mcp.json (copia limpa) a lista e vazia
    txt = json.dumps(d)
    assert "cfut_" not in txt and "mstrl_" not in txt and "Users" not in txt            # nunca caminho nem chave


def test_assuntos_trazem_agente_e_contagem_de_fatos():
    a = P.assuntos_com_fatos()
    assert {"Sultão", "Alma", "Cofre"} <= {x["agente"] for x in a} and all(isinstance(x["fatos"], int) for x in a)


def test_javascript_do_painel_tem_sintaxe_valida():
    """O painel quebrou em branco por um erro de aspas no JS: este teste roda `node --check` na pagina (pula se nao houver node)."""
    import shutil
    import subprocess
    import tempfile
    from pathlib import Path
    node = shutil.which("node")
    if not node:
        return
    for nome in ("painel.html", "sauraki.html", "b2.html", "hud.html"):
        html = (Path(__file__).resolve().parent.parent / "ui" / nome).read_text(encoding="utf-8")
        i = html.find("<script>")
        if i < 0:
            continue
        js = html[i + 8:html.rindex("</script>")]
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
            f.write(js)
        r = subprocess.run([node, "--check", f.name], capture_output=True, text=True, creationflags=0x08000000, timeout=60)
        assert r.returncode == 0, nome + ": " + r.stderr[:300]
