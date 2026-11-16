# -*- coding: utf-8 -*-
"""Mede quantas respostas do Jarvis o Dono corrigiu (28/10/2026). Local, sem IA: conta correcoes explicitas ('nao foi isso que perguntei', 'nada a ver', 'errou')
na mensagem seguinte a uma resposta. A rotina semanal de treino usa isto para ver se a taxa de erro cai."""
import re
import sqlite3
import time

from .store import DATA

NL = chr(10) * 2
CORRECAO = re.compile(r"(?i)nada a ver|n[ãa]o,? (eu|era|é|foi|entendeu)|errou|seu cu|de novo|n[ãa]o entendeu|n[ãa]o foi isso|pra que desgra|viajou|n[ãa]o perguntei|n[ãa]o pedi")


def medir(dias=14):
    """(trocas, correcoes, [(fala do Dono, resposta anterior)]) do Dono com o Jarvis."""
    c = sqlite3.connect(str(DATA / "jarvis.db"))
    rows = c.execute("select direcao, texto from eventos where ts>? and contato like 'Dono%' and canal in ('whatsapp','conversa-jarvis') order by ts",
                     (time.time() - dias * 86400,)).fetchall()
    ant, trocas, erros = None, 0, []
    for d, t in rows:
        t = t.split(NL + "[Conversa recente")[0].split(NL + "[Projeto")[0]
        if d == "C":
            ant, trocas = t, trocas + 1
        elif d == "E" and ant and CORRECAO.search(t) and len(t) < 200:
            erros.append((t[:90], ant[:110]))
            ant = None
    return trocas, len(erros), erros
