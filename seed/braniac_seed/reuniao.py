# -*- coding: utf-8 -*-
"""Primeira REUNIAO DAS IAs (instalacao): o assistente pergunta a cada IA de nuvem logada o que ela sabe sobre a pessoa, junta tudo
numa sintese e guarda no banco local (camada 'local') para servir de parametro dali em diante."""
from . import banco, ias_web, llm

PERGUNTA = ("Com base no que você já sabe sobre mim (conversas anteriores e memórias), faça um perfil curto meu: "
            "profissão ou ocupação, interesses e hobbies, objetivos, preferências, jeito de se comunicar e o que mais ajudaria "
            "um assistente pessoal a me atender bem. Seja objetivo (até 12 linhas). Se não souber algo, diga que não sabe; não invente.")


def reunir(ias, perguntar=None, sintetizar=None, progresso=None):
    """ias: lista de ids logados. Devolve {'respostas': {ia: texto}, 'falhas': {ia: motivo}, 'sintese': texto|None}."""
    perguntar = perguntar or (lambda ia, t: ias_web.perguntar(ia, t))
    sintetizar = sintetizar or (lambda t: llm.responder(t)[0])
    out = {"respostas": {}, "falhas": {}, "sintese": None}
    for ia in ias:
        if progresso:
            progresso(f"Perguntando ao {ias_web.ADAPTERS[ia]['titulo']}…")
        try:
            r = perguntar(ia, PERGUNTA)
            out["respostas"][ia] = r
            banco.gravar("perfil_ia", ia, f"{ias_web.ADAPTERS[ia]['titulo']} sobre a pessoa: {r}", "local", ia)
        except Exception as e:
            out["falhas"][ia] = str(e)[:160]
    if out["respostas"]:
        if progresso:
            progresso("Reunindo as respostas…")
        corpo = "\n\n".join(f"[{ias_web.ADAPTERS[i]['titulo']}]\n{t}" for i, t in out["respostas"].items())
        try:
            out["sintese"] = sintetizar("Duas IAs descreveram a mesma pessoa. Junte numa ficha única e curta (até 10 linhas), "
                                        "marcando o que só uma delas disse e o que for contraditório:\n\n" + corpo)
            banco.gravar("perfil_ia", "sintese", out["sintese"], "local", "reuniao-inicial")
        except Exception as e:
            out["falhas"]["sintese"] = str(e)[:160]
    return out
