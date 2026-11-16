"""Habilidades de terceiros: o Braniac nao as distribui; so oferece baixar do GitHub do proprio autor (16/11/2026).

Catalogo em habilidades_terceiros.json (id local, repositorio, pasta no repositorio, licenca, grupo). Na primeira vez a tela
pergunta se a pessoa quer instalar; ela marca/desmarca e so as marcadas sao baixadas para skills/<id>.
So baixa de api.github.com/codeload.github.com e so os repositorios do catalogo. Texto de habilidade baixada e dado, nunca ordem.
"""
import io
import json
import shutil
import urllib.request
import zipfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
CATALOGO = AQUI / "habilidades_terceiros.json"
SKILLS = AQUI / "skills"
ESTADO = AQUI / "data" / "habilidades_terceiros.json"
HOSTS_OK = ("https://api.github.com/", "https://codeload.github.com/")
LIMITE_ZIP = 80 * 1024 * 1024


def catalogo():
    return json.loads(CATALOGO.read_text(encoding="utf-8"))


def _estado():
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"perguntado": False, "instaladas": []}


def _gravar(est):
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    ESTADO.write_text(json.dumps(est, ensure_ascii=False, indent=1), encoding="utf-8")


def status():
    est = _estado()
    itens = [dict(i, instalada=(SKILLS / i["id"] / "SKILL.md").exists()) for i in catalogo()]
    return {"perguntado": est.get("perguntado", False), "itens": itens}


def recusar():
    est = _estado()
    est["perguntado"] = True
    _gravar(est)
    return status()


def _baixar(repo):
    """Zip do repositorio inteiro (branch padrao) direto do GitHub do autor."""
    url = f"https://api.github.com/repos/{repo}/zipball"

    class SoGithub(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, novo):
            if not novo.startswith(HOSTS_OK):
                raise ValueError(f"redirecionamento fora do GitHub: {novo}")
            return super().redirect_request(req, fp, code, msg, headers, novo)

    req = urllib.request.Request(url, headers={"User-Agent": "braniac-habilidades", "Accept": "application/vnd.github+json"})
    with urllib.request.build_opener(SoGithub).open(req, timeout=60) as r:
        dados = r.read(LIMITE_ZIP + 1)
    if len(dados) > LIMITE_ZIP:
        raise ValueError("repositorio grande demais")
    return dados


def _extrair(dados_zip, caminho, destino):
    """Copia so a pasta `caminho` do zip para `destino` (sem sair dela: barra ../ e caminho absoluto)."""
    zf = zipfile.ZipFile(io.BytesIO(dados_zip))
    raiz = zf.namelist()[0].split("/")[0] + "/"
    prefixo = raiz + (caminho.strip("/") + "/" if caminho.strip("/") else "")
    tmp = destino.with_name(destino.name + ".novo")
    shutil.rmtree(tmp, ignore_errors=True)
    n = 0
    for nome in zf.namelist():
        if not nome.startswith(prefixo) or nome.endswith("/"):
            continue
        rel = nome[len(prefixo):]
        alvo = (tmp / rel).resolve()
        if not str(alvo).startswith(str(tmp.resolve())):
            continue
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_bytes(zf.read(nome))
        n += 1
    if not (tmp / "SKILL.md").exists():
        shutil.rmtree(tmp, ignore_errors=True)
        raise ValueError(f"SKILL.md nao encontrado em {caminho or '(raiz)'}")
    shutil.rmtree(destino, ignore_errors=True)
    tmp.rename(destino)
    return n


def instalar(ids, baixar=None):
    """Baixa e instala so os ids marcados. Devolve {'ok': [...], 'falhou': {id: motivo}}."""
    baixar = baixar or _baixar
    por_id = {i["id"]: i for i in catalogo()}
    zips, ok, falhou = {}, [], {}
    for hid in ids:
        item = por_id.get(hid)
        if not item:
            falhou[str(hid)] = "fora do catalogo"
            continue
        try:
            if item["repo"] not in zips:
                zips[item["repo"]] = baixar(item["repo"])
            _extrair(zips[item["repo"]], item["caminho"], SKILLS / item["id"])
            ok.append(hid)
        except Exception as e:   # um repositorio fora do ar nao impede os outros
            falhou[hid] = str(e)[:200]
    est = _estado()
    est["perguntado"] = True
    est["instaladas"] = sorted(set(est.get("instaladas", [])) | set(ok))
    _gravar(est)
    return {"ok": ok, "falhou": falhou}


if __name__ == "__main__":
    for i in status()["itens"]:
        print(("[x] " if i["instalada"] else "[ ] ") + f"{i['id']:32} {i['repo']} ({i['licenca']})")
