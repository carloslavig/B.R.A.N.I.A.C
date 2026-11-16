# -*- coding: utf-8 -*-
"""Historico por conversa, cooldown de provedores e contagem de uso (SQLite)."""
import sqlite3, threading, time
from datetime import date
from pathlib import Path

DATA = Path(__file__).parent / "data"


class _BancoComLock:
    """sqlite3 compartilhado entre threads: serializa execute+commit."""
    def __init__(self, conn):
        self.conn, self.lock = conn, threading.RLock()

    def execute(self, *a):
        with self.lock:
            return self.conn.execute(*a)

    def executescript(self, *a):
        with self.lock:
            return self.conn.executescript(*a)

    def commit(self):
        with self.lock:
            self.conn.commit()


class Store:
    def __init__(self, path=None):
        DATA.mkdir(exist_ok=True)
        self.db = _BancoComLock(sqlite3.connect(str(path or DATA / "braniac.db"), check_same_thread=False))
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS msgs(
                id INTEGER PRIMARY KEY, conv TEXT, role TEXT, content TEXT,
                provider TEXT, ts REAL);
            CREATE TABLE IF NOT EXISTS estado(
                nome TEXT PRIMARY KEY, ate REAL, erro TEXT);
            CREATE TABLE IF NOT EXISTS uso(
                dia TEXT, nome TEXT, n INTEGER, PRIMARY KEY(dia, nome));
        """)

    def add_msg(self, conv, role, content, provider=None):
        self.db.execute("INSERT INTO msgs(conv,role,content,provider,ts) VALUES(?,?,?,?,?)",
                        (conv, role, content, provider, time.time()))
        self.db.commit()

    def historico(self, conv, n):
        rows = self.db.execute(
            "SELECT role, content FROM msgs WHERE conv=? ORDER BY id DESC LIMIT ?", (conv, n)).fetchall()
        return [{"role": r, "content": c} for r, c in reversed(rows)]

    def cooldown(self, nome):
        r = self.db.execute("SELECT ate FROM estado WHERE nome=?", (nome,)).fetchone()
        return max(0.0, r[0] - time.time()) if r and r[0] is not None else 0.0      # 'ate' vazio (linha antiga/corrompida) = sem espera

    def set_cooldown(self, nome, segundos, erro=""):
        self.db.execute("INSERT OR REPLACE INTO estado VALUES(?,?,?)",
                        (nome, time.time() + segundos, erro[:200]))
        self.db.commit()

    def clear_cooldown(self, nome):
        self.db.execute("DELETE FROM estado WHERE nome=?", (nome,))
        self.db.commit()

    def uso_hoje(self, nome):
        r = self.db.execute("SELECT n FROM uso WHERE dia=? AND nome=?",
                            (date.today().isoformat(), nome)).fetchone()
        return r[0] if r else 0

    def add_uso(self, nome):
        self.db.execute(
            "INSERT INTO uso VALUES(?,?,1) ON CONFLICT(dia,nome) DO UPDATE SET n=n+1",
            (date.today().isoformat(), nome))
        self.db.commit()

    def erro(self, nome):
        r = self.db.execute("SELECT erro FROM estado WHERE nome=?", (nome,)).fetchone()
        return r[0] if r else ""
