# -*- coding: utf-8 -*-
"""Upload para o YouTube (Shorts) pela API oficial (YouTube Data API v3, videos.insert).

Configuracao (uma vez, feita PELO DONO):
 1. console.cloud.google.com -> projeto -> ativar "YouTube Data API v3"
 2. Credenciais -> ID do cliente OAuth tipo "App para computador" -> baixar o JSON
 3. Salvar como braniac/data/cortes/youtube_client_secret.json
 4. python -m braniac.cortes youtube-login   (abre o navegador; o Dono faz o login e autoriza)
O token fica em data/cortes/youtube_token.json (fora do git). Perfil com canal proprio (ex.: gringo, em ingles):
 python -m braniac.cortes youtube-login --perfil gringo  ->  youtube_token_gringo.json (logar na conta/canal do perfil)
 python -m braniac.cortes youtube-canal --perfil gringo  ->  aplica descricao, palavras-chave e playlists do canal Projeto nao auditado pelo Google: videos sobem como privados."""
from . import config

ESCOPOS = ["https://www.googleapis.com/auth/youtube.upload"]
ESCOPOS_CANAL = ESCOPOS + ["https://www.googleapis.com/auth/youtube"]  # perfis: tambem edita o "Sobre" e cria playlists


def _arqs(conta=""):
    return config.PASTA / "youtube_client_secret.json", config.PASTA / (f"youtube_token_{conta}.json" if conta else "youtube_token.json")


def _escopos(conta):
    return ESCOPOS_CANAL if conta else ESCOPOS


def configurado(conta=""):
    return _arqs(conta)[1].exists()


def login(conta=""):
    """Fluxo OAuth no navegador. So o Dono executa (o agente nao faz login)."""
    from google_auth_oauthlib.flow import InstalledAppFlow
    segredo, token = _arqs(conta)
    if not segredo.exists():
        raise RuntimeError(f"falta {segredo} (baixe o JSON do cliente OAuth no Google Cloud)")
    cred = InstalledAppFlow.from_client_secrets_file(str(segredo), _escopos(conta)).run_local_server(port=0)
    token.write_text(cred.to_json(), encoding="utf-8")
    return f"login do YouTube salvo{' (' + conta + ')' if conta else ''}"


def _servico(conta=""):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    _, token = _arqs(conta)
    if not token.exists():
        raise RuntimeError("YouTube nao configurado: rode 'python -m braniac.cortes youtube-login" + (f" --perfil {conta}'" if conta else "'"))
    cred = Credentials.from_authorized_user_file(str(token), _escopos(conta))
    if not cred.valid and cred.refresh_token:
        cred.refresh(Request())
        token.write_text(cred.to_json(), encoding="utf-8")
    return build("youtube", "v3", credentials=cred, cache_discovery=False)


def enviar(arquivo, titulo, descricao, tags, privacidade="private", categoria="20", conta="", publicar_em=None):
    """Sobe o video e devolve o id do YouTube. publicar_em (timestamp): sobe privado e o YouTube publica sozinho nessa hora."""
    from googleapiclient.http import MediaFileUpload
    if "#shorts" not in (titulo + descricao).lower():
        descricao = (descricao + "\n\n#shorts").strip()
    corpo = {"snippet": {"title": titulo[:100], "description": descricao[:4900], "tags": [t.lstrip("#") for t in tags][:15],
                         "categoryId": str(categoria)},
             "status": {"privacyStatus": privacidade, "selfDeclaredMadeForKids": False}}
    if publicar_em:
        import datetime as _dt
        corpo["status"].update(privacyStatus="private", publishAt=_dt.datetime.fromtimestamp(publicar_em, _dt.timezone.utc)
                               .strftime("%Y-%m-%dT%H:%M:%S.000Z"))
    req = _servico(conta).videos().insert(part="snippet,status", body=corpo,
                                     media_body=MediaFileUpload(str(arquivo), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    return resp["id"]


def configurar_canal(perfil):
    """Aplica no canal do perfil o kit de data/cortes/canal_<perfil>.json: descricao (Sobre), palavras-chave, pais, idioma
    e playlists (cria so as que faltam). Nao mexe em nome/foto/banner (isso o Dono faz no YouTube Studio)."""
    import json
    kit = json.loads((config.PASTA / f"canal_{perfil}.json").read_text(encoding="utf-8"))
    conta = config.do_perfil(perfil).get("youtube_conta", perfil)
    yt = _servico(conta)
    canal = yt.channels().list(part="id,brandingSettings", mine=True).execute()["items"][0]
    marca = canal.get("brandingSettings", {})
    marca.setdefault("channel", {}).update({"description": kit["sobre"][:1000], "keywords": " ".join(
        f'"{k}"' if " " in k else k for k in kit["palavras_chave"])[:500], "defaultLanguage": kit.get("idioma", "en"),
        "country": kit.get("pais", "US")})
    yt.channels().update(part="brandingSettings", body={"id": canal["id"], "brandingSettings": marca}).execute()
    existentes = {p["snippet"]["title"] for p in yt.playlists().list(part="snippet", mine=True, maxResults=50).execute().get("items", [])}
    criadas = []
    for pl in kit.get("playlists", []):
        if pl["titulo"] not in existentes:
            yt.playlists().insert(part="snippet,status", body={"snippet": {"title": pl["titulo"], "description": pl.get("descricao", "")},
                                                                "status": {"privacyStatus": "public"}}).execute()
            criadas.append(pl["titulo"])
    return f"canal {canal['id']} atualizado (Sobre + palavras-chave); playlists criadas: {', '.join(criadas) or 'nenhuma nova'}"
