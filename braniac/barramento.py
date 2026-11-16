# -*- coding: utf-8 -*-
"""BARRAMENTO DOS AGENTES (26/10/2026): como os agentes do Braniac conversam entre si. Caixa de mensagens local (data/agentes.db), 100% sem IA e sem rede.
Um agente POSTA uma mensagem para outro (de, para, tipo, texto, urgencia); o destinatario LE a sua caixa no proprio ciclo e marca como lida/respondida.
O barramento so entrega recados: NUNCA executa nada. Quem age continua sendo cada agente, dentro das suas travas (Compasso/Jarvis checam antes de enviar a alguem).
Tipos usados: dono_disse (Jarvis -> Alma), status (qualquer -> Compasso), alerta, pedido, resposta."""
import sqlite3
import threading
import time

from .store import DATA

DB = DATA / "agentes.db"
AGENTES = {"Jarvis", "Alma", "Compasso", "Correio", "Garimpeiro", "Forja", "Ilhéu", "Sultão", "Cofre", "Ada", "Cabo Tito", "Conselho", "Vaquinha", "Tino", "Valério", "Nando", "Claudinho", "Zelo"}
_lock = threading.Lock()


def _db():
    DATA.mkdir(exist_ok=True)
    c = sqlite3.connect(str(DB), check_same_thread=False)
    c.execute("CREATE TABLE IF NOT EXISTS msg(id INTEGER PRIMARY KEY, ts REAL, de TEXT, para TEXT, tipo TEXT, texto TEXT, urgencia INTEGER DEFAULT 0, lida INTEGER DEFAULT 0, resp_de INTEGER)")
    return c


def _do_registro():
    """Agentes criados depois (assuntos novos) tambem podem falar no barramento."""
    try:
        from . import assuntos
        extra = set()
        try:
            from . import empresa_compras, empresa_cortes, empresa_dev, empresa_inv, empresa_mkt, modulos
            if modulos.ativo("cortes_video"):
                extra |= set(empresa_cortes.nomes())   # Claquete, 5o andar
            if modulos.ativo("compras"):
                extra |= set(empresa_compras.nomes())   # Pechincha, 6o andar
            if modulos.ativo("programacao"):
                extra |= set(empresa_dev.nomes())   # 2o andar
            if modulos.ativo("marketing"):
                extra |= set(empresa_mkt.nomes())   # Fornalha, 3o andar
            if modulos.ativo("investimentos"):
                extra |= set(empresa_inv.nomes())   # Quantix, 4o andar
        except Exception:
            pass
        return {a["agente"] for a in assuntos.listar() if a["agente"]} | extra
    except Exception:
        return set()


def enviar(de, para, tipo, texto, urgencia=0, resp_de=None):
    """Posta um recado. Devolve o id. Remetente/destinatario desconhecidos sao recusados (ValueError)."""
    conhecidos = AGENTES | _do_registro()
    if de not in conhecidos or para not in conhecidos:
        raise ValueError(f"agente desconhecido: {de!r} -> {para!r}")
    with _lock:
        c = _db()
        cur = c.execute("INSERT INTO msg(ts,de,para,tipo,texto,urgencia,resp_de) VALUES(?,?,?,?,?,?,?)", (time.time(), de, para, tipo, str(texto)[:1500], int(urgencia), resp_de))
        c.commit()
        i = cur.lastrowid
        c.close()
    return i


def caixa(para, so_novas=True, n=20):
    """[{id, ts, de, tipo, texto, urgencia}] do mais antigo ao mais novo."""
    with _lock:
        c = _db()
        rows = c.execute("SELECT id,ts,de,tipo,texto,urgencia FROM msg WHERE para=?" + (" AND lida=0" if so_novas else "") + " ORDER BY id LIMIT ?", (para, n)).fetchall()
        c.close()
    return [dict(zip(("id", "ts", "de", "tipo", "texto", "urgencia"), r)) for r in rows]


def marcar_lida(i):
    with _lock:
        c = _db()
        c.execute("UPDATE msg SET lida=1 WHERE id=?", (i,))
        c.commit()
        c.close()


def responder(msg, de, texto, tipo="resposta", urgencia=0):
    """Responde a uma mensagem recebida (vai para quem enviou) e marca a original como lida."""
    marcar_lida(msg["id"])
    with _lock:
        c = _db()
        para = c.execute("SELECT de FROM msg WHERE id=?", (msg["id"],)).fetchone()[0]
        c.close()
    return enviar(de, para, tipo, texto, urgencia, resp_de=msg["id"])


def historico(n=50):
    """Conversa entre agentes (mais recentes por ultimo), para a tela e para o Dono ver o que eles combinam."""
    with _lock:
        c = _db()
        rows = c.execute("SELECT id,ts,de,para,tipo,texto,urgencia,lida FROM msg ORDER BY id DESC LIMIT ?", (n,)).fetchall()
        c.close()
    return [dict(zip(("id", "ts", "de", "para", "tipo", "texto", "urgencia", "lida"), r)) for r in reversed(rows)]
