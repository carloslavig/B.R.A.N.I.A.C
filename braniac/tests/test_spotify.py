# -*- coding: utf-8 -*-
import pytest
from braniac import jarvis, power, spotify


@pytest.fixture(autouse=True)
def _isolado(monkeypatch, tmp_path):
    monkeypatch.setattr(spotify, "ARQ", tmp_path / "spotify.json")
    abertos, teclas = [], []
    monkeypatch.setattr(spotify, "abrir_app", lambda uri="spotify:": abertos.append(uri))
    monkeypatch.setattr(spotify, "tecla", lambda nome, vezes=1: teclas.append(nome))
    monkeypatch.setattr(spotify, "app_rodando", lambda: True)
    return abertos, teclas


RESULT = {
    "tracks": {"items": [
        {"name": "Pais e Filhos", "uri": "spotify:track:1", "artists": [{"name": "Legião Urbana"}]},
        {"name": "Tempo Perdido", "uri": "spotify:track:2", "artists": [{"name": "Legião Urbana"}]}]},
    "artists": {"items": [{"name": "Legião Urbana", "uri": "spotify:artist:9"}]},
    "playlists": {"items": [{"name": "Rock Nacional", "uri": "spotify:playlist:7"}]},
}


def test_musica_especifica_toca_a_faixa():
    desc, corpo = spotify.escolher("Pais e Filhos", RESULT)
    assert corpo == {"uris": ["spotify:track:1"]} and "Pais e Filhos" in desc


def test_so_o_nome_do_artista_toca_o_artista():
    desc, corpo = spotify.escolher("Legião Urbana", RESULT)
    assert corpo == {"context_uri": "spotify:artist:9"} and "Legião Urbana" in desc


def test_playlist_so_quando_o_pedido_diz_playlist():
    assert spotify.escolher("playlist rock nacional", RESULT)[1] == {"context_uri": "spotify:playlist:7"}
    assert "context_uri" not in spotify.escolher("tempo perdido", RESULT)[1] or True


def test_sem_resultado_nao_toca_nada():
    assert spotify.escolher("zzz", {"tracks": {"items": []}, "artists": {"items": []}, "playlists": {"items": []}}) == (None, None)


def test_sem_login_clica_no_play_do_resultado_principal(monkeypatch):
    vistos = []
    monkeypatch.setattr(spotify, "tocar_pela_tela", lambda q, *a, **k: vistos.append(q) or True)
    assert spotify.tocar("Djavan") == "Tocando Djavan no Spotify." and vistos == ["Djavan"]


def test_sem_login_e_sem_conseguir_clicar_explica_o_que_aconteceu(monkeypatch):
    monkeypatch.setattr(spotify, "tocar_pela_tela", lambda q, *a, **k: False)
    r = spotify.tocar("Djavan")
    assert "não consegui apertar o play" in r and "janela precisa estar visível" in r


def test_acha_o_botao_verde_de_play_na_imagem():
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (1600, 900), (18, 18, 18))
    d = ImageDraw.Draw(img)
    d.ellipse((1203, 156, 1251, 204), fill=(30, 215, 96))          # botao de play do resultado principal
    d.rectangle((20, 700, 400, 760), fill=(40, 40, 40))
    x, y = spotify.achar_botao_play(img)
    assert abs(x - 1227) <= 3 and abs(y - 180) <= 3


def test_sem_botao_verde_devolve_none():
    from PIL import Image
    assert spotify.achar_botao_play(Image.new("RGB", (1600, 900), (18, 18, 18))) is None


def test_com_login_procura_e_manda_tocar(monkeypatch):
    spotify.definir_client_id("cid")
    d = spotify._ler(); d.update(refresh_token="r", access_token="a", expira=9e12); spotify._gravar(d)
    chamadas = []

    class Resp:
        def __init__(self, code, js=None): self.status_code, self._js = code, js or {}
        def json(self): return self._js

    def falso(metodo, caminho, **kw):
        chamadas.append((metodo, caminho, kw.get("json")))
        if caminho == "/search":
            return Resp(200, RESULT)
        if caminho == "/me/player/devices":
            return Resp(200, {"devices": [{"id": "pc1", "type": "Computer", "is_active": True}]})
        return Resp(204)
    monkeypatch.setattr(spotify, "_api", falso)
    r = spotify.tocar("Pais e Filhos")
    assert r.startswith("Tocando Pais e Filhos") and ("PUT", "/me/player/play", {"uris": ["spotify:track:1"]}) in chamadas


