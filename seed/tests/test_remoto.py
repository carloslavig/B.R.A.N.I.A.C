# -*- coding: utf-8 -*-
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from braniac_seed import cofre, pc_tools, permissoes, remoto

DONO, OUTRO = 111, 222


@pytest.fixture(autouse=True)
def casa(tmp_path, monkeypatch):
    monkeypatch.setenv("BRANIAC_HOME", str(tmp_path))
    monkeypatch.setattr(cofre, "guardar", lambda p, k: None)


def upd(de, texto, tipo="private"):
    return {"update_id": 1, "message": {"text": texto, "from": {"id": de}, "chat": {"id": de, "type": tipo}}}


def bot(plano=None, conversa="oi!"):
    chamadas = []

    def planejar(t):
        chamadas.append(t)
        return plano or {"acao": "nenhuma", "args": {}, "resposta": "ok"}
    b = remoto.Bot(token=None, planejar=planejar, conversar=lambda t: conversa)
    b.chamadas = chamadas
    return b


def parear(b, de=DONO):
    cod = remoto.novo_codigo()
    b.tratar(upd(de, f"/parear {cod}"))


def textos(b):
    return [t for k, c, t in b.enviados if k == "texto"]


# ---------- pareamento ----------

def test_estranho_sem_pareamento_e_ignorado():
    b = bot()
    b.tratar(upd(OUTRO, "abre a calculadora"))
    b.tratar(upd(OUTRO, "/parear ABC123"))
    assert b.enviados == [] and not remoto.resumo()["pareado"]


def test_pareia_com_codigo_correto_e_so_uma_vez():
    b = bot()
    parear(b)
    assert remoto.resumo()["pareado"] and "Pareado" in textos(b)[0]
    cod = remoto.novo_codigo()                       # outro codigo existe, mas o dono ja esta definido
    b.enviados.clear()
    b.tratar(upd(OUTRO, f"/parear {cod}"))
    assert b.enviados == [] and remoto._estado()["dono_id"] == DONO


def test_codigo_errado_ou_expirado_nao_pareia(monkeypatch):
    b = bot()
    remoto.novo_codigo()
    b.tratar(upd(DONO, "/parear ZZZZZZ"))
    assert not remoto.resumo()["pareado"]
    cod = remoto.novo_codigo()
    e = remoto._estado()
    e["pareamento"]["ate"] = time.time() - 1
    remoto._salvar(e)
    b.tratar(upd(DONO, f"/parear {cod}"))
    assert not remoto.resumo()["pareado"]


def test_grupo_e_ignorado_mesmo_do_dono():
    b = bot()
    parear(b)
    b.enviados.clear()
    b.tratar(upd(DONO, "/status", tipo="group"))
    assert b.enviados == []


def test_nao_dono_e_ignorado_depois_do_pareamento():
    b = bot()
    parear(b)
    b.enviados.clear()
    b.tratar(upd(OUTRO, "apaga tudo"))
    assert b.enviados == [] and not b.chamadas


# ---------- armado / desarmado ----------

def test_desarmado_so_conversa_e_nunca_chama_o_planejador():
    b = bot(conversa="claro, mas sem mexer no PC")
    parear(b)
    b.enviados.clear()
    b.tratar(upd(DONO, "abre a calculadora"))
    assert "desarmado" in textos(b)[0] and not b.chamadas


def test_telegram_nao_consegue_armar():
    b = bot()
    parear(b)
    for t in ("/armar", "/armar sempre", "arma o controle remoto", "armar"):
        b.tratar(upd(DONO, t))
    assert not remoto.armado()


def test_armar_exige_pareamento():
    with pytest.raises(remoto.RemotoErro):
        remoto.armar(60)


def test_armado_expira():
    b = bot()
    parear(b)
    remoto.armar(1)
    assert remoto.armado()
    e = remoto._estado()
    e["armado_ate"] = time.time() - 1
    remoto._salvar(e)
    assert not remoto.armado()


