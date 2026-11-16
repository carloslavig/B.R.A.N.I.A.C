# -*- coding: utf-8 -*-
"""Limpeza de disco assistida (Dono, 07/10/2026). SO ANALISA e, quando mandado, move DUPLICADOS EXATOS para a Lixeira (reversivel).
Nada e apagado em definitivo aqui e a Lixeira nunca e esvaziada por este modulo: quem libera o espaco de verdade e o Dono.
Nunca toca: pastas do sistema/programas, AppData, .git, projetos (Projetos/), perfis de navegador, pastas do Braniac/BRANIAC.
python -m braniac.limpeza varrer [raizes...]   -> data/limpeza/relatorio.json  (+ resumo)
python -m braniac.limpeza resumo               -> imprime o ultimo resumo"""
import hashlib, json, os, sys, time
from collections import defaultdict
from pathlib import Path

DATA = Path(__file__).parent / "data" / "limpeza"
MIN_DUP = 20 * 1024 * 1024
IGNORAR = {"$recycle.bin", "system volume information", "windows", "program files", "program files (x86)", "programdata", "appdata", ".git", "node_modules",
           "projetos", "chromeagente", "braniacloja", "braniacloja", "recovery", "msocache", "$windows.~bt", "windowsapps", "onedrive"}
EXTENSOES_SEGURAS_DUP = None   # qualquer tipo: so duplicado EXATO (hash completo) conta


def _pular(nome):
    return nome.lower() in IGNORAR


def tamanhos_pastas(raiz, profundidade=2, topo=25):
    """Tamanho das pastas ate N niveis (onde o espaco esta indo)."""
    tot = defaultdict(int)
    raiz = Path(raiz)

    def andar(p, nivel):
        total = 0
        try:
            with os.scandir(p) as it:
                for e in it:
                    try:
                        if e.is_symlink():
                            continue
                        if e.is_dir(follow_symlinks=False):
                            total += andar(e.path, nivel + 1)
                        else:
                            total += e.stat(follow_symlinks=False).st_size
                    except OSError:
                        pass
        except OSError:
            return 0
        if nivel <= profundidade:
            tot[str(p)] = total
        return total
    andar(raiz, 0)
    return sorted(tot.items(), key=lambda x: -x[1])[:topo]


def _hash(caminho, parcial=False):
    h = hashlib.sha1()
    try:
        with open(caminho, "rb") as f:
            if parcial:
                h.update(f.read(1 << 20))
                f.seek(-min(1 << 20, os.path.getsize(caminho)), 2)
                h.update(f.read(1 << 20))
            else:
                while True:
                    b = f.read(1 << 22)
                    if not b:
                        break
                    h.update(b)
    except OSError:
        return None
    return h.hexdigest()


def duplicados(raizes, minimo=MIN_DUP, limite_s=3600):
    """Grupos de arquivos IDENTICOS (mesmo tamanho, mesmo hash do inicio+fim e do conteudo inteiro)."""
    por_tam = defaultdict(list)
    fim = time.time() + limite_s
    for raiz in raizes:
        for dirpath, dirs, files in os.walk(raiz):
            dirs[:] = [d for d in dirs if not _pular(d)]
            for f in files:
                p = os.path.join(dirpath, f)
                try:
                    st = os.stat(p)
                    if st.st_size >= minimo and not os.path.islink(p):
                        por_tam[st.st_size].append(p)
                except OSError:
                    pass
            if time.time() > fim:
                break
    grupos = []
    for tam, caminhos in por_tam.items():
        if len(caminhos) < 2:
            continue
        por_parcial = defaultdict(list)
        for p in caminhos:
            h = _hash(p, parcial=True)
            if h:
                por_parcial[h].append(p)
        for lista in por_parcial.values():
            if len(lista) < 2:
                continue
            por_total = defaultdict(list)
            for p in lista:
                h = _hash(p)
                if h:
                    por_total[h].append(p)
            for l2 in por_total.values():
                if len(l2) > 1:
                    grupos.append({"tamanho": tam, "arquivos": sorted(l2), "desperdicio": tam * (len(l2) - 1)})
    return sorted(grupos, key=lambda g: -g["desperdicio"])


def varrer(raizes=None):
    DATA.mkdir(parents=True, exist_ok=True)
    raizes = raizes or [str(Path.home()), "E:\\"]
    rel = {"quando": time.strftime("%Y-%m-%d %H:%M"), "raizes": raizes, "pastas": {}, "duplicados": []}
    for r in raizes:
        if os.path.exists(r):
            rel["pastas"][r] = tamanhos_pastas(r)
    rel["duplicados"] = duplicados([r for r in raizes if os.path.exists(r)])
    rel["desperdicio_total_gb"] = round(sum(g["desperdicio"] for g in rel["duplicados"]) / 1e9, 1)
    (DATA / "relatorio.json").write_text(json.dumps(rel, ensure_ascii=False, indent=1), encoding="utf-8")
    return rel


def resumo(rel=None, max_grupos=15):
    rel = rel or json.loads((DATA / "relatorio.json").read_text(encoding="utf-8"))
    linhas = [f"Varredura de {rel['quando']}: {len(rel['duplicados'])} grupos de duplicados exatos, ~{rel['desperdicio_total_gb']} GB repetidos."]
    for g in rel["duplicados"][:max_grupos]:
        linhas.append(f"- {g['tamanho'] / 1e9:.2f} GB x{len(g['arquivos'])}: " + " | ".join(g["arquivos"]))
    return "\n".join(linhas)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "resumo":
        print(resumo())
    else:
        r = varrer(sys.argv[2:] or None)
        print(resumo(r))