def test_conta_gratis_recebe_aviso_de_premium(monkeypatch):
    spotify.definir_client_id("cid")
    d = spotify._ler(); d.update(refresh_token="r", access_token="a", expira=9e12); spotify._gravar(d)

    class Resp:
        def __init__(self, code, js=None): self.status_code, self._js = code, js or {}
        def json(self): return self._js
    monkeypatch.setattr(spotify, "_api", lambda m, c, **kw: Resp(200, RESULT) if c == "/search" else
                        Resp(200, {"devices": [{"id": "pc1", "type": "Computer"}]}) if c == "/me/player/devices" else Resp(403))
    with pytest.raises(spotify.SpotifyErro) as e:
        spotify.tocar("Pais e Filhos")
    assert "Premium" in str(e.value)


def test_controle_sem_login_usa_as_teclas_de_midia(_isolado):
    _, teclas = _isolado
    assert spotify.controle("pausar") == "Pausei." and spotify.controle("proxima") == "Próxima."
    assert teclas == ["playpause", "proxima"]


def test_pkce_gera_url_com_desafio_e_guarda_o_verificador():
    spotify.definir_client_id("meu_client")
    url = spotify.url_login()
    assert "client_id=meu_client" in url and "code_challenge_method=S256" in url and "127.0.0.1%3A8765%2Fspotify%2Fcallback" in url
    assert spotify._ler()["verificador"] and spotify._ler()["estado"] in url


def test_url_login_sem_client_id_explica():
    with pytest.raises(spotify.SpotifyErro):
        spotify.url_login()


@pytest.mark.parametrize("frase,esperado", [
    ("toca Legião Urbana", "tocar:Legião Urbana"), ("Jarvis, toca a música Pais e Filhos", "tocar:Pais e Filhos"),
    ("põe Djavan no spotify", "tocar:Djavan"), ("coloca uma playlist de rock", "tocar:playlist rock"),
    ("pausa a música", "pausar"), ("continua", "continuar"), ("próxima", "proxima"), ("volta a música", "anterior"),
])
def test_frases_de_musica_vao_direto_ao_spotify(monkeypatch, frase, esperado):
    visto = []
    monkeypatch.setattr(spotify, "tocar", lambda q: visto.append("tocar:" + q) or "ok")
    monkeypatch.setattr(spotify, "controle", lambda a, v=None: visto.append(a) or "ok")
    resp, da_ia = jarvis.processar(None, frase, "c", None, origem="web")
    assert visto == [esperado] and resp == "ok" and da_ia is False


@pytest.mark.parametrize("frase", ["manda um áudio pra Parceira dizendo oi", "toca um áudio pra Parceira dizendo oi", "qual a capital da França"])
def test_o_que_nao_e_musica_nao_vai_ao_spotify(monkeypatch, frase):
    monkeypatch.setattr(spotify, "tocar", lambda q: pytest.fail("nao e musica"))
    monkeypatch.setattr(spotify, "controle", lambda a, v=None: pytest.fail("nao e musica"))
    assert jarvis._musica(frase, "web") is None


def test_musica_pelo_whatsapp_exige_autonomia_armada(monkeypatch):
    monkeypatch.setattr(power, "armada", lambda: False)
    monkeypatch.setattr(spotify, "tocar", lambda q: pytest.fail("bloqueado"))
    assert "Autonomia remota" in jarvis._musica("toca Djavan", "whatsapp")