def test_parar_desarma_na_hora():
    b = bot()
    parear(b)
    remoto.armar(None)
    b.tratar(upd(DONO, "/parar"))
    assert not remoto.armado() and "DESARMADO" in textos(b)[-1]


# ---------- permissoes e confirmacao ----------

def test_acao_sem_permissao_e_negada():
    b = bot({"acao": "status_pc", "args": {}, "resposta": ""})
    parear(b)
    remoto.armar(None)
    b.enviados.clear()
    b.tratar(upd(DONO, "como está o pc?"))
    assert "🚫" in textos(b)[0]


def test_acao_liberada_executa_sem_confirmar(monkeypatch):
    permissoes.conceder("sistema.status")
    b = bot({"acao": "status_pc", "args": {}, "resposta": ""})
    parear(b)
    remoto.armar(None)
    b.enviados.clear()
    b.tratar(upd(DONO, "como está o pc?"))
    assert "Memória" in textos(b)[0] and b.chamadas == ["como está o pc?"]


def _armar_com_perigo(tmp_path, monkeypatch):
    permissoes.conceder("programas.executar")
    feitos = []
    monkeypatch.setitem(pc_tools.FERRAMENTAS, "executar", ("x", ["comando"], "programas.executar", True, lambda comando: feitos.append(comando) or "rodou"))
    b = bot({"acao": "executar", "args": {"comando": "echo oi"}, "resposta": ""})
    parear(b)
    remoto.armar(None)
    b.enviados.clear()
    return b, feitos


def test_acao_perigosa_pede_codigo_e_so_roda_com_ele(tmp_path, monkeypatch):
    b, feitos = _armar_com_perigo(tmp_path, monkeypatch)
    b.tratar(upd(DONO, "roda echo oi"))
    assert not feitos and "SIM" in textos(b)[0]
    cod = remoto._estado()["pendente"]["codigo"]
    b.tratar(upd(DONO, "SIM 0000" if cod != "0000" else "SIM 1111"))
    assert not feitos
    b.tratar(upd(DONO, "roda echo oi"))
    cod = remoto._estado()["pendente"]["codigo"]
    b.tratar(upd(DONO, f"SIM {cod}"))
    assert feitos == ["echo oi"]
    b.tratar(upd(DONO, f"SIM {cod}"))                 # uso unico
    assert feitos == ["echo oi"]


def test_confirmacao_cancelada_ou_expirada_nao_executa(tmp_path, monkeypatch):
    b, feitos = _armar_com_perigo(tmp_path, monkeypatch)
    b.tratar(upd(DONO, "roda"))
    b.tratar(upd(DONO, "não"))
    assert not feitos and "pendente" not in remoto._estado()
    b.tratar(upd(DONO, "roda"))
    e = remoto._estado()
    cod = e["pendente"]["codigo"]
    e["pendente"]["ate"] = time.time() - 1
    remoto._salvar(e)
    b.tratar(upd(DONO, f"SIM {cod}"))
    assert not feitos


def test_confirmacao_nao_vale_se_desarmaram_no_meio(tmp_path, monkeypatch):
    b, feitos = _armar_com_perigo(tmp_path, monkeypatch)
    b.tratar(upd(DONO, "roda"))
    cod = remoto._estado()["pendente"]["codigo"]
    remoto.desarmar()
    b.tratar(upd(DONO, f"SIM {cod}"))
    assert not feitos


def test_limite_de_comandos_por_minuto():
    b = bot()
    parear(b)
    for _ in range(remoto.LIMITE_POR_MIN + 3):
        b.tratar(upd(DONO, "/status"))
    assert any("Muitos comandos" in t for t in textos(b))


def test_acao_inexistente_inventada_pela_ia_e_ignorada():
    b = bot({"acao": "formatar_disco", "args": {}, "resposta": "feito"})
    parear(b)
    remoto.armar(None)
    b.enviados.clear()
    b.tratar(upd(DONO, "faz algo"))
    assert textos(b) == ["feito"]                     # so devolve o texto; nenhuma ferramenta e chamada


