# -*- coding: utf-8 -*-
"""Projetos e conversas (v0.7): cada conversa tem historico PROPRIO e o projeto pode ter instrucoes que valem em todas as conversas dele.
Assim os assuntos nao se misturam. Tudo fica no PC da pessoa (projetos.db na pasta de dados); arquivar so esconde, nada e apagado."""
import sqlite3
import time
from . import paths


def _con():
    c = sqlite3.connect(paths.arquivo("projetos.db"))
    c.executescript("""
        CREATE TABLE IF NOT EXISTS projetos(id INTEGER PRIMARY KEY, nome TEXT NOT NULL, instrucoes TEXT DEFAULT '', criado REAL);
        CREATE TABLE IF NOT EXISTS conversas(id INTEGER PRIMARY KEY, projeto INTEGER, titulo TEXT, criado REAL, atualizado REAL, arquivada INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS mensagens(id INTEGER PRIMARY KEY, conversa INTEGER, papel TEXT, texto TEXT, ts REAL);
    """)
    if not c.execute("SELECT 1 FROM projetos").fetchone():
        c.execute("INSERT INTO projetos(nome, instrucoes, criado) VALUES('Geral', '', ?)", (time.time(),))
        c.commit()
    return c


def estado():
    with _con() as c:
        p = [dict(zip(("id", "nome", "instrucoes"), r)) for r in c.execute("SELECT id, nome, instrucoes FROM projetos ORDER BY id")]
        v = [dict(zip(("id", "projeto", "titulo", "atualizado"), r))
             for r in c.execute("SELECT id, projeto, titulo, atualizado FROM conversas WHERE arquivada=0 ORDER BY atualizado DESC LIMIT 300")]
    return {"projetos": p, "conversas": v}


def _texto(v, n):
    v = str(v or "").strip()
    if not v or len(v) > n:
        raise ValueError(f"texto vazio ou maior que {n} caracteres")
    return v


def acao(d):
    a = d.get("acao")
    with _con() as c:
        if a == "criar_projeto":
            novo = c.execute("INSERT INTO projetos(nome, instrucoes, criado) VALUES(?,?,?)",
                             (_texto(d.get("nome"), 80), str(d.get("instrucoes") or "")[:4000], time.time())).lastrowid
        elif a == "editar_projeto":
            c.execute("UPDATE projetos SET nome=?, instrucoes=? WHERE id=?", (_texto(d.get("nome"), 80), str(d.get("instrucoes") or "")[:4000], int(d["id"])))
            novo = int(d["id"])
        elif a == "criar_conversa":
            agora = time.time()
            novo = c.execute("INSERT INTO conversas(projeto, titulo, criado, atualizado) VALUES(?,?,?,?)",
                             (int(d.get("projeto") or 1), str(d.get("titulo") or "Nova conversa")[:80], agora, agora)).lastrowid
        elif a == "renomear":
            c.execute("UPDATE conversas SET titulo=? WHERE id=?", (_texto(d.get("titulo"), 80), int(d["id"])))
            novo = int(d["id"])
        elif a == "mover":
            c.execute("UPDATE conversas SET projeto=? WHERE id=?", (int(d["projeto"]), int(d["id"])))
            novo = int(d["id"])
        elif a == "arquivar":
            c.execute("UPDATE conversas SET arquivada=1 WHERE id=?", (int(d["id"]),))
            novo = int(d["id"])
        else:
            raise ValueError("ação desconhecida")
    return {"novo": novo, **estado()}


def instrucoes(conversa):
    """(nome do projeto, instrucoes) da conversa, ou (None, '')."""
    with _con() as c:
        r = c.execute("SELECT p.nome, p.instrucoes FROM conversas v JOIN projetos p ON p.id=v.projeto WHERE v.id=?", (int(conversa),)).fetchone()
    return (r[0], r[1] or "") if r else (None, "")


def anotar(conversa, papel, texto):
    """Guarda a fala ('eu' ou 'ia') e da titulo a conversa nova a partir da primeira mensagem."""
    agora = time.time()
    with _con() as c:
        c.execute("INSERT INTO mensagens(conversa, papel, texto, ts) VALUES(?,?,?,?)", (int(conversa), papel, str(texto)[:8000], agora))
        c.execute("UPDATE conversas SET atualizado=? WHERE id=?", (agora, int(conversa)))
        if papel == "eu":
            c.execute("UPDATE conversas SET titulo=? WHERE id=? AND titulo='Nova conversa'", (" ".join(str(texto).split())[:60], int(conversa)))


def historico(conversa, n=20):
    with _con() as c:
        rows = c.execute("SELECT papel, texto FROM mensagens WHERE conversa=? ORDER BY id DESC LIMIT ?", (int(conversa), n)).fetchall()
    return list(reversed(rows))


def mensagens(conversa, n=300):
    return [{"papel": p, "texto": t} for p, t in historico(conversa, n)]
