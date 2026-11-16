from pathlib import Path

from braniac import video_analise


def test_main_sem_videos(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["x", str(tmp_path)])
    video_analise.main()
    assert "nenhum .mp4" in capsys.readouterr().out


def test_saida_dentro_de_data():
    assert video_analise.SAIDA == Path(video_analise.__file__).resolve().parent / "data" / "analises_video"
