# -*- coding: utf-8 -*-
import hashlib, io, json, sys, urllib.error, zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from braniac_seed import atualizador, cofre, hardware, nomes, onboarding, perfil, permissoes, provedores


@pytest.fixture(autouse=True)
def casa(tmp_path, monkeypatch):
    monkeypatch.setenv("BRANIAC_HOME", str(tmp_path))     # nada toca o PC real
    return tmp_path


# ---------- permissoes ----------

def test_nada_vem_liberado():
    assert not any(permissoes.permitido(c) for c in permissoes.CATALOGO)


def test_filho_exige_pai_e_revogar_pai_revoga_filhos():
    permissoes.conceder("arquivos.ler")                      # conceder o filho libera o pai junto (precisa dele para valer)
    assert permissoes.permitido("arquivos.ler") and permissoes.permitido("arquivos")
    assert not permissoes.permitido("arquivos.apagar")        # granular: o irmao nao veio de brinde
    permissoes.revogar("arquivos")
    assert not permissoes.permitido("arquivos.ler")           # cascata


def test_exigir_levanta_e_registro_guarda_historia():
    with pytest.raises(permissoes.PermissaoNegada):
        permissoes.exigir("email.enviar")
    permissoes.conceder("email", com_filhos=True)
    permissoes.exigir("email.enviar")
    permissoes.revogar_tudo()
    assert not permissoes.permitido("email.enviar")
    assert any(l[1] == "revogou" and l[2] == "TUDO" for l in permissoes._ler()["registro"])


def test_modo_nenhum_e_valido_e_fica_registrado():
    permissoes.aplicar_modo("nenhum")
    assert perfil.carregar()["consentimento_acesso_pc"] == "nenhum" and not permissoes.liberadas()


def test_modo_total_libera_tudo():
    permissoes.aplicar_modo("total")
    assert permissoes.permitido("whatsapp.enviar") and perfil.carregar()["consentimento_acesso_pc"] == "total"


# ---------- chaves ----------

def test_chave_curta_ou_recusada_nao_entra(monkeypatch):
    guardadas = []
    monkeypatch.setattr(cofre, "guardar", lambda p, k: guardadas.append(p))
    assert provedores.cadastrar("google", "curta")[0] is False

    def recusa(url, h):
        raise urllib.error.HTTPError(url, 401, "x", {}, None)
    assert provedores.cadastrar("google", "x" * 40, http=recusa) == (False, "chave recusada pelo serviço")
    assert not guardadas
    assert provedores.cadastrar("google", "x" * 40, http=lambda u, h: 200) == (True, "ok") and guardadas == ["google"]


def test_catalogo_explica_o_que_cada_chave_melhora():
    assert all(c["melhora"] and c["onde"].startswith("https://") for c in provedores.catalogo())
    assert provedores.ORDEM[0] == "google" and provedores.ORDEM[1] == "openrouter"


@pytest.mark.skipif(sys.platform != "win32", reason="cofre = Gerenciador de Credenciais do Windows")
def test_cofre_guarda_le_e_remove():
    nome = "teste-braniac-seed"
    try:
        cofre.guardar(nome, "chave-secreta-de-teste-123456")
        assert cofre.ler(nome) == "chave-secreta-de-teste-123456"
    finally:
        cofre.remover(nome)
    assert cofre.ler(nome) is None


# ---------- hardware ----------

def test_perfis_de_hardware():
    assert hardware.recomendar({"ram_gb": 4, "gpu": None, "disco_livre_gb": 100})[0] == "leve"
    assert hardware.recomendar({"ram_gb": 16, "gpu": None, "disco_livre_gb": 100})[0] == "equilibrado"
    assert hardware.recomendar({"ram_gb": 32, "gpu": {"nome": "RTX", "vram_gb": 12}, "disco_livre_gb": 100})[0] == "potente"
    assert hardware.recomendar({"ram_gb": 32, "gpu": {"nome": "RTX", "vram_gb": 12}, "disco_livre_gb": 3})[0] == "leve"


