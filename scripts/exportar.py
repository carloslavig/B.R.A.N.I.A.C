"""Gera a copia PUBLICA do Braniac real: mesmo codigo, telas e modulos, sem dado pessoal.

Uso: python scripts/exportar.py <pasta do braniac-fonte> <destino>
- So copia arquivos versionados no braniac-fonte (git ls-files): data/, .env, chaves e o que o .gitignore barra nunca entram.
- Troca nomes, lugares e enderecos pela lista local scripts/trocas-pessoais.json ([["de", "para"], ...]; fora do git,
  porque a propria lista e dado pessoal). A troca vale igual no codigo e nos testes, entao o comportamento continua o mesmo.
- Pula arquivos/pastas de scripts/fora-do-publico.txt (um padrao glob por linha, tambem local).
Depois rode: python scripts/varrer_pessoal.py <destino>  e os testes da copia.
"""
import fnmatch
import json
import pathlib
import re
import shutil
import subprocess
import sys

AQUI = pathlib.Path(__file__).resolve().parent
TEXTO = {".py", ".html", ".js", ".json", ".md", ".txt", ".toml", ".rs", ".ps1", ".bat", ".css", ".yml", ".yaml", ".cfg", ".ini", ".sh", ".mjs"}


def variantes(de, para):
    """'Tia Ana' -> tambem 'tia ana' e 'TIA ANA' (mesma caixa no destino)."""
    return {(de, para), (de.lower(), para.lower()), (de.upper(), para.upper())}


def montar_regra(trocas):
    pares = sorted({v for de, para in trocas for v in variantes(de, para)}, key=lambda p: -len(p[0]))
    mapa = dict(pares)
    # limite = qualquer coisa que nao seja letra/digito (inclusive '_'), para trocar tambem em nomes como avisar_ao_fulano
    rx = re.compile(r"(?<![^\W_])(?:" + "|".join(re.escape(de) for de, _ in pares) + r")(?![^\W_])")
    return lambda texto: rx.sub(lambda m: mapa[m.group(0)], texto)


def exportar(fonte, destino, trocas, fora=()):
    fonte, destino = pathlib.Path(fonte), pathlib.Path(destino)
    arquivos = subprocess.run(["git", "ls-files", "-z"], cwd=fonte, capture_output=True, check=True).stdout.decode("utf-8").split("\0")
    trocar = montar_regra(trocas) if trocas else (lambda t: t)
    if destino.exists():
        shutil.rmtree(destino)
    copiados = 0
    for rel in filter(None, arquivos):
        if any(fnmatch.fnmatch(rel, p) or rel.startswith(p.rstrip("*")) and p.endswith("/*") for p in fora):
            continue
        orig = fonte / rel
        if not orig.is_file():   # apagado no disco e ainda no indice
            continue
        alvo = destino / trocar(rel)
        alvo.parent.mkdir(parents=True, exist_ok=True)
        if orig.suffix.lower() in TEXTO:
            alvo.write_text(trocar(orig.read_text(encoding="utf-8", errors="surrogateescape")), encoding="utf-8", errors="surrogateescape")
        else:
            shutil.copy2(orig, alvo)
        copiados += 1
    return copiados


def exportar_padrao(fonte, destino, padrao, trocar=lambda t: t):
    """Copia a configuracao inicial de data/ para <destino>/padrao, zerando as chaves pessoais ({arquivo: [chaves]})."""
    n = 0
    for rel, zerar in padrao.items():
        orig = pathlib.Path(fonte) / "data" / rel
        if not orig.exists():
            continue
        d = json.loads(orig.read_text(encoding="utf-8"))
        for k in zerar:
            if k in d:
                d[k] = type(d[k])()
        alvo = pathlib.Path(destino) / "padrao" / rel
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_text(trocar(json.dumps(d, ensure_ascii=False, indent=1)), encoding="utf-8")
        n += 1
    return n


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    trocas_arq = AQUI / "trocas-pessoais.json"
    trocas = json.loads(trocas_arq.read_text(encoding="utf-8")) if trocas_arq.exists() else []
    fora_arq = AQUI / "fora-do-publico.txt"
    fora = [l.strip() for l in fora_arq.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")] if fora_arq.exists() else []
    n = exportar(argv[0], argv[1], trocas, fora)
    padrao_arq = AQUI / "dados-padrao.json"   # local: {"empresa_mkt/equipe.json": ["clientes"], ...}
    padrao = json.loads(padrao_arq.read_text(encoding="utf-8")) if padrao_arq.exists() else {}
    p = exportar_padrao(argv[0], argv[1], padrao, montar_regra(trocas) if trocas else (lambda t: t))
    print(f"{n} arquivos exportados para {argv[1]} ({len(trocas)} trocas, {len(fora)} exclusoes, {p} configuracoes iniciais).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
