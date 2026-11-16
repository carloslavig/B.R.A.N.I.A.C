"""Trava antes de publicar: procura dado pessoal no codigo que vai para o repositorio publico.

Uso: python scripts/varrer_pessoal.py [--export] <pasta> [<pasta> ...]   -> sai com 1 se achar algo.
Padroes genericos ficam aqui. Nomes de pessoas/lugares do dono ficam em scripts/termos-pessoais.txt
(um por linha, fora do git), porque a propria lista ja seria dado pessoal.
"""
import os
import pathlib
import re
import sys

EXT = {".py", ".html", ".js", ".json", ".md", ".rs", ".ps1", ".toml", ".txt"}
PULAR = {"node_modules", "target", "__pycache__", ".git", "graphify-out", "dist", "build", "binaries", "data", "dados-link", "modelos"}
GENERICOS = {
    "caminho de usuario": r"[A-Za-z]:[\\/]+Users[\\/]+(?!<|\{|%|\$|Public\b|usuario\b)[A-Za-z0-9._-]+",
    "telefone": r"(?<!\d)(?:\+?55\s?)?\(?\d{2}\)?\s?9\d{4}[-\s]?\d{4}(?!\d)",
    "e-mail": r"[A-Za-z0-9._%+-]+@(?!example\.)[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    "id do Google Drive": r"[\"']1[A-Za-z0-9_-]{27,40}[\"']",
    "projeto do ChatGPT": r"chatgpt\.com/g/g-p-[0-9a-f]{16,}",
    "chave de API": r"\b(?:sk-[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{30,}|gsk_[A-Za-z0-9]{20,}|nvapi-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{30,})",
}
# numero de exemplo em teste: 4 digitos iguais seguidos ou a sequencia 5432
FICTICIO = re.compile(r"(\d)\1{3}|5432")
# listas locais (fora do git) que guardam justamente os nomes
LISTAS_LOCAIS = {"termos-pessoais.txt", "extras-publico.txt", "dados-padrao.json", "termos-export.txt", "trocas-pessoais.json", "fora-do-publico.txt"}
# trechos que podem aparecer em codigo publico sem ser dado de ninguem
LIBERADO = ("varredura: ok", "noreply@", "@acme.", "@exemplo.", "@empresa.", "@s.whatsapp.net", "Monte Carlo", "rh@", "x@", "maria@", "@x.com", "@b.com", "@loja.", "@braniac.local", "@linkedin.com", "@sebrae.", "git@github.com","github.com/carloslavig", "@types/")


def carregar_termos(arquivo):
    p = pathlib.Path(arquivo)
    if not p.exists():
        return []
    return [t.strip() for t in p.read_text(encoding="utf-8").splitlines() if t.strip() and not t.startswith("#")]


def _arquivos(pastas):
    for pasta in map(pathlib.Path, pastas):
        if pasta.is_file():
            yield pasta
            continue
        for raiz, dirs, nomes in os.walk(pasta):
            dirs[:] = [d for d in dirs if d not in PULAR]   # nem entra em node_modules/data
            yield from (pathlib.Path(raiz, n) for n in nomes if n not in LISTAS_LOCAIS)


def varrer(pastas, termos=()):
    regras = {nome: re.compile(rx) for nome, rx in GENERICOS.items()}
    if termos:
        regras["termo pessoal"] = re.compile(r"\b(?:" + "|".join(re.escape(t) for t in termos) + r")\b", re.I)
    achados = []
    for f in _arquivos(pastas):
            if f.suffix.lower() not in EXT:
                continue
            for n, linha in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                for nome, rx in regras.items():
                    m = rx.search(linha)
                    if m and nome == "telefone" and FICTICIO.search(re.sub(r"\D", "", m.group(0))):
                        continue
                    if m and not any(ok in linha for ok in LIBERADO):
                        achados.append((str(f), n, nome, m.group(0)))
    return achados


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    termos = carregar_termos(pathlib.Path(__file__).with_name("termos-pessoais.txt"))
    if argv[0] == "--export":   # copia do Braniac real: o nome do autor tambem nao pode sobrar
        argv = argv[1:]
        termos += carregar_termos(pathlib.Path(__file__).with_name("termos-export.txt"))
    achados = varrer(argv, termos)
    for f, n, nome, trecho in achados:
        print(f"{f}:{n}: {nome}: {trecho}")
    print(f"\n{len(achados)} achado(s)." if achados else "Nada pessoal encontrado.")
    return 1 if achados else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
