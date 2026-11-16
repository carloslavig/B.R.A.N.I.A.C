# -*- coding: utf-8 -*-
from datetime import datetime
import shutil

from braniac import empresa_cortes as C

SEGS = [{"ini": float(i * 5), "fim": float(i * 5 + 5), "texto": f"frase numero {i} com varias palavras aqui"} for i in range(12)]


def _isolar(tmp_path, monkeypatch):
    shutil.copy(C.EQUIPE_JSON, tmp_path / "equipe.json")
    c = C._ler(tmp_path / "equipe.json", {})
    c.update(direitos_ok=False, gameplay_ok=False, gameplay_padrao="", busca_automatica=False, youtube_ritmo=None)
    C._gravar(tmp_path / "equipe.json", c)
    monkeypatch.setattr(C, "PASTA", tmp_path)
    monkeypatch.setattr(C, "SAIDA", tmp_path / "saida")
    monkeypatch.setattr(C, "EQUIPE_JSON", tmp_path / "equipe.json")
    monkeypatch.setattr(C, "PEDIDOS_JSON", tmp_path / "pedidos.json")
    monkeypatch.setattr(C, "FILA_JSON", tmp_path / "fila.json")
    monkeypatch.setattr(C, "_segmentos", lambda v: SEGS)
    monkeypatch.setattr(C, "_ia", lambda s, p: '{"ini": 10, "fim": 40}')
    monkeypatch.setattr(C, "_montar_fn", lambda f, g, ini, dur, d: d.write_bytes(b"x"))
    monkeypatch.setattr(C, "_queimar_fn", lambda b, s, d: d.write_bytes(b"x"))
    monkeypatch.setattr(C, "_sonda", lambda a: {"duracao": 30, "largura": 1080, "altura": 1920, "audio": True, "volume_db": -20})
    f = tmp_path / "fala.mp4"
    g = tmp_path / "game.mp4"
    f.write_bytes(b"x")
    g.write_bytes(b"x")
    return str(f), str(g)


def _ate_ok(fala, game):
    p, _ = C.abrir(fala, "Streamer Manoel", "Podcast X", game)
    for _ in range(8):
        C.trabalhar(1, ignorar_teto=True)
    return p["id"]


def test_abrir_recusa_sem_autor_gameplay_e_segredo(tmp_path, monkeypatch):
    fala, game = _isolar(tmp_path, monkeypatch)
    assert C.abrir(fala, "", gameplay=game)[0] is None
    assert C.abrir(fala, "Fulano", gameplay="")[0] is None
    assert C.abrir(fala, "Fulano senha 123", gameplay=game)[0] is None


def test_fluxo_completo_cita_fonte_e_para_no_ok(tmp_path, monkeypatch):
    fala, game = _isolar(tmp_path, monkeypatch)
    id_ = _ate_ok(fala, game)
    p = C._pedidos()[0]
    assert p["estado"] == "aguardando_ok" and p["trecho"]["ini"] == 10
    assert "Fonte: Streamer Manoel - Podcast X" in (tmp_path / "saida" / id_ / "leg.srt").read_text(encoding="utf-8")


def test_aprovar_travado_ate_liberar_direitos(tmp_path, monkeypatch):
    fala, game = _isolar(tmp_path, monkeypatch)
    id_ = _ate_ok(fala, game)
    assert "Ainda não" in C.aprovar(id_)
    assert C._pedidos()[0]["estado"] == "aguardando_ok"
    c = C.config()
    c.update(direitos_ok=True, gameplay_ok=True)
    C._gravar(C.EQUIPE_JSON, c)
    assert "confirme antes" in C.aprovar(id_)
    C.confirmar_locutor(id_)
    assert "TikTok em" in C.aprovar(id_)
    assert C._pedidos()[0]["estado"] == "aprovado" and (tmp_path / "saida" / "kwai" / f"{id_}.mp4").exists()
    assert C.aprovar(id_).startswith("Pedido não")


def test_lupa_reprova_formato_errado(tmp_path, monkeypatch):
    fala, game = _isolar(tmp_path, monkeypatch)
    monkeypatch.setattr(C, "_sonda", lambda a: {"duracao": 30, "largura": 1920, "altura": 1080, "audio": True, "volume_db": -20})
    _ate_ok(fala, game)
    assert C._pedidos()[0]["estado"] == "reprovado"


def test_escolha_sem_ia_usa_janela_densa(tmp_path, monkeypatch):
    _isolar(tmp_path, monkeypatch)
    monkeypatch.setattr(C, "_ia", lambda s, p: "nada")
    ini, fim = C._escolher(SEGS)
    assert 20 <= fim - ini <= 45


