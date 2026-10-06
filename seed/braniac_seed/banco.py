# -*- coding: utf-8 -*-
"""Banco LOCAL da pessoa (SQLite em %LOCALAPPDATA%\\BRANIAC\\banco.db): fonte unica de contexto para TODAS as IAs.
Duas camadas: 'publico' (pode ir a qualquer IA) e 'local' (so Ollama/IA local; nunca IA online). Nada disto sobe ao repositorio."""
import sqlite3, threading, time
from . import paths

_lock = threading.RLock()


def _con():
    c = sqlite3.connect(str(paths.arquivo("banco.db")), check_same_thread=False)
    c.execute("CREATE TABLE IF NOT EXISTS fatos(id INTEGER PRIMARY KEY, escopo TEXT, chave TEXT, texto TEXT, nivel TEXT DEFAULT 'local', "
              "fonte TEXT, ts REAL, UNIQUE(escopo, chave))")
    return c


def gravar(escopo, chave, texto, nivel="local", fonte="instalacao"):
    texto = (texto or "").strip()
    if not texto:
        return False
    with _lock:
        c = _con()
        c.execute("INSERT INTO fatos(escopo,chave,texto,nivel,fonte,ts) VALUES(?,?,?,?,?,?) ON CONFLICT(escopo,chave) DO UPDATE SET "
                  "texto=excluded.texto, nivel=excluded.nivel, fonte=excluded.fonte, ts=excluded.ts",
                  (escopo, chave[:120], texto, nivel if nivel in ("publico", "local") else "local", fonte, time.time()))
        c.commit()
        c.close()
    return True


def listar(escopo=None, nivel=None):
    with _lock:
        c = _con()
        sql, args = "SELECT escopo, chave, texto, nivel FROM fatos WHERE 1=1", []
        if escopo:
            sql += " AND escopo=?"
            args.append(escopo)
        if nivel:
            sql += " AND nivel=?"
            args.append(nivel)
        rows = c.execute(sql + " ORDER BY ts", args).fetchall()
        c.close()
    return rows
