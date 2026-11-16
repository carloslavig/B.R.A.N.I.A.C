# -*- coding: utf-8 -*-
from datetime import datetime

from braniac import empresa_dev as E


def _isolar(tmp_path, monkeypatch, respostas):
    monkeypatch.setattr(E, "PASTA", tmp_path)
    monkeypatch.setattr(E, "PROJETOS", tmp_path / "projetos")
    monkeypatch.setattr(E, "EQUIPE_JSON", tmp_path / "equipe.json")
    monkeypatch.setattr(E, "TICKETS_JSON", tmp_path / "tickets.json")
    monkeypatch.setattr(E, "_codar_web", lambda sistema, prompt: None)       # testes nunca abrem IA web
    fila = list(respostas)
    monkeypatch.setattr(E, "_ia", lambda sistema, prompt: fila.pop(0) if fila else "APROVADO ok")


def test_ticket_recusa_segredo_e_roteia_por_area(tmp_path, monkeypatch):
    _isolar(tmp_path, monkeypatch, [])
    t, msg = E.abrir("loja", "guardar a senha do cliente", "")
    assert t is None and "recusado" in msg
    t, _ = E.abrir("Loja Loja", "Criar endpoint de pedidos", "rota REST para listar pedidos")
    assert t["area"] == "api" and t["responsavel"] == "Ravi" and t["projeto"] == "loja-loja"
    t2, _ = E.abrir("loja", "Ajustar botão do site", "css do botão")
    assert t2["area"] == "front" and t2["responsavel"] == "Nina"


def test_fluxo_completo_ate_pronto_e_reprovacao_volta(tmp_path, monkeypatch):
    # dev entrega, revisao reprova, dev corrige, revisao aprova, qa aprova
    _isolar(tmp_path, monkeypatch, ["codigo v1", "REPROVADO falta tratar erro", "codigo v2", "APROVADO bom", "APROVADO testes ok"])
    E.abrir("app", "Criar tela de login", "html css botao")
    feitos = E.trabalhar()
    t = E._tickets()[0]
    assert t["estado"] == "pronto" and t["tentativas"] == 2 and len(feitos) == 5
    assert (tmp_path / "projetos" / "app").exists() and len(list((tmp_path / "projetos" / "app").glob("T001-*"))) == 2


def test_teto_diario_e_senior_so_quando_critico(tmp_path, monkeypatch):
    _isolar(tmp_path, monkeypatch, [])
    chamados, original = [], E.senior_revisa
    monkeypatch.setattr(E, "senior_revisa", lambda t, e, ao=None: chamados.append(t["id"]) or True)
    E.abrir("app", "Banco de dados do estoque", "sql", critico=True)
    E.abrir("app", "Outro ajuste simples de css", "css")
    E.trabalhar(maximo=2)
    assert chamados == ["T001"] and E._tickets()[0]["estado"] == "bloqueado"
    for _ in range(E.MAX_CLAUDE_DIA):
        E._somar("claude")
    assert original({"id": "X", "projeto": "p", "titulo": "t", "critico": True, "tentativas": 0}, "") is False


def test_tick_so_em_dia_util_e_horario(tmp_path, monkeypatch):
    _isolar(tmp_path, monkeypatch, [])
    assert E.tick(datetime(2026, 11, 1, 10, 0)) == []        # domingo
    assert E.tick(datetime(2026, 11, 2, 22, 0)) == []        # noite


def test_aprovar_so_pronto_e_quadro(tmp_path, monkeypatch):
    _isolar(tmp_path, monkeypatch, ["codigo", "APROVADO", "APROVADO"])
    E.abrir("app", "Criar tela de login", "html css botao")
    assert "ainda não está pronto" in E.aprovar("T001")
    E.trabalhar()
    assert "entregue" in E.aprovar("t001") and "[entregue]" in E.quadro()


def test_git_branch_por_ticket_e_merge_no_aprovar(tmp_path, monkeypatch):
    import shutil
    if not shutil.which("git"):
        return
    _isolar(tmp_path, monkeypatch, ["codigo", "APROVADO", "APROVADO"])
    E.abrir("app", "Criar tela de login", "html css botao")
    E.trabalhar()
    d = tmp_path / "projetos" / "app"
    assert E._git(d, "rev-parse", "--verify", "t001")[0]
    assert "T001" not in E._git(d, "ls-tree", "--name-only", "main")[1]       # ainda so na branch
    assert "mesclado" in E.aprovar("T001")
    assert "T001-" in E._git(d, "ls-tree", "--name-only", "main")[1]


def test_projetos_diferentes_andam_juntos(tmp_path, monkeypatch):
    _isolar(tmp_path, monkeypatch, [])
    E.abrir("a", "Tela A de login", "css")
    E.abrir("b", "Tela B de login", "css")
    E.abrir("a", "Outra tela A", "css")
    feitos = E.trabalhar(maximo=2)
    assert len(feitos) == 2
    est = {t["id"]: t["estado"] for t in E._tickets()}
    assert est["T001"] == "revisao" and est["T002"] == "revisao" and est["T003"] == "novo"     # T003 e do mesmo projeto de T001: espera a vez


def test_extrai_arquivos_do_texto_e_barra_caminho_perigoso():
    txt = ("Resumo.\n**app.py**\n```python\nprint('oi')\n```\n"
           "```html\n<!-- web/index.html -->\n<p>oi</p>\n```\n"
           "`../../fora.py`\n```python\nx=1\n```\n`run.exe`\n```\nlixo\n```\n")
    r = E.extrair_arquivos(txt)
    assert set(r) == {"app.py", "web/index.html"} and r["app.py"].strip() == "print('oi')"


def test_extrai_arquivos_por_marcador():
    txt = ("resumo\n=== ARQUIVO: src/main.rs ===\nfn main() {}\n=== FIM ===\n"
           "=== ARQUIVO: ../x.rs ===\nruim\n=== FIM ===")
    assert E.extrair_arquivos(txt) == {"src/main.rs": "fn main() {}"}


def test_build_rs_barrado_e_sem_repo_nao_quebra(tmp_path, monkeypatch):
    _isolar(tmp_path, monkeypatch, [])
    assert E.extrair_arquivos("=== ARQUIVO: build.rs ===\nfn main(){}\n=== FIM ===") == {}
    assert E.verificar_build({"id": "T001", "projeto": "nenhum"})[0] is None