def test_teto_de_passos(tmp_path, monkeypatch):
    fala, game = _isolar(tmp_path, monkeypatch)
    c = C.config()
    c["limites"]["passos_dia"] = 1
    C._gravar(C.EQUIPE_JSON, c)
    C.abrir(fala, "A", gameplay=game)
    assert len(C.trabalhar(1)) == 1
    assert "Teto" in C.trabalhar(1)[0]


def test_equipe_sem_nome_repetido():
    from braniac import empresa_dev, empresa_inv, empresa_mkt
    outros = set(empresa_dev.nomes()) | set(empresa_inv.nomes()) | set(empresa_mkt.nomes())
    assert not outros & set(C.nomes()) and len(set(C.nomes())) == len(C.nomes())


def test_vigia_antigo_pausado(tmp_path, monkeypatch):
    from braniac.cortes import vigia
    (tmp_path / "PAUSA_ANDAR").write_text("")
    monkeypatch.setattr(vigia, "PAUSA", tmp_path / "PAUSA_ANDAR")
    assert "pausada" in vigia.ligar_em_segundo_plano()


def test_busca_filtra_hostis_curtos_e_usados(tmp_path, monkeypatch):
    fala, game = _isolar(tmp_path, monkeypatch)
    monkeypatch.setattr(C, "_buscar_fn", lambda q: [
        "a1|Streamer Manoel no Podcast X|3000|Streamer Manoel", "a2|RESPOSTA ao Streamer Manoel|3000|Canal", "a3|Streamer Manoel trecho|60|Canal",
        "a4|Outro assunto qualquer|3000|Canal", "a5|Streamer Manoel live longa|90000|Canal"])
    assert [a[0][-2:] for a in C.buscar_fontes()] == ["a1"]
    monkeypatch.setattr(C, "abrir", lambda *a, **k: ({"titulo_fonte": a[2]}, "ok"))
    C.abrir_da_busca()
    assert C.buscar_fontes() == []


def test_publicar_vencidos_so_no_horario_e_uma_vez(tmp_path, monkeypatch):
    _isolar(tmp_path, monkeypatch)
    C._gravar(C.FILA_JSON, [{"id": "V001", "plataforma": "tiktok", "quando": "2026-11-04 09:00", "arquivo": "x.mp4", "estado": "agendado"}])
    subidos = []
    ok = lambda arq, leg: subidos.append(leg) or ""
    assert C.publicar_vencidos(datetime(2026, 11, 4, 8, 59), None, ok) is None and not subidos
    assert "publicado" in C.publicar_vencidos(datetime(2026, 11, 4, 9, 0), None, ok)
    assert C.publicar_vencidos(datetime(2026, 11, 4, 9, 5), None, ok) is None and len(subidos) == 1
    assert C._ler(C.FILA_JSON, [])[0]["estado"] == "publicado"


def test_publicar_erro_fica_registrado(tmp_path, monkeypatch):
    _isolar(tmp_path, monkeypatch)
    C._gravar(C.FILA_JSON, [{"id": "V001", "plataforma": "tiktok", "quando": "2026-11-04 09:00", "arquivo": "x.mp4", "estado": "agendado"}])
    assert "NÃO subiu" in C.publicar_vencidos(datetime(2026, 11, 4, 9, 1), None, lambda a, l: "sessão caiu")
    assert C._ler(C.FILA_JSON, [])[0]["estado"].startswith("erro")


def test_busca_so_aceita_canal_do_streamer_ou_aprovado_e_barra_titulo_de_briga(monkeypatch):
    linhas = ["aaa|Streamer Manoel fala sobre o Brasil|3600|Streamer Manoel",
              "bbb|STREAMER MANOEL PERDEU A PACIÊNCIA COM JEAN WYLLYS|2400|MamãeFalei",
              "ccc|Streamer Manoel no podcast X|3000|Podcast X",
              "ddd|Streamer Manoel debate vs fulano|3000|Streamer Manoel"]
    monkeypatch.setattr(C, "_buscar_fn", lambda q: linhas)
    monkeypatch.setattr(C, "_pedidos", lambda: [])
    monkeypatch.setattr(C, "config", lambda: {"busca": {"min_s": 600, "max_s": 14400}})
    urls = [a[0] for a in C.buscar_fontes(10)]
    assert urls == ["https://www.youtube.com/watch?v=aaa"]
    monkeypatch.setattr(C, "config", lambda: {"busca": {"min_s": 600, "max_s": 14400, "canais_ok": ["Podcast X"]}})
    assert [a[0][-3:] for a in C.buscar_fontes(10)] == ["aaa", "ccc"]