# ---------- nome e voz ----------

def test_nome_obrigatorio_e_validado():
    assert not nomes.validar_nome("")[0] and not nomes.validar_nome("Alexa")[0] and not nomes.validar_nome("A1b")[0]
    assert nomes.validar_nome("Aurora")[0]


def test_sugestoes_seguem_os_gostos_e_a_voz():
    s = nomes.sugerir("eu gosto de música e de jogar videogame", "feminina")
    assert "Melodia" in s and "Zelda" in s
    assert "Link" in nomes.sugerir("jogo muito", "masculina")
    assert len(nomes.sugerir("", "masculina")) == 6          # sem pistas: mistura
    with pytest.raises(ValueError):
        nomes.sugerir("x", "outra")


def test_frase_de_acordar():
    assert nomes.frase_de_acordar("Aurora") == "Aurora, tá acordado?"


# ---------- onboarding ----------

def test_nao_conclui_sem_nome_voz_chave_e_consentimento():
    assert len(onboarding.faltando(chaves=[])) == 3
    with pytest.raises(onboarding.Pendencia):
        onboarding.concluir(chaves=[])


def test_fluxo_completo_com_recusa_de_acesso_ao_pc():
    onboarding.consentimento("nenhum")                        # recusar o acesso ao PC nao impede de usar
    onboarding.definir_nome_voz("Aurora", "feminina")
    onboarding.definir_integracoes(["spotify"])
    onboarding.definir_icone("flutuante")
    onboarding.concluir(chaves=["google"])
    p = perfil.carregar()
    assert p["concluido"] and p["nome_assistente"] == "Aurora" and p["voz"] == "feminina" and p["modo_icone"] == "flutuante"
    assert not permissoes.liberadas()


def test_voz_precisa_ser_escolhida():
    with pytest.raises(onboarding.Pendencia):
        onboarding.definir_nome_voz("Aurora", "tanto faz")


def test_progresso_continua_de_onde_parou():
    assert onboarding.etapa_atual() == "boas_vindas"
    onboarding.proxima()
    assert onboarding.etapa_atual() == "consentimento"


# ---------- atualizador ----------

def _pacote(conteudo=b"print('nova funcao')"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("funcoes/nova.py", conteudo)
    return buf.getvalue()


def _manifesto(v, dados):
    return {"versao": v, "pacotes": [{"nome": f"f-{v}.zip", "url": "https://github.com/carloslavig/x.zip", "sha256": hashlib.sha256(dados).hexdigest()}]}


def test_atualiza_confere_hash_e_faz_rollback():
    d1, d2 = _pacote(b"v1"), _pacote(b"v2")
    atualizador.instalar(_manifesto("1.0.0", d1), baixar=lambda u: d1)
    assert atualizador.versao_atual() == "1.0.0"
    assert atualizador.ha_atualizacao(_manifesto("1.1.0", d2)) and not atualizador.ha_atualizacao(_manifesto("1.0.0", d1))
    atualizador.instalar(_manifesto("1.1.0", d2), baixar=lambda u: d2)
    assert atualizador.versao_atual() == "1.1.0"
    assert atualizador.reverter() == "1.0.0" and atualizador.versao_atual() == "1.0.0"


def test_pacote_adulterado_nao_instala():
    bom = _pacote(b"ok")
    with pytest.raises(atualizador.UpdateErro):
        atualizador.instalar(_manifesto("2.0.0", bom), baixar=lambda u: _pacote(b"malicioso"))
    assert atualizador.versao_atual() is None


def test_zip_com_caminho_fora_da_pasta_e_barrado():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("../fora.py", b"x")
    dados = buf.getvalue()
    with pytest.raises(atualizador.UpdateErro):
        atualizador.instalar(_manifesto("3.0.0", dados), baixar=lambda u: dados)


def test_so_baixa_do_repositorio_do_dono():
    with pytest.raises(atualizador.UpdateErro):
        atualizador._baixar("https://site-qualquer.com/pacote.zip")
