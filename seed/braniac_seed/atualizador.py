# -*- coding: utf-8 -*-
"""Atualizacao so de NOVAS FUNCOES e PARAMETROS (nunca dados da pessoa). O PC so BAIXA do repositorio; nada da pessoa sobe.

Manifesto (manifest.json no GitHub): {"versao": "1.4.0", "pacotes": [{"nome": "funcoes-1.4.0.zip", "url": "https://...", "sha256": "..."}]}
Seguranca: so URLs HTTPS do dono do repositorio; confere SHA-256 do pacote antes de instalar; instala em pasta versionada, mantem a anterior
e volta sozinho para ela se a nova nao iniciar (rollback). Proximo passo planejado: assinar o manifesto (Ed25519) com chave publica embutida.
"""
import hashlib, json, shutil, urllib.request, zipfile
from pathlib import Path
from . import paths

REPO_DONO = "https://github.com/carloslavig/"
HOSTS_OK = ("https://github.com/carloslavig/", "https://raw.githubusercontent.com/carloslavig/", "https://objects.githubusercontent.com/")
MANIFESTO_URL = "https://raw.githubusercontent.com/carloslavig/B.R.A.N.I.A.C/main/manifest.json"


class UpdateErro(RuntimeError):
    pass


def _ext():
    d = paths.dados_dir() / "extensoes"
    d.mkdir(exist_ok=True)
    return d


def _baixar(url):
    if not url.startswith(HOSTS_OK):
        raise UpdateErro("endereço de atualização não confiável")
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "braniac-seed"}), timeout=60) as r:
        return r.read()


def versao_atual():
    try:
        return json.loads((_ext() / "atual.json").read_text(encoding="utf-8"))["versao"]
    except (OSError, ValueError, KeyError):
        return None


def _vkey(v):
    return tuple(int(x) for x in str(v).split(".") if x.isdigit())


def ha_atualizacao(manifesto):
    atual = versao_atual()
    return atual is None or _vkey(manifesto["versao"]) > _vkey(atual)


def instalar(manifesto, baixar=None):
    """Baixa, confere o hash e instala numa pasta nova. So troca o ponteiro 'atual' depois de tudo certo."""
    baixar = baixar or _baixar
    v = manifesto["versao"]
    destino = _ext() / v
    tmp = _ext() / (v + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    try:
        for pac in manifesto["pacotes"]:
            dados = baixar(pac["url"])
            if hashlib.sha256(dados).hexdigest() != pac["sha256"].lower():
                raise UpdateErro(f"pacote {pac['nome']} corrompido ou adulterado (hash não confere)")
            z = tmp / pac["nome"]
            z.write_bytes(dados)
            with zipfile.ZipFile(z) as zf:
                for n in zf.namelist():                       # impede escrever fora da pasta (zip malicioso)
                    if Path(n).is_absolute() or ".." in Path(n).parts:
                        raise UpdateErro("pacote com caminho inválido")
                zf.extractall(tmp / "conteudo")
            z.unlink()
        shutil.rmtree(destino, ignore_errors=True)
        tmp.rename(destino)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    anterior = versao_atual()
    (_ext() / "atual.json").write_text(json.dumps({"versao": v, "anterior": anterior}), encoding="utf-8")
    return destino


def reverter():
    """Rollback: volta para a versao anterior (usado quando a nova nao inicia)."""
    try:
        d = json.loads((_ext() / "atual.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise UpdateErro("nada para reverter")
    if not d.get("anterior") or not (_ext() / d["anterior"]).exists():
        raise UpdateErro("não há versão anterior guardada")
    (_ext() / "atual.json").write_text(json.dumps({"versao": d["anterior"], "anterior": None}), encoding="utf-8")
    return d["anterior"]


def buscar_manifesto(baixar=None):
    return json.loads((baixar or _baixar)(MANIFESTO_URL).decode("utf-8"))