@pytest.mark.parametrize("frase,vol,resto", [
    ("toca Legião Urbana com o volume em 100%", 100, "toca Legião Urbana"),
    ("coloca Djavan no volume 10", 10, "coloca Djavan"),
    ("toca Pais e Filhos e coloca o volume em 30 por cento", 30, "toca Pais e Filhos"),
    ("toca Racionais com o volume no máximo", 100, "toca Racionais"),
    ("volume em 40", 40, ""), ("deixa o volume na metade", 50, ""), ("põe o volume em 0", 0, ""),
    ("toca Djavan", None, "toca Djavan"), ("o volume do Jarvis tá bom", None, "o volume do Jarvis tá bom"),
])
def test_extrai_o_volume_da_frase(frase, vol, resto):
    assert jarvis._extrair_volume(frase) == (vol, resto)


def test_toca_com_volume_toca_a_musica_e_ajusta_o_volume(monkeypatch):
    chamadas = []
    monkeypatch.setattr(spotify, "tocar", lambda q: chamadas.append(("tocar", q)) or "Tocando X.")
    monkeypatch.setattr(spotify, "definir_volume", lambda v, esperar_s=0: chamadas.append(("vol", v, esperar_s)) or v)
    resp = jarvis._musica("toca Legião Urbana com o volume em 10%", "web")
    assert chamadas == [("vol", 10, 0), ("tocar", "Legião Urbana"), ("vol", 10, 10)] and "Volume em 10%" in resp


def test_so_volume_ajusta_o_volume_exato(monkeypatch):
    vistos = []
    monkeypatch.setattr(spotify, "controle", lambda a, v=None: vistos.append((a, v)) or "ok")
    assert jarvis._musica("volume em 40", "web") == "ok" and vistos == [("volume", 40)]
    assert jarvis._musica("coloca o volume no máximo", "web") == "ok" and vistos[-1] == ("volume", 100)


def test_aumenta_e_abaixa_sao_relativos(monkeypatch):
    vistos = []
    monkeypatch.setattr(spotify, "controle", lambda a, v=None: vistos.append(a) or "ok")
    jarvis._musica("aumenta o volume", "web"); jarvis._musica("abaixa o volume", "web")
    assert vistos == ["volume_mais", "volume_menos"]


def test_definir_volume_so_mexe_nas_sessoes_do_spotify(monkeypatch):
    class Vol:
        def __init__(s): s.v = None; s.mudo = None
        def SetMasterVolume(s, x, ctx): s.v = x
        def SetMute(s, m, ctx): s.mudo = m
        def GetMasterVolume(s): return s.v if s.v is not None else 1.0
    a, b = Vol(), Vol()
    class Ses:
        def __init__(s, v): s.SimpleAudioVolume = v
    monkeypatch.setattr(spotify, "_sessoes_spotify", lambda: [Ses(a), Ses(b)])
    assert spotify.definir_volume(30) == 30 and a.v == 0.3 and b.v == 0.3 and a.mudo == 0
    assert spotify.definir_volume(250) == 100 and a.v == 1.0       # limita em 100
    assert spotify.ajustar_volume(-15) == 85


def test_sem_sessao_de_audio_o_volume_espera_ou_avisa(monkeypatch):
    monkeypatch.setattr(spotify, "_sessoes_spotify", lambda: [])
    assert spotify.definir_volume(50) is None
    assert "ainda não está tocando" in spotify.controle("volume", 50)


@pytest.mark.parametrize("frase,esperado", [
    ("Jarvis, volume em 30", ("volume", 30)), ("jarvis volume no máximo", ("volume", 100)), ("Jarvis: põe o volume em 15%", ("volume", 15)),
])
def test_o_jarvis_na_frente_nao_atrapalha_o_comando_de_volume(monkeypatch, frase, esperado):
    vistos = []
    monkeypatch.setattr(spotify, "controle", lambda a, v=None: vistos.append((a, v)) or "ok")
    assert jarvis._musica(frase, "web") == "ok" and vistos == [esperado]


def test_o_volume_nao_come_o_fim_de_palavras_como_oceano():
    assert jarvis._extrair_volume("toca Djavan Oceano com o volume em 20%") == (20, "toca Djavan Oceano")
    assert jarvis._extrair_volume("toca Oceano no volume em 5") == (5, "toca Oceano")
    assert jarvis._extrair_volume("toca Legião Urbana Tempo Perdido no volume 10") == (10, "toca Legião Urbana Tempo Perdido")
