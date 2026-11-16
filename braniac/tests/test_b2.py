# -*- coding: utf-8 -*-
"""B.R.A.N.I.A.C 2: projetos/conversas separados, habilidades criadas pela interface e o Jarvis mexendo no PC com limites."""
import pytest
from braniac import b2, pc


@pytest.fixture(autouse=True)
def isolado(tmp_path, monkeypatch):
    monkeypatch.setattr(b2, "DB", tmp_path / "b2.db")
    monkeypatch.setattr(b2, "SKILLS", tmp_path / "skills")


def test_projeto_conversa_e_contexto():
    e = b2.acao({"acao": "criar_projeto", "nome": "Sites", "instrucoes": "Responda curto."})
    pid = e["novo"]
    c = b2.acao({"acao": "criar_conversa", "projeto": pid})["novo"]
    assert "[Projeto: Sites. Instrucoes do projeto: Responda curto.]" in b2.contexto_da_conversa(c)
    b2.titulo_inicial(c, "Arrumar o site da Loja")
    assert [v["titulo"] for v in b2.estado()["conversas"]] == ["Arrumar o site da Loja"]
    b2.acao({"acao": "arquivar", "id": c})
    assert b2.estado()["conversas"] == []          # arquivar so esconde
    with pytest.raises(ValueError):
        b2.acao({"acao": "criar_projeto", "nome": ""})


def test_criar_skill_nao_sobrescreve_e_valida():
    nome = b2.criar_skill("Responder Hóspede!", "quando hospede perguntar do check-in", "1. ler\n2. responder", "airbnb_ler rm -rf")
    md = (b2.SKILLS / nome / "SKILL.md").read_text(encoding="utf-8")
    assert nome == "responder-h-spede" and "allowed-tools: airbnb_ler rm rf" in md and "name: responder-h-spede" in md
    with pytest.raises(ValueError):
        b2.criar_skill("Responder Hóspede!", "x", "y")
    with pytest.raises(ValueError):
        b2.criar_skill("sem passos", "x", "")


def test_pc_nunca_abre_executavel_e_busca_por_nome(tmp_path, monkeypatch):
    (tmp_path / "virus.exe").write_text("x")
    abertos = []
    monkeypatch.setattr(pc.os, "startfile", lambda p: abertos.append(p), raising=False)
    assert "Nao abro .exe" in pc.abrir(str(tmp_path / "virus.exe")) and not abertos
    assert "Abri a pasta" in pc.abrir(str(tmp_path)) and abertos
    (tmp_path / "Curriculo_Dono.pdf").write_text("x")
    monkeypatch.setattr(pc, "RAIZES", [tmp_path])
    assert "Curriculo_Dono.pdf" in pc.procurar("curriculo")
    assert "virus.exe" in pc.listar(str(tmp_path)) and "Nao achei" in pc.abrir(str(tmp_path / "nada"))


class _Store:
    def __init__(self, rows):
        import sqlite3
        self.db = sqlite3.connect(":memory:")
        self.db.execute("CREATE TABLE msgs(id INTEGER PRIMARY KEY, conv TEXT, role TEXT, content TEXT, provider TEXT, ts REAL)")
        self.db.executemany("INSERT INTO msgs(conv,role,content,provider,ts) VALUES(?,?,?,?,?)", rows)


def test_procurar_conversas_acha_trecho_com_data():
    st = _Store([("jarvis", "user", "combinei o site da Cliente por 300", None, 1792000000), ("b2:1", "assistant", "ok [Projeto: Geral.]", None, 1792000100)])
    r = b2.procurar_conversas(st, "Cliente")
    assert "Dono: combinei o site da Cliente por 300" in r and "[jarvis]" in r
    assert "Nao achei" in b2.procurar_conversas(st, "inexistente") and "3 letras" in b2.procurar_conversas(st, "ab")


class _Router:
    def __init__(self, resp):
        self.resp, self.chamou = resp, 0

    def responder_neutro(self, s, t):
        self.chamou += 1
        return self.resp


