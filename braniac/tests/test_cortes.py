# -*- coding: utf-8 -*-
"""Cortes de lives: deteccao, legenda e fila (sem rede, sem GPU, sem ffmpeg)."""
import json
import numpy as np
import pytest
from braniac.cortes import comandos, config, deteccao, fila, legenda, pipeline


@pytest.fixture(autouse=True)
def _pasta_isolada(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PASTA", tmp_path / "cortes")
    monkeypatch.setattr(config, "ARQ", tmp_path / "cortes" / "cortes.json")
    monkeypatch.setattr(pipeline, "_telegram", lambda *a, **k: None)


def _audio(total=600, picos=()):
    rng = np.random.default_rng(1)
    db = -40 + rng.normal(0, 1.5, total).astype(np.float32)
    for p in picos:
        db[p:p + 5] = -12
    return db


def test_acha_os_picos_de_audio_sem_sobreposicao():
    score, _, _ = deteccao.pontuar(_audio(picos=(200, 210, 450)))
    js = deteccao.escolher_janelas(score, quantos=5, minimo=2.0)
    assert len(js) == 2  # 200 e 210 viram um corte so
    assert js[0][0] <= 200 <= js[0][1] and js[1][0] <= 450 <= js[1][1]
    assert all(25 <= f - i <= 58 for i, f, *_ in js)


def test_fim_do_arquivo_e_ruido_constante_nao_viram_pico():
    db = np.full(300, -46.3, dtype=np.float32)
    db[-5:] += 0.3  # variacao minima no fim
    score, _, _ = deteccao.pontuar(db)
    assert deteccao.escolher_janelas(score, minimo=2.0) == []


def test_inicio_da_live_e_ignorado():
    score, _, _ = deteccao.pontuar(_audio(picos=(10,)))
    assert deteccao.escolher_janelas(score, minimo=2.0) == []


def test_chat_com_hype_reforca_e_e_adiantado(tmp_path):
    arq = tmp_path / "chat.jsonl"
    linhas = [{"t": t, "msg": "oi"} for t in range(0, 600, 4)] + [{"t": 306 + i * 0.1, "msg": "KEKW kkkkk"} for i in range(60)]
    arq.write_text("\n".join(json.dumps(l) for l in linhas), encoding="utf-8")
    chat, hype = deteccao.chat_por_segundo(arq, 600, atraso_s=6)
    assert chat[300:306].sum() > 100 and sum(hype.values()) == 60
    score, _, zc = deteccao.pontuar(_audio(), chat)
    js = deteccao.escolher_janelas(score, minimo=2.0)
    assert js and js[0][0] <= 300 <= js[0][1]


def test_chat_quase_vazio_e_ignorado(tmp_path):
    arq = tmp_path / "chat.jsonl"
    arq.write_text(json.dumps({"t": 5, "msg": "oi"}), encoding="utf-8")
    assert deteccao.chat_por_segundo(arq, 100)[0] is None


def test_legenda_agrupa_e_destaca_a_palavra():
    pal = [(0.0, 0.3, "eu"), (0.3, 0.6, "nao"), (0.6, 0.9, "acredito"), (2.0, 2.4, "caraca")]
    gs = legenda.agrupar(pal)
    assert [len(g) for g in gs] == [2, 1, 1] or [len(g) for g in gs] == [3, 1]
    assert all(g[0][2] != "caraca" or len(g) == 1 for g in gs)  # pausa longa abre grupo novo


def test_gerar_ass(tmp_path):
    p = legenda.gerar_ass([(0.0, 0.5, "{oi}"), (0.5, 1.0, "gente")], tmp_path / "l.ass")
    t = p.read_text(encoding="utf-8")
    assert "PlayResY: 1920" in t and t.count("Dialogue:") == 2 and "{oi}" not in t and "(OI)" in t


def test_fila_aprovar_rejeitar_e_comandos():
    a = fila.adicionar(canal="c", origem="live", fonte="x", inicio=0, fim=30, arquivo="a.mp4", titulo="A", motivo="m")
    b = fila.adicionar(canal="c", origem="live", fonte="x", inicio=60, fim=90, arquivo="b.mp4", titulo="B", motivo="m")
    assert "#%d" % a in comandos.aprovar(str(a))
    assert fila.pegar(a)["status"] == "aprovado"
    assert "#%d" % b in comandos.rejeitar(f"corte {b}")
    assert comandos.aprovar("todos") .startswith("nenhum")  # nada mais esperando
    assert fila.resumo() == {"aprovado": 1, "rejeitado": 1}
    fila.marcar_visto("clipe:1")
    assert fila.ja_visto("clipe:1") and not fila.ja_visto("clipe:2")


def test_publicar_sem_youtube_prepara_tiktok_e_nao_repete_aviso(tmp_path, monkeypatch):
    v = tmp_path / "v.mp4"
    v.write_bytes(b"0" * 100)
    a = fila.adicionar(canal="c", origem="live", fonte="x", inicio=0, fim=30, arquivo=str(v), titulo="T", hashtags="#shorts #x",
                       status="aprovado")
    rel = pipeline.publicar_aprovados()
    assert any("TikTok" in r for r in rel) and (config.PASTA / "tiktok" / f"corte_{a:04d}.mp4").exists()
    assert pipeline.publicar_aprovados() == []  # segundo ciclo: nada novo, nenhum aviso repetido


def test_canal_sem_autorizacao_nao_e_vigiado(monkeypatch):
    from braniac.cortes import twitch, vigia
    chamados = []
    monkeypatch.setattr(twitch, "ao_vivo", lambda login: chamados.append(login))
    config.carregar()
    vigia.Vigia().ciclo()
    assert chamados == []


def test_perfil_gringo_ingles_e_separado(tmp_path):
    from braniac.cortes import titulos, youtube
    cfg = config.para_canal({"login": "fulano", "nome": "Fulano", "perfil": "gringo"})
    assert cfg["idioma"] == "en" and cfg["clipes_janela_h"] == 168 and cfg["perfil"] == "gringo"
    assert config.para_canal({"login": "x"})["idioma"] == "pt"  # canal sem perfil continua PT
    t = titulos.gerar("fulano", "", usar_ia=False, titulo_base="crazy clutch in ranked", idioma="en", nome="Fulano")
    assert t["titulo"] == "crazy clutch in ranked | Fulano" and "#twitchclips" in t["hashtags"]
    d = pipeline.descricao(cfg, "fulano", "Fulano", "T", ["#shorts"], "https://clips.twitch.tv/abc")
    assert "twitch.tv/fulano" in d and "Original clip: https://clips.twitch.tv/abc" in d and "credit" in d
    assert youtube._arqs("gringo")[1].name == "youtube_token_gringo.json" and youtube._arqs()[1].name == "youtube_token.json"


def test_publicar_gringo_vai_para_pasta_propria_e_pede_login_proprio(tmp_path):
    v = tmp_path / "v.mp4"
    v.write_bytes(b"0" * 100)
    a = fila.adicionar(canal="f", origem="clipe", fonte="x", inicio=0, fim=30, arquivo=str(v), titulo="T", hashtags="#shorts",
                       status="aprovado", perfil="gringo")
    rel = pipeline.publicar_aprovados()
    assert (config.PASTA / "tiktok" / "gringo" / f"corte_{a:04d}.mp4").exists()
    assert any("--perfil gringo" in r for r in rel)
    assert fila.publicados_hoje("gringo") == 0


def test_grade_de_horarios():
    import time
    from braniac.cortes import pipeline
    cfg = {"youtube_horarios": ["19:00", "12:00"], "youtube_agendar_dias": 1}
    agora = time.mktime((2026, 10, 10, 15, 20, 0, 0, 0, -1))
    hora = lambda t: time.strftime("%d %H:%M", time.localtime(t))
    oc = set()
    vistos = []
    while (t := pipeline.proximo_horario(cfg, oc, agora)) is not None:
        vistos.append(hora(t))
        oc.add(t)
    # horario de hoje que ja passou ainda conta (sobe na hora); amanha so os futuros; depois disso a agenda fecha
    assert vistos == ["10 12:00", "10 19:00", "11 12:00", "11 19:00"]
