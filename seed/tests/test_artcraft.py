# -*- coding: utf-8 -*-
"""Ferramentas do ArtCraft: permissao, pasta de saida segura e (se o app estiver instalado) execucao real."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from braniac_seed import artcraft, pc_tools, permissoes


REAL = Path.home() / "Apps" / "ArtCraft"   # instalacao portatil de quem desenvolve (o teste real so roda onde ela existe)


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("BRANIAC_ARTCRAFT", str(REAL))
    monkeypatch.setenv("BRANIAC_HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    yield tmp_path


def _tem(app):
    if not (REAL / app).exists():
        return False
    try:
        artcraft._exe(app)
        return True
    except artcraft.ArtCraftErro:
        return False


def test_sem_permissao_nao_executa_e_nao_aparece_para_a_ia():
    with pytest.raises(permissoes.PermissaoNegada):
        pc_tools.executar_ferramenta("vetor_cartaz", {"texto": "oi"})
    assert "vetor_cartaz" not in pc_tools.catalogo_para_ia()


def test_argumento_obrigatorio_e_opcional():
    permissoes.aplicar_modo("total")
    assert "vetor_cartaz" in pc_tools.catalogo_para_ia()
    with pytest.raises(pc_tools.FerramentaErro, match="texto"):
        pc_tools.executar_ferramenta("vetor_cartaz", {})


def test_saida_sempre_na_pasta_de_criacoes_com_nome_simples():
    s = artcraft._saida(r"..\..\Windows\evil.png", ".png")
    assert s.parent == artcraft.pasta_saida() and s.name == "evil.png"
    assert artcraft._saida("relatorio", ".pdf").name == "relatorio.pdf"
    assert artcraft._saida("a.exe", ".png").name == "a.png"


@pytest.mark.skipif(not _tem("vectorcraft"), reason="ArtCraft nao instalado")
def test_cartaz_real_e_conversao_de_foto(ambiente):
    texto, img = artcraft.vetor_cartaz("Teste", "c.png")
    assert img and (artcraft.pasta_saida() / "c.png").is_file()
    if _tem("photocraft"):
        artcraft.foto_redimensionar(str(artcraft.pasta_saida() / "c.png"), "p.png", "200")
        assert (artcraft.pasta_saida() / "p.png").is_file()


def test_atualizacao_libera_permissoes_novas_so_para_quem_escolheu_total(ambiente):
    from braniac_seed import perfil
    import json
    antigas = [c for c in permissoes.CATALOGO if not c.startswith("criativo")]
    arq = permissoes._arq()
    for modo, esperado in (("total", True), ("granular", False)):
        perfil.atualizar(consentimento_acesso_pc=modo)
        arq.write_text(json.dumps({"liberadas": antigas, "registro": []}), encoding="utf-8")   # arquivo gravado pela versao 0.4
        assert permissoes.permitido("criativo.vetor") is esperado
    perfil.atualizar(consentimento_acesso_pc="total")
    permissoes.aplicar_modo("total")
    permissoes.revogar("criativo.vetor")
    assert not permissoes.permitido("criativo.vetor")      # revogar continua valendo depois de uma nova leitura


def test_json_de_texto_puro_do_navegador_nao_quebra():
    import http.server, threading
    from braniac_seed import navegador

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(b"Target activated")
        log_message = lambda *a: None
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    navegador.PORTA, antes = srv.server_port, navegador.PORTA
    try:
        assert navegador._json("/json/activate/x") == "Target activated"
    finally:
        navegador.PORTA = antes
        srv.shutdown()


def test_desenho_livre_valida_entrada():
    with pytest.raises(artcraft.ArtCraftErro, match="Cor inválida"):
        artcraft._passos_desenho([{"t": "rect", "x": 0, "y": 0, "w": 5, "h": 5, "cor": "vermelho"}])
    with pytest.raises(artcraft.ArtCraftErro, match="inválido"):
        artcraft._passos_desenho([{"t": "caminho", "d": "M0 0 L1 1; rm -rf"}])
    with pytest.raises(artcraft.ArtCraftErro, match="desconhecida"):
        artcraft._passos_desenho([{"t": "foguete"}])
    with pytest.raises(artcraft.ArtCraftErro, match="JSON"):
        artcraft._passos_desenho("não é json")


@pytest.mark.skipif(not _tem("vectorcraft"), reason="ArtCraft nao instalado")
def test_desenho_livre_real():
    formas = [{"t": "rect", "x": 0, "y": 0, "w": 612, "h": 792, "cor": "#87ceeb"}, {"t": "elipse", "x": 200, "y": 200, "w": 200, "h": 200, "cor": "#ffd700", "borda": "#ff8800", "largura": 6},
              {"t": "caminho", "d": "M100 700 L300 500 L500 700 Z", "cor": "#228b22"}, {"t": "linha", "x1": 0, "y1": 700, "x2": 612, "y2": 700, "borda": "#000000"},
              {"t": "estrela", "cx": 100, "cy": 100, "r1": 50, "r2": 20, "cor": "#ffffff"}, {"t": "texto", "x": 150, "y": 740, "texto": "Oi", "tam": 30, "cor": "#000000"}]
    texto, img = artcraft.vetor_desenhar(formas, "d.png")
    assert img and len(img) > 2000