def test_aprender_cria_habilidade_so_em_tarefa_complexa_e_com_limite(monkeypatch):
    monkeypatch.setitem(b2._APRENDIDAS, "dia", None)
    js = '{"vale": true, "nome": "agendar-dentista", "descricao": "quando pedir para marcar dentista", "passos": "1. agenda\n2. pc", "ferramentas": "agenda pc"}'
    r = _Router(js)
    assert b2.aprender(r, "marca dentista", [("agenda", "ok"), ("pc", "ok")]) is None and r.chamou == 0     # so 2 ferramentas: nem pergunta
    notas = []
    assert b2.aprender(r, "marca dentista", [("agenda", "ok"), ("pc", "ok"), ("pesquisar_web", "ok")], notas.append) == "agendar-dentista"
    assert (b2.SKILLS / "agendar-dentista" / "SKILL.md").exists() and "aprendeu" in notas[0]
    assert b2.aprender(_Router('{"vale": false}'), "x", [("a", ""), ("b", ""), ("c", "")]) is None
    monkeypatch.setitem(b2._APRENDIDAS, "n", b2.MAX_APRENDIDAS_DIA)
    assert b2.aprender(_Router(js.replace("agendar-dentista", "outra")), "x", [("a", ""), ("b", ""), ("c", "")]) is None


def test_conselho_aceita_tema_com_chaves():
    from braniac import conselho
    vistos = []
    rel = conselho.reunir("criar rota que responde {'relatorio': x} no servidor", lambda ia, p: vistos.append(p) or "ok", None)
    assert "{'relatorio': x}" in vistos[0] and "<PAPEL>" not in vistos[0] and "Conselho" in rel


def test_salvar_chave_pela_interface(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("GROQ_API_KEY=abc\nCEREBRAS_API_KEY=\n", encoding="utf-8")
    monkeypatch.delenv("CEREBRAS_API_KEY", raising=False)
    from braniac import segredos
    monkeypatch.setattr(segredos, "proteger", lambda v: v)      # sem DPAPI no teste: grava como veio
    monkeypatch.setattr(segredos, "revelar", lambda v: v)
    r = b2.salvar_chave("CEREBRAS_API_KEY", " csk-1234567890abcdef ", arquivo=env)
    assert r["ok"] and b2.os.environ["CEREBRAS_API_KEY"] == "csk-1234567890abcdef"
    linhas = env.read_text(encoding="utf-8").splitlines()
    assert "GROQ_API_KEY=abc" in linhas and "CEREBRAS_API_KEY=csk-1234567890abcdef" in linhas
    b2.salvar_chave("NVIDIA_API_KEY", "nvapi-abcdef123456", arquivo=env)           # variavel nova: acrescenta no fim
    assert env.read_text(encoding="utf-8").splitlines()[-1] == "NVIDIA_API_KEY=nvapi-abcdef123456"
    assert "csk-1234" not in str(b2.chaves())                                        # a listagem nunca traz o valor
    assert next(c for c in b2.chaves() if c["env"] == "CEREBRAS_API_KEY")["ativa"]
    for ruim in ("curto", "com espaco no meio xx", "x" * 500):
        with pytest.raises(ValueError):
            b2.salvar_chave("MISTRAL_API_KEY", ruim, arquivo=env)
    with pytest.raises(ValueError):
        b2.salvar_chave("PATH", "valorvalido123", arquivo=env)                      # so as variaveis conhecidas


def test_anexo_e_audio_em_pedacos_e_leitura_da_imagem(tmp_path, monkeypatch):
    import base64
    monkeypatch.setattr(b2, "ANEXOS", tmp_path / "anexos")
    dados = b"\x89PNG" + bytes(range(256)) * 40
    t = base64.b64encode(dados).decode()
    partes = [t[i:i + 3000] for i in range(0, len(t), 3000)]
    for i, p in enumerate(partes[:-1]):
        assert b2.juntar_partes({"id": "x", "i": i, "n": len(partes), "parte": p}) is None
    assert b2.juntar_partes({"id": "x", "i": len(partes) - 1, "n": len(partes), "parte": partes[-1]}) == dados   # fora de ordem tambem: indexa por i
    r = b2.salvar_anexo(dados, descrever=lambda d, i, t: "um logo vermelho")
    assert r["descricao"] == "um logo vermelho" and r["caminho"].endswith(".png") and open(r["caminho"], "rb").read() == dados
    assert "nao consegui" in b2.salvar_anexo(dados, descrever=lambda d, i, t: 1 / 0)["descricao"]
    with pytest.raises(ValueError):
        b2.juntar_partes({"id": "", "i": 0, "n": 1, "parte": ""})
