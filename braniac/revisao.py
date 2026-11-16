# -*- coding: utf-8 -*-
"""Revisao das decisoes do atendimento ANTES de agirem (decisao do Dono: nada de 'decisao de merda' sair sem passar pelo Claude).

Um auditor barato e deterministico olha cada decisao (E enviar, I ignorar, A avisar, P perguntar) e procura os erros ja vistos:
  1. rotular/julgar a pessoa (trote, zoeira, golpe, mentiroso...);
  2. repetir o que ja foi dito a ela nas ultimas 24 h (mesma frase ou resposta quase igual);
  3. ignorar/so avisar quando a pessoa fez um PEDIDO (orcamento, pergunta, 'gostaria', 'quero'...).
Se achar algo, a decisao NAO sai: vai para o Claude (ao vivo se estiver presente no canal; senao um revisor de fundo com regras estritas).
Sem revisor disponivel => o Jarvis SEGURA (P) e avisa o Dono, em vez de mandar o que foi barrado.
"""
import re
from datetime import datetime
from . import canal, contexto, memoria
from .store import DATA

LOG = DATA / "revisoes.log"

JULGAMENTO = re.compile(r"\btrote\b|zoeira|golpe\b|golpista|mentiros[oa]|\btroll\b|palha[cç]ada|sacanagem|n[aã]o\s+leva\s+a\s+s[eé]rio", re.I)
PEDIDO = re.compile(r"\?|or[cç]amento|quanto\s+(?:custa|fica|[eé])|gostaria|\bquero\b|preciso|consegue|tem\s+como|d[aá]\s+pra|pode\s+(?:me|fazer|ver)|valor", re.I)
LIMIAR_REPETICAO = 0.55
NEUTRA = "Recebi sua mensagem! Vou conferir isso direitinho e já te retorno."   # resposta segura quando a decisao proposta e barrada e ninguem revisa


def _log(txt):
    DATA.mkdir(exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {txt}\n")


def _frases(txt):
    return {memoria._norm(f) for f in re.split(r"[.!?,;:]+", txt or "") if len(memoria._norm(f)) > 22}


def repete(texto, saidas):
    """True se o texto repete (mesma frase ou resposta quase igual) algo que ja dissemos a esta pessoa."""
    novas = _frases(texto)
    pal = memoria._palavras(texto)
    for s in saidas:
        if novas & _frases(s):                      # a mesma frase de novo (ex.: a mesma observacao sobre a data)
            return True
        outras = memoria._palavras(s)
        if pal and outras and len(pal & outras) / len(pal | outras) >= LIMIAR_REPETICAO:
            return True
    return False


def auditar(it, cod, texto, saidas=None):
    """Lista de problemas da decisao (vazia = pode seguir)."""
    problemas = []
    if JULGAMENTO.search(re.sub(r"https?://\S+|www\.\S+", " ", texto or "")):  # endereco nao conta (validar_resposta ja cuida de links)
        problemas.append("rotula/julga a pessoa (trote, zoeira, golpe...): proibido; trate como cliente real, com educação")
    if cod == "E":
        saidas = memoria.saidas_recentes(it["nome"]) if saidas is None else saidas
        if repete(texto, saidas):
            problemas.append("repete o que já foi dito a esta pessoa nas últimas 24 h (não volte a falar do mesmo ponto)")
    if cod in ("A", "I") and PEDIDO.search(" ".join(it.get("msgs", []))) and not contexto.nao_responder(it["nome"]):
        problemas.append("a pessoa fez um PEDIDO/pergunta e a decisão não responde nada (responda o que dá e peça o dado que falta)")
    return problemas


def formatar_revisao(id_, it, flags, cod, texto, problemas):
    base = canal.formatar_pergunta(id_, it["nome"], flags, it["msgs"], it.get("ctx"))
    return ("V" + base[1:] + "|PROPOSTA=" + canal.limpar(f"{cod}:{texto}", 220) + "|PROBLEMAS=" + canal.limpar("; ".join(problemas), 260))


def revisar(it, flags, cod, texto, problemas, espera_s=150):
    """Pede a revisao. Devolve (cod, texto) revisado ou None se ninguem conseguiu revisar."""
    import uuid
    id_ = uuid.uuid4().hex[:6]
    linha = formatar_revisao(id_, it, flags, cod, texto, problemas)
    if canal.presente():                            # o Claude esta aqui: pergunta a ele
        res = canal._postar_e_esperar(id_, linha, espera_s)
        if res:
            return res[1], res[2]
    mem = memoria.contexto_para_decidir(it["nome"], " ".join(it.get("msgs", [])))
    res = contexto.decidir_claude(linha, memoria_txt=mem)   # revisor de fundo, com a regra de REVISAO no prompt
    return (res[1], res[2]) if res else None


def decidir_com_revisao(it, flags, dec, espera_s=150):
    """Aplica auditoria + revisao a uma decisao (cod, texto). Devolve (cod, texto, anotacao) ; anotacao '' se nada mudou."""
    cod, texto = dec
    problemas = auditar(it, cod, texto)
    if not problemas:
        return cod, texto, ""
    rev = revisar(it, flags, cod, texto, problemas, espera_s)
    if rev:
        c2, t2 = rev
        if not auditar(it, c2, t2) or c2 in ("P", "A") and not JULGAMENTO.search(t2 or ""):
            _log(f"{it['nome']} | REVISADA {cod}->{c2} | motivo={problemas[0][:70]!r} | nova={t2[:100]!r}")
            return c2, t2, "revisada"
    # sem revisor, ou a revisao ainda tem problema: o proposto NAO sai. Autonomia total: o Jarvis se vira sozinho, sem perguntar ao Dono.
    if any("repete" in p for p in problemas):                 # ja dissemos isso: melhor calar do que repetir
        _log(f"{it['nome']} | AUTO-IGNORADA {cod} | repetiria o que ja foi dito | proposta={texto[:100]!r}")
        return "I", "", "autoignorada"
    if NEUTRA in memoria.saidas_recentes(it["nome"]):          # a mensagem neutra ja foi dada: nao repete
        _log(f"{it['nome']} | AUTO-IGNORADA {cod} | neutra ja enviada | proposta={texto[:100]!r}")
        return "I", "", "autoignorada"
    _log(f"{it['nome']} | NEUTRA no lugar de {cod} | {problemas[0][:90]!r} | proposta={texto[:100]!r}")
    return "E", NEUTRA, "neutra"
