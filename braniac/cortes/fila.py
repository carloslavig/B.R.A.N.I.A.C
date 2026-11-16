# -*- coding: utf-8 -*-
"""Fila dos cortes (SQLite em data/cortes/cortes.db): detectado -> renderizado -> aprovado/rejeitado -> publicado."""
import sqlite3, threading, time
from . import config

_LOCK = threading.RLock()
ESQUEMA = """
CREATE TABLE IF NOT EXISTS cortes(
  id INTEGER PRIMARY KEY AUTOINCREMENT, canal TEXT, origem TEXT, fonte TEXT, inicio REAL, fim REAL,
  score REAL, motivo TEXT, arquivo TEXT, transcricao TEXT, titulo TEXT, descricao TEXT, hashtags TEXT,
  status TEXT DEFAULT 'renderizado', youtube_id TEXT, tiktok TEXT, erro TEXT, criado REAL, atualizado REAL);
CREATE TABLE IF NOT EXISTS vistos(chave TEXT PRIMARY KEY, quando REAL);
"""


def _con():
    config.PASTA.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(config.PASTA / "cortes.db", timeout=30)
    c.row_factory = sqlite3.Row
    c.executescript(ESQUEMA)
    if "perfil" not in {r[1] for r in c.execute("PRAGMA table_info(cortes)")}:  # bancos antigos: perfil vazio = canal PT
        c.execute("ALTER TABLE cortes ADD COLUMN perfil TEXT DEFAULT ''")
    if "agendado" not in {r[1] for r in c.execute("PRAGMA table_info(cortes)")}:  # horario de publicacao no YouTube
        c.execute("ALTER TABLE cortes ADD COLUMN agendado REAL")
    return c


def ja_visto(chave):
    with _LOCK, _con() as c:
        return c.execute("SELECT 1 FROM vistos WHERE chave=?", (chave,)).fetchone() is not None


def marcar_visto(chave):
    with _LOCK, _con() as c:
        c.execute("INSERT OR IGNORE INTO vistos VALUES(?,?)", (chave, time.time()))


def adicionar(**campos):
    campos.setdefault("status", "renderizado")
    campos["criado"] = campos["atualizado"] = time.time()
    with _LOCK, _con() as c:
        cols = ",".join(campos)
        cur = c.execute(f"INSERT INTO cortes({cols}) VALUES({','.join('?' * len(campos))})", tuple(campos.values()))
        return cur.lastrowid


def atualizar(id_, **campos):
    campos["atualizado"] = time.time()
    with _LOCK, _con() as c:
        c.execute(f"UPDATE cortes SET {','.join(k + '=?' for k in campos)} WHERE id=?", (*campos.values(), id_))


def pegar(id_):
    with _LOCK, _con() as c:
        r = c.execute("SELECT * FROM cortes WHERE id=?", (id_,)).fetchone()
        return dict(r) if r else None


def listar(status=None, limite=30):
    with _LOCK, _con() as c:
        if status:
            rs = c.execute("SELECT * FROM cortes WHERE status=? ORDER BY id DESC LIMIT ?", (status, limite))
        else:
            rs = c.execute("SELECT * FROM cortes ORDER BY id DESC LIMIT ?", (limite,))
        return [dict(r) for r in rs]


def publicados_hoje(perfil=""):
    inicio = time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, -1))
    with _LOCK, _con() as c:
        return c.execute("SELECT COUNT(*) FROM cortes WHERE status='publicado' AND atualizado>=? AND COALESCE(perfil,'')=?",
                         (inicio, perfil or "")).fetchone()[0]


def horarios_ocupados(perfil=""):
    with _LOCK, _con() as c:
        return {r[0] for r in c.execute("SELECT agendado FROM cortes WHERE status='publicado' AND agendado IS NOT NULL "
                                         "AND COALESCE(perfil,'')=?", (perfil or "",))}


def agenda(perfil="", desde=0):
    with _LOCK, _con() as c:
        return [dict(r) for r in c.execute("SELECT * FROM cortes WHERE status='publicado' AND agendado>=? AND COALESCE(perfil,'')=? "
                                            "ORDER BY agendado", (desde, perfil or ""))]


def estoque(perfil=""):
    """Cortes aprovados que ainda nao subiram para o YouTube."""
    with _LOCK, _con() as c:
        return c.execute("SELECT COUNT(*) FROM cortes WHERE status='aprovado' AND COALESCE(perfil,'')=?", (perfil or "",)).fetchone()[0]


def resumo():
    with _LOCK, _con() as c:
        rs = c.execute("SELECT status, COUNT(*) n FROM cortes GROUP BY status").fetchall()
    return {r["status"]: r["n"] for r in rs}
