# -*- coding: utf-8 -*-
"""Consulta de LEIS (repositorio github.com/danalec/legalize-br: 198 mil leis, decretos e MPs de 1988-2026, 1 arquivo .md por norma, de graca e local).
Indice FTS5 so de titulo + ementa + inicio do texto (data/legislacao.db, ~100 MB); a norma inteira se le do arquivo. Reconstruir: python -m braniac.leis indexar"""
import html
import re
import sqlite3
import sys
import urllib.request
from .store import DATA

PASTA = DATA / "legislacao" / "br"
DB = DATA / "legislacao.db"
INICIO = 3000   # caracteres do texto que entram no indice


def _meta(txt):
    m = lambda k: (re.search(rf"^{k}: (.*)$", txt, re.M) or [0, ""])[1].strip()
    aut = (re.search(r"autoridade: (.*)", txt) or [0, ""])[1].strip()    # Federal / Estadual / Municipal
    loc = (re.search(r"localidade: (.*)", txt) or [0, ""])[1].strip()
    return m("titulo"), m("rango"), m("fecha_publicacion"), f"{aut} {loc}".strip() or "?", (re.search(r"ementa: (.*)", txt) or [0, ""])[1].strip()


def indexar():
    """Le o comeco de cada arquivo e monta o indice (alguns minutos)."""
    con = sqlite3.connect(DB)
    con.execute("DROP TABLE IF EXISTS leis")
    con.execute("CREATE VIRTUAL TABLE leis USING fts5(id UNINDEXED, titulo, rango UNINDEXED, data UNINDEXED, local UNINDEXED, ementa, texto, tokenize='unicode61 remove_diacritics 2')")
    for i, arq in enumerate(PASTA.iterdir(), 1):
        with open(arq, encoding="utf-8", errors="ignore") as f:
            txt = f.read(INICIO + 1200)
        t, r, d, loc, e = _meta(txt)
        con.execute("INSERT INTO leis VALUES (?,?,?,?,?,?,?)", (arq.stem, t, r, d, loc, e, txt.split("---", 2)[-1][:INICIO]))
        if i % 20000 == 0:
            con.commit()
            print(i, flush=True)
    con.commit()
    con.close()


def buscar(termo, n=8):
    """Texto com as normas que mais combinam com o termo (id, tipo, data, local, titulo/ementa). Use ler(id) para o texto."""
    if not DB.exists():
        return "O indice de leis ainda nao foi montado (python -m braniac.leis indexar)."
    palavras = re.findall(r"\w+", termo, re.U)
    if not palavras:
        return "Diga o que procurar (assunto, numero ou nome da lei)."
    con = sqlite3.connect(DB)
    q = " ".join(f'"{p}"' for p in palavras)
    sql = "SELECT id, rango, data, local, titulo, ementa FROM leis WHERE leis MATCH ? AND rango NOT LIKE 'PL%' ORDER BY (local LIKE 'Federal%') DESC, bm25(leis, 0, 8, 0, 0, 0, 4, 1) LIMIT ?"
    rows = con.execute(sql, (q, n)).fetchall()
    if not rows and len(palavras) > 1:     # nenhuma norma tem TODAS as palavras: tenta qualquer uma das palavras fortes
        rows = con.execute(sql, (" OR ".join(f'"{p}"' for p in palavras if len(p) > 3) or q, n)).fetchall()
    con.close()
    return "\n".join(f"[{i}] {r} {d} ({loc}) {t[:90]} :: {e[:160]}" for i, r, d, loc, t, e in rows) or "Nada encontrado (tente menos palavras)."


def ler(id_norma, maximo=6000, a_partir=0):
    """Texto de uma norma pelo id (so digitos/letras/hifen)."""
    if not re.fullmatch(r"[\w-]+", str(id_norma)):
        return "id invalido"
    arq = PASTA / f"{id_norma}.md"
    if not arq.exists():
        return "norma nao encontrada"
    txt = arq.read_text(encoding="utf-8", errors="ignore")
    return txt[a_partir:a_partir + maximo] + (f"\n[... continua: a_partir={a_partir + maximo} de {len(txt)}]" if len(txt) > a_partir + maximo else "")


# o Planalto derruba conexao sem cabecalho completo de navegador (so "Mozilla/5.0" nao basta)
CABECALHO = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
             "Accept": "text/html,application/xhtml+xml", "Accept-Language": "pt-BR,pt;q=0.9"}
BLOCOS = ((2023, 2026), (2019, 2022), (2015, 2018), (2011, 2014), (2007, 2010), (2004, 2006))
ANTIGOS = ((1990, 1994), (1995, 1998), (1999, 2000), (2001, 2002), (2003, 2006))   # pastas de decretos antigos


def _urls_planalto(tipo, num, ano):
    L, p = ("L", "lei") if tipo == "lei" else ("D", "decreto")
    nomes = [f"{L}{num}", f"{L.lower()}{num}"]
    base = "https://www.planalto.gov.br/ccivil_03/"
    bloco = next((f"_ato{a}-{b}" for a, b in BLOCOS if a <= ano <= b), None)
    urls = [f"{base}{bloco}/{ano}/{p}/{n}.htm" for n in nomes] if bloco else []
    pasta = next((f"{a}-{b}" for a, b in ANTIGOS if a <= ano <= b), "")
    if tipo == "decreto":
        urls += [f"{base}decreto/{pasta}/{n}.htm" for n in nomes] + [f"{base}decreto/{n}.htm" for n in nomes]
    else:
        urls += [f"{base}leis/{n}.htm" for n in nomes] + [f"{base}leis/{ano}/{n}.htm" for n in nomes] + [f"{base}leis/LEIS_{ano}/{n}.htm" for n in nomes]
    return urls


def planalto(tipo, numero, ano, maximo=6000, a_partir=0):
    """Texto OFICIAL de uma lei/decreto federal no site do Planalto (inclui o aviso 'Revogado pelo...' da pagina). tipo: 'lei' ou 'decreto'."""
    num = re.sub(r"\D", "", str(numero))
    if tipo not in ("lei", "decreto") or not num or not str(ano).isdigit():
        return "Use tipo 'lei' ou 'decreto', numero (so digitos) e ano."
    for url in _urls_planalto(tipo, num, int(ano)):
        try:
            req = urllib.request.Request(url, headers=CABECALHO)
            txt = urllib.request.urlopen(req, timeout=30).read().decode("latin-1", "ignore")
        except OSError:
            continue
        txt = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<style.*?</style>|<script.*?</script>", " ", txt)))).strip()
        if len(txt) > 300 and "não foi encontrado" not in txt[:200]:    # a pagina de erro do Planalto devolve HTTP 200
            resto = f"\n[... continua: a_partir={a_partir + maximo} de {len(txt)}]" if len(txt) > a_partir + maximo else ""
            return f"{url}\n{txt[a_partir:a_partir + maximo]}{resto}"
    return "Nao achei essa norma no Planalto (confira tipo, numero e ano; normas antigas e portarias ficam em outros sites)."


if __name__ == "__main__":
    if sys.argv[1:] == ["indexar"]:
        indexar()
    elif sys.argv[1:2] in (["lei"], ["decreto"]) and len(sys.argv) == 4:
        print(planalto(sys.argv[1], sys.argv[2], sys.argv[3]))
    else:
        print(buscar(" ".join(sys.argv[1:])))
