# -*- coding: utf-8 -*-
"""Atualizacao AUTOMATICA pelas releases do GitHub (so BAIXA; nada da pessoa sobe).

A cada ALGUMAS HORAS (e na abertura) consulta a ultima release de carloslavig/B.R.A.N.I.A.C. Se a versao for maior que a instalada:
baixa o instalador (so de github.com/carloslavig), confere o SHA-256 que a release publica ('SHA256: <hex>' nas notas) e roda em segundo plano
(/S: sem janela; instala por usuario e mantem as configuracoes). Sem hash na release, ou hash diferente: NAO instala.
A pessoa desliga com `atualizacao_automatica: false` no perfil (ou falando 'desligar atualizacao automatica'). Se a instalacao falhar, a versao atual segue instalada."""
import hashlib, json, os, re, subprocess, tempfile, threading, time, urllib.request
from pathlib import Path
from . import __version__, perfil

REPO = "carloslavig/B.R.A.N.I.A.C"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
HOSTS_OK = (f"https://github.com/{REPO}/", "https://objects.githubusercontent.com/", "https://release-assets.githubusercontent.com/")
INTERVALO_S = 6 * 3600
_ESTADO = {"ultima_checagem": None, "ultima_versao": None, "mensagem": ""}


class UpdateErro(RuntimeError):
    pass


def _vkey(v):
    return tuple(int(x) for x in re.findall(r"\d+", str(v)))


def _get(url, limite=300 * 1024 * 1024):
    if not url.startswith(("https://api.github.com/",) + HOSTS_OK):
        raise UpdateErro("endereço de atualização não confiável")
    req = urllib.request.Request(url, headers={"User-Agent": "braniac-auto-update", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        dados = r.read(limite + 1)
    if len(dados) > limite:
        raise UpdateErro("arquivo grande demais")
    return dados


def ativa():
    return bool(perfil.carregar().get("atualizacao_automatica", True))


def definir(ligada):
    perfil.atualizar(atualizacao_automatica=bool(ligada))
    return bool(ligada)


def procurar(baixar=None, atual=None):
    """Devolve {'versao','url','sha256'} da release mais nova que a instalada, ou None. Levanta UpdateErro se a release for suspeita."""
    rel = json.loads((baixar or _get)(API).decode("utf-8"))
    v = str(rel.get("tag_name", "")).lstrip("v")
    _ESTADO.update(ultima_checagem=time.strftime("%Y-%m-%d %H:%M:%S"), ultima_versao=v)
    if not v or _vkey(v) <= _vkey(atual or __version__):
        return None
    asset = next((a for a in rel.get("assets", []) if re.fullmatch(r"BRANIAC_[\d.]+_x64-setup\.exe", a.get("name", ""))), None)
    if not asset:
        raise UpdateErro(f"a release {v} não tem o instalador")
    m = re.search(r"SHA256:\s*([0-9a-fA-F]{64})", rel.get("body") or "")
    if not m:
        raise UpdateErro(f"a release {v} não publica o SHA-256; não instalo sem conferir")
    return {"versao": v, "url": asset["browser_download_url"], "sha256": m.group(1).lower()}


def baixar_e_conferir(info, baixar=None):
    dados = (baixar or _get)(info["url"])
    if hashlib.sha256(dados).hexdigest() != info["sha256"]:
        raise UpdateErro("o instalador baixado não confere com o SHA-256 da release (corrompido ou adulterado)")
    pasta = Path(tempfile.mkdtemp(prefix="braniac-update-"))
    arq = pasta / f"BRANIAC_{info['versao']}_x64-setup.exe"
    arq.write_bytes(dados)
    return arq


def instalar(arq):
    """Roda o instalador em segundo plano (o proprio instalador fecha o app antigo e reabre o novo)."""
    subprocess.Popen([str(arq), "/S", "/UPDATE"], creationflags=0x08000000 | getattr(subprocess, "DETACHED_PROCESS", 0),
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def checar_e_atualizar(baixar=None, executar=None):
    """Um ciclo completo. Devolve texto curto do que aconteceu."""
    try:
        info = procurar(baixar)
        if not info:
            _ESTADO["mensagem"] = f"Você está na versão mais nova ({__version__})."
            return _ESTADO["mensagem"]
        arq = baixar_e_conferir(info, baixar)
        (executar or instalar)(arq)
        _ESTADO["mensagem"] = f"Atualizando para a versão {info['versao']}…"
    except Exception as e:      # sem internet, limite do GitHub, hash errado: nada muda e tenta de novo depois
        _ESTADO["mensagem"] = f"Não consegui atualizar agora: {str(e)[:120]}"
    return _ESTADO["mensagem"]


def estado():
    return {**_ESTADO, "ativa": ativa(), "versao": __version__}


def iniciar():
    def loop():
        time.sleep(90)                       # deixa o app abrir antes
        while True:
            if ativa():
                checar_e_atualizar()
            time.sleep(INTERVALO_S)
    threading.Thread(target=loop, daemon=True, name="auto-update").start()
