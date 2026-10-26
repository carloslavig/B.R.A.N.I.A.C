# -*- coding: utf-8 -*-
"""Módulo FINANCEIRO (agente 'Moeda'): controle pessoal de gastos, receitas e metas, 100% local (SQLite em modulos/financeiro.db).
LIMITES DE SEGURANÇA: nunca pede nem guarda número de cartão, senha, CPF, chave Pix ou dados de conta; não acessa banco, não paga nem transfere nada;
só registra o que a pessoa DISSE. Não dá recomendação de investimento. Todo lançamento pode ser desfeito."""
import re
import sqlite3
from datetime import date, datetime, timedelta

from . import modulos, paths

SENSIVEL = re.compile(r"(?i)senha|password|cvv|cpf|\bpix\b.*chave|chave pix|\b(?:\d[ -]?){13,19}\b|ag[eê]ncia|n[uú]mero da conta|token")


def _con():
    p = paths.arquivo("modulos")
    p.mkdir(exist_ok=True)
    c = sqlite3.connect(str(p / "financeiro.db"), check_same_thread=False)
    c.executescript("""
        CREATE TABLE IF NOT EXISTS lancamentos(id INTEGER PRIMARY KEY, ts REAL, data TEXT, tipo TEXT, centavos INTEGER, categoria TEXT, descricao TEXT);
        CREATE TABLE IF NOT EXISTS metas(id INTEGER PRIMARY KEY, nome TEXT UNIQUE, centavos INTEGER, prazo TEXT);""")
    return c


def valor_br(v):
    """'R$ 1.234,56' / '35,5' / 35.5 / 40 -> centavos (int). ValueError se não for dinheiro."""
    if isinstance(v, (int, float)):
        cent = round(float(v) * 100)
    else:
        t = re.sub(r"[^\d.,]", "", str(v or ""))
        if not t:
            raise ValueError("faltou o valor")
        if "," in t:
            t = t.replace(".", "").replace(",", ".")
        elif t.count(".") > 1 or (t.count(".") == 1 and len(t.split(".")[1]) == 3):
            t = t.replace(".", "")
        cent = round(float(t) * 100)
    if not 0 < cent < 10 ** 10:
        raise ValueError("valor fora do possível")
    return int(cent)


def _brl(c):
    return f"R$ {c / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def registrar(args):
    texto = " ".join(str(args.get(k, "")) for k in ("descricao", "categoria", "valor"))
    if SENSIVEL.search(texto):
        raise ValueError("não guardo número de cartão, senha, CPF ou dados de conta: conte só o gasto (valor e o que foi).")
    tipo = "receita" if str(args.get("tipo", "gasto")).lower().startswith(("rec", "ganh", "entr")) else "gasto"
    cent = valor_br(args.get("valor"))
    data = str(args.get("data") or date.today().isoformat())[:10]
    try:
        datetime.strptime(data, "%Y-%m-%d")
    except ValueError:
        data = date.today().isoformat()
    cat = (str(args.get("categoria") or "outros").strip().lower() or "outros")[:30]
    with _con() as c:
        c.execute("INSERT INTO lancamentos(ts,data,tipo,centavos,categoria,descricao) VALUES(?,?,?,?,?,?)",
                  (datetime.now().timestamp(), data, tipo, cent, cat, str(args.get("descricao") or "")[:120]))
    return f"Anotado: {tipo} de {_brl(cent)} em {cat} ({data})."


def desfazer(_args):
    with _con() as c:
        r = c.execute("SELECT id,tipo,centavos,categoria FROM lancamentos ORDER BY id DESC LIMIT 1").fetchone()
        if not r:
            return "Não há lançamento para desfazer."
        c.execute("DELETE FROM lancamentos WHERE id=?", (r[0],))
    return f"Desfeito: {r[1]} de {_brl(r[2])} em {r[3]}."


def resumo(args):
    per = str(args.get("periodo") or "mes").lower()
    hoje = date.today()
    ini = {"hoje": hoje, "semana": hoje - timedelta(days=6)}.get(per, hoje.replace(day=1))
    cat = str(args.get("categoria") or "").strip().lower()
    with _con() as c:
        rows = c.execute("SELECT tipo,categoria,SUM(centavos) FROM lancamentos WHERE data>=? AND (?='' OR categoria=?) GROUP BY tipo,categoria",
                         (ini.isoformat(), cat, cat)).fetchall()
    g = {k: v for t, k, v in rows if t == "gasto"}
    rec = sum(v for t, _, v in rows if t == "receita")
    if not rows:
        return f"Nenhum lançamento desde {ini.strftime('%d/%m')}."
    top = ", ".join(f"{k} {_brl(v)}" for k, v in sorted(g.items(), key=lambda kv: -kv[1])[:5])
    return (f"Desde {ini.strftime('%d/%m')}: gastos {_brl(sum(g.values()))}" + (f" ({top})" if top else "") + f"; receitas {_brl(rec)}; saldo {_brl(rec - sum(g.values()))}.")


def meta(args):
    nome = str(args.get("nome") or "").strip()[:60]
    if not nome:
        raise ValueError("diga o nome da meta")
    cent = valor_br(args.get("valor"))
    with _con() as c:
        c.execute("INSERT INTO metas(nome,centavos,prazo) VALUES(?,?,?) ON CONFLICT(nome) DO UPDATE SET centavos=excluded.centavos, prazo=excluded.prazo",
                  (nome, cent, str(args.get("prazo") or "")[:10]))
        total = c.execute("SELECT COALESCE(SUM(centavos),0) FROM lancamentos WHERE tipo='receita'").fetchone()[0]
    return f"Meta '{nome}': {_brl(cent)}" + (f" até {args['prazo']}" if args.get("prazo") else "") + f". Receitas registradas até agora: {_brl(total)}."


modulos.registrar_ferramenta("financeiro_registrar", registrar, 'anota gasto ou receita. args: {"tipo":"gasto|receita","valor":"35,50","categoria":"mercado","descricao":"...","data":"AAAA-MM-DD opcional"}')
modulos.registrar_ferramenta("financeiro_resumo", resumo, 'resume gastos/receitas. args: {"periodo":"hoje|semana|mes","categoria":"opcional"}')
modulos.registrar_ferramenta("financeiro_meta", meta, 'define uma meta de economia. args: {"nome":"viagem","valor":"3000","prazo":"AAAA-MM-DD opcional"}')
modulos.registrar_ferramenta("financeiro_desfazer", desfazer, "desfaz o ÚLTIMO lançamento. args: {}")
