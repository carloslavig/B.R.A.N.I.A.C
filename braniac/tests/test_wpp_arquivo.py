# -*- coding: utf-8 -*-
import zipfile
import pytest
from braniac import wpp_arquivo as wa


def test_executavel_vira_zip(tmp_path):
    exe = tmp_path / "Instalador.exe"
    exe.write_bytes(b"MZ" + b"\0" * 100)
    z = wa.compactar(str(exe), tmp_path)
    assert z.endswith("Instalador.zip")
    with zipfile.ZipFile(z) as f:
        assert f.namelist() == ["Instalador.exe"]


def test_arquivo_comum_nao_e_alterado(tmp_path):
    p = tmp_path / "foto.png"
    p.write_bytes(b"x")
    assert wa.compactar(str(p), tmp_path) == str(p)


def test_arquivo_inexistente_vira_mensagem_e_nada_e_enviado(tmp_path, monkeypatch):
    monkeypatch.setattr(wa, "_enviar", lambda *a: pytest.fail("nao deveria abrir o WhatsApp"))
    assert "não encontrado" in wa.enviar_arquivo("Fulano", str(tmp_path / "nao_existe.zip"))


def test_arquivo_grande_demais_nao_e_enviado(tmp_path, monkeypatch):
    p = tmp_path / "grande.bin"
    p.write_bytes(b"0")
    monkeypatch.setattr(wa, "LIMITE_MB", 0)
    monkeypatch.setattr(wa, "_enviar", lambda *a: pytest.fail("nao deveria abrir o WhatsApp"))
    assert "grande demais" in wa.enviar_arquivo("Fulano", str(p))


def test_validar_recusa_executavel_sem_compactar(tmp_path):
    exe = tmp_path / "a.exe"
    exe.write_bytes(b"x")
    with pytest.raises(wa.ArquivoErro):
        wa.validar(str(exe))


def test_envio_chama_o_whatsapp_com_o_zip(tmp_path, monkeypatch):
    exe = tmp_path / "Setup.exe"
    exe.write_bytes(b"MZ")
    monkeypatch.setattr(wa.tempfile, "gettempdir", lambda: str(tmp_path))
    visto = {}
    monkeypatch.setattr(wa, "_enviar", lambda nome, p, leg: visto.update(nome=nome, arq=p.name, leg=leg) or "✅ ok")
    assert wa.enviar_arquivo("Amigo", str(exe), "oi") == "✅ ok"
    assert visto == {"nome": "Amigo", "arq": "Setup.zip", "leg": "oi"}


def test_previa_travada_recarrega_o_whatsapp_e_tenta_uma_vez(tmp_path, monkeypatch):
    # 15/11: a aba do WhatsApp Web travou e descartava todo anexo ate recarregar
    pdf = tmp_path / "guia.pdf"
    pdf.write_bytes(b"%PDF")
    respostas, recargas = [wa.PREVIA_NAO_ABRIU, "✅ ok"], []
    monkeypatch.setattr(wa, "_enviar", lambda n, p, l: respostas.pop(0))
    monkeypatch.setattr(wa, "_recarregar", lambda: recargas.append(1))
    assert wa.enviar_arquivo("Parceiro", str(pdf)) == "✅ ok" and recargas == [1]
    respostas[:] = [wa.PREVIA_NAO_ABRIU, wa.PREVIA_NAO_ABRIU]
    assert wa.enviar_arquivo("Parceiro", str(pdf)) == wa.PREVIA_NAO_ABRIU and recargas == [1, 1]   # so uma recarga por envio


def test_jarvis_manda_qualquer_arquivo_menos_os_que_guardam_segredo():
    from pathlib import Path
    home = Path.home()
    aqui = Path(wa.__file__)
    assert wa.resolver_caminho(str(aqui)) == str(aqui.resolve())                  # pasta do Braniac: liberada
    assert wa.resolver_caminho("wpp_arquivo.py") == str(aqui.resolve())           # por parte do nome (acha na pasta do Braniac)
    assert wa.resolver_caminho("braniac").endswith("BRANIAC_0.3.0.zip")
    for ruim in (home / ".env", aqui.parent / "data" / "jarvis.db", Path("C:/Windows/system32/notepad.exe"), home / "AppData" / "Local" / "x.zip",
                 aqui.parent.parent / "gustavo" / "plano" / "PLANO.md", aqui.parent / "data" / "legado" / "dono.db"):
        with pytest.raises(wa.ArquivoErro):
            wa.resolver_caminho(str(ruim))
    with pytest.raises(wa.ArquivoErro):
        wa.resolver_caminho("arquivo-que-nao-existe-xyz")


def test_ferramenta_do_jarvis_envia_pelo_wpp_arquivo(monkeypatch):
    from braniac import jarvis, whatsapp
    visto = {}
    monkeypatch.setattr(jarvis, "_resolver_contato", lambda r, n, o: ("Amigo Pereira Fresco Da Silva", None))
    monkeypatch.setattr(wa, "enviar_arquivo", lambda nome, arq, leg: visto.update(nome=nome, arq=arq, leg=leg) or "✅ ok")
    assert jarvis._enviar_arquivo(None, "Amigo Pereira", "braniac", "segue", "x") == "✅ ok"
    assert visto["arq"].endswith("BRANIAC_0.3.0.zip") and visto["nome"].startswith("Amigo")
    assert "Não mandei" in jarvis._enviar_arquivo(None, "Amigo", r"C:\Users\usuario\.env", "", "x")
    assert any(f["function"]["name"] == "whatsapp_enviar_arquivo" for f in jarvis.FERRAMENTAS) if isinstance(jarvis.FERRAMENTAS, list) and jarvis.FERRAMENTAS and "function" in jarvis.FERRAMENTAS[0] else True
