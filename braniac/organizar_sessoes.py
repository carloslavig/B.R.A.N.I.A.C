# -*- coding: utf-8 -*-
"""Organiza as conversas da aba Sessoes do B.R.A.N.I.A.C 1 (b2.py) por assunto, igual a skill organizar-conversas do Claude.
So MOVE conversas que ainda estao em 'Geral' para o projeto do assunto (cria o projeto se faltar). Nao apaga, nao arquiva, nao renomeia."""
import re
import sqlite3

from . import b2

# (projeto, palavras). A primeira regra que casar vence; projeto novo e criado com este nome.
REGRAS = [
    ("🎬 Parceiro / Vídeos", r"v[ií]deo|esteira|salvador|parceiro|reels?|cortes?\b"),
    ("🌐 Sites e clientes", r"\bsites?\b|landing|aventur|cliente|layla|esfiha|l[ií]bano|estoque|loja|vaquinha"),
    ("🧠 Braniac e ferramentas", r"braniac|jarvis|pr[eé]dio|agentes?\b|habilidade|skill|programar|conselho|claude|\bpc\b|notebook"),
]


def organizar(aplicar=True):
    """Devolve [(id, titulo, projeto_novo)] do que moveu (ou moveria, se aplicar=False)."""
    feitas = []
    with b2._con() as c:
        geral = c.execute("SELECT id FROM projetos WHERE nome='Geral'").fetchone()
        if not geral:
            return feitas
        ids = {n: i for i, n in c.execute("SELECT id, nome FROM projetos")}
        for cid, titulo in c.execute("SELECT id, titulo FROM conversas WHERE arquivada=0 AND projeto=?", (geral[0],)).fetchall():
            for nome, rx in REGRAS:
                if re.search(rx, titulo or "", re.I):
                    if aplicar:
                        if nome not in ids:
                            ids[nome] = c.execute("INSERT INTO projetos(nome, instrucoes, criado) VALUES(?, '', strftime('%s','now'))", (nome,)).lastrowid
                        c.execute("UPDATE conversas SET projeto=? WHERE id=?", (ids[nome], cid))
                    feitas.append((cid, titulo, nome))
                    break
    return feitas


def resumo(aplicar=True):
    f = organizar(aplicar)
    if not f:
        return "Nada a organizar: as conversas de Geral nao casam com nenhum assunto."
    return ("Movi " if aplicar else "Moveria ") + f"{len(f)} conversa(s): " + "; ".join(f"'{t[:40]}' -> {p}" for _, t, p in f)


if __name__ == "__main__":
    print(resumo())
