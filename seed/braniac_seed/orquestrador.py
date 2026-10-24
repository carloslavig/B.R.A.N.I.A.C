# -*- coding: utf-8 -*-
"""ORQUESTRADOR DE IAs (v0.7): para tarefa grande ou com varias partes, uma IA divide o trabalho em ate 3 partes, cada parte vai para uma IA
DIFERENTE das chaves que a pessoa conectou (em paralelo) e uma IA junta tudo numa resposta so. Com uma chave so, faz em sequencia na mesma IA.
So vai para as IAs o texto da tarefa (nunca arquivos, senhas ou dados do PC)."""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from . import cofre, llm

MAX_PARTES = 3


def disponiveis():
    """Provedores com chave conectada (na ordem de preferencia do llm)."""
    out = []
    for p in llm.OPENAI:
        try:
            if cofre.ler(p):
                out.append(p)
        except cofre.CofreErro:
            pass
    return out


def _partes(tarefa, responder):
    bruto, _ = responder(f"Tarefa: {tarefa}",
                         sistema=f"Divida a tarefa em no maximo {MAX_PARTES} partes independentes que possam ser feitas em paralelo. "
                                 'Responda SO um JSON: {"partes": ["...", "..."]}. Se a tarefa for simples, devolva uma parte so.')
    try:
        partes = json.loads(re.search(r"\{.*\}", bruto, re.S).group(0), strict=False)["partes"]
        partes = [str(p).strip() for p in partes if str(p).strip()][:MAX_PARTES]
    except (AttributeError, ValueError, KeyError, TypeError):
        partes = []
    return partes or [tarefa]


def orquestrar(tarefa, responder=None, provedores=None):
    """Devolve {'resposta', 'partes': [(parte, provedor)]}. responder(prompt, sistema, chaves) permite testar sem internet."""
    tarefa = " ".join(str(tarefa or "").split())
    if len(tarefa) < 8:
        raise ValueError("descreva a tarefa com um pouco mais de detalhe")
    responder = responder or (lambda prompt, sistema="", chaves=None: llm.responder(prompt, sistema=sistema, chaves=chaves))
    provs = provedores if provedores is not None else disponiveis()
    partes = _partes(tarefa, responder)

    def fazer(i_parte):
        i, parte = i_parte
        chaves = [provs[i % len(provs)]] if provs else None   # cada parte numa IA diferente; sem chave: IA local
        txt, quem = responder(f"Tarefa geral: {tarefa}\nSua parte: {parte}", sistema="Faca SO a sua parte, em portugues do Brasil, de forma objetiva.", chaves=chaves)
        return parte, quem, txt

    with ThreadPoolExecutor(max_workers=MAX_PARTES) as ex:
        feitos = list(ex.map(fazer, enumerate(partes)))
    if len(feitos) == 1:
        return {"resposta": feitos[0][2], "partes": [(feitos[0][0], feitos[0][1])]}
    juntar = "\n\n".join(f"[Parte {i + 1} - {quem}] {parte}\n{txt}" for i, (parte, quem, txt) in enumerate(feitos))
    final, _ = responder(f"Tarefa: {tarefa}\n\nResultados das partes:\n{juntar}",
                         sistema="Junte os resultados numa resposta unica, clara e sem repeticao, em portugues do Brasil. Nao invente nada que nao esteja nas partes.")
    return {"resposta": final, "partes": [(p, q) for p, q, _ in feitos]}