def test_auditoria_registra_tudo():
    b = bot()
    parear(b)
    b.tratar(upd(OUTRO, "oi"))
    b.tratar(upd(DONO, "/status"))
    log = (Path(__import__("os").environ["BRANIAC_HOME"]) / "remoto.log").read_text(encoding="utf-8")
    assert "PAREADO" in log and "não é o dono" in log and "dono: /status" in log


# ---------- token ----------

def test_token_invalido_nao_e_aceito_nem_guardado():
    with pytest.raises(remoto.RemotoErro):
        remoto.cadastrar_token("abc")
    with pytest.raises(remoto.RemotoErro):
        remoto.cadastrar_token("123456789:" + "A" * 35, http=lambda m, t, d=None, timeout=0: {"ok": False})


def test_token_valido_guarda_no_cofre(monkeypatch):
    guardado = []
    monkeypatch.setattr(cofre, "guardar", lambda p, k: guardado.append(p))
    bot_nome = remoto.cadastrar_token("123456789:" + "A" * 35, http=lambda m, t, d=None, timeout=0: {"ok": True, "result": {"username": "meu_bot"}})
    assert bot_nome == "meu_bot" and guardado == ["telegram"] and remoto.resumo()["bot"] == "meu_bot"


def test_planejador_interpreta_json_e_texto_solto(monkeypatch):
    monkeypatch.setattr(remoto.llm, "responder", lambda t, sistema="": ('claro: {"acao":"abrir","args":{"alvo":"calculadora"},"resposta":"abrindo"}', "x"))
    assert remoto._planejar_padrao("abre a calculadora")["acao"] == "abrir"
    monkeypatch.setattr(remoto.llm, "responder", lambda t, sistema="": ("só conversa", "x"))
    assert remoto._planejar_padrao("oi")["acao"] == "nenhuma"


# ---------- ferramentas ----------

def test_locais_protegidos_sao_recusados(tmp_path):
    with pytest.raises(pc_tools.FerramentaErro):
        pc_tools._caminho(str(Path.home() / ".ssh" / "id_rsa"), existe=False)
    with pytest.raises(pc_tools.FerramentaErro):
        pc_tools._caminho(str(tmp_path / "BRANIAC-dados" / "perfil.json"), existe=False)


def test_comando_destrutivo_e_recusado():
    for c in ("Format-Volume -DriveLetter D", "diskpart", "net user admin x /add"):
        with pytest.raises(pc_tools.FerramentaErro):
            pc_tools.executar(c)


def test_ler_escrever_listar_em_pasta_comum(tmp_path):
    arq = tmp_path / "a.txt"
    assert "Criei" in pc_tools.escrever_arquivo(str(arq), "olá mundo")
    assert pc_tools.ler_arquivo(str(arq)) == "olá mundo"
    assert "a.txt" in pc_tools.listar_pasta(str(tmp_path))
    (tmp_path / "bin.dat").write_bytes(b"\x00\x01\x02")
    with pytest.raises(pc_tools.FerramentaErro):
        pc_tools.ler_arquivo(str(tmp_path / "bin.dat"))


def test_executar_ferramenta_exige_permissao_e_argumentos(tmp_path):
    with pytest.raises(permissoes.PermissaoNegada):
        pc_tools.executar_ferramenta("listar_pasta", {"caminho": str(tmp_path)})
    permissoes.conceder("arquivos.ler")
    with pytest.raises(pc_tools.FerramentaErro):
        pc_tools.executar_ferramenta("listar_pasta", {})
    assert "itens" in pc_tools.executar_ferramenta("listar_pasta", {"caminho": str(tmp_path)})[0]


def test_ia_so_ve_as_ferramentas_liberadas():
    assert pc_tools.catalogo_para_ia() == ""
    permissoes.conceder("arquivos.ler")
    cat = pc_tools.catalogo_para_ia()
    assert "listar_pasta" in cat and "apagar" not in cat and "executar" not in cat
