# -*- coding: utf-8 -*-
"""Tratamento obrigatorio (decisao do Dono): a Parceira Lima e SEMPRE 'Parceira'. Nunca 'Parceira', nem 'Parceira' sozinho.
Aplicado em toda saida do Jarvis (mensagens de WhatsApp e fala), para valer mesmo quando a IA esquece a regra."""
import re

_JA_TRATADA = re.compile(r"\bDeusa\s+Parceira(?:[ií]na)?(?:\s+Lima)?\b", re.I)
_CITACAO = re.compile(r"(?:cham\w*|dizer|dizendo|falei|falar|escrev\w*|trat\w*)\s+(?:\w+\s+){0,3}(?:de|como)\s+$", re.I)
_NOME = re.compile(r"\bJana[ií]na(?:\s+Lima)?\b|\bJana\b", re.I)


_MAE = re.compile(r"\b(?:(?:dona|d\.|sra\.?|senhora)\s+)?(?:mainha|M[aá]rcia)\b", re.I)


def _tia_mae(texto):
    """A mae do Dono e SEMPRE 'Mae' (nunca 'mainha', 'dona Mae' ou 'Mae' sozinho)."""
    def troca(m):
        antes = texto[max(0, m.start() - 4):m.start()].lower()
        if antes.endswith("tia "):
            return m.group(0)
        return "Mãe"
    return _MAE.sub(troca, texto)


def corrigir(texto):
    """Troca 'Parceira', 'Parceira Lima' e 'Parceira' por 'Parceira' (sem duplicar o 'Deusa')."""
    if not texto:
        return texto
    texto = _tia_mae(texto)
    texto = _JA_TRATADA.sub("Parceira", texto)          # normaliza o que ja estava tratado ('Deusa Parceira', 'parceira lima')
    partes, ultimo = [], 0
    for m in _NOME.finditer(texto):
        inicio = max(0, m.start() - 6)
        if texto[inicio:m.start()].lower().endswith("deusa "):
            continue                                       # ja vem depois de 'Deusa '
        if _CITACAO.search(texto[max(0, m.start() - 40):m.start()]):
            continue                                       # 'chamado de Parceira' (retratacao): o erro citado nao pode ser trocado
        partes.append(texto[ultimo:m.start()])
        partes.append("Parceira")
        ultimo = m.end()
    partes.append(texto[ultimo:])
    return "".join(partes)


_SOLO = re.compile(r"(^|[,.!?;:]\s*)(?:gostos[oa]|querid[oa]|amor|lind[oa]|bonit[oa]|beb[eê]|gat[oa]|del[ií]cia|tes[aã]o|nen[eê]m|fofo|fofinho|princ[ei]p[ei]?)(?=\s*[,.!?;:]|\s*$)", re.I)
_MEU = re.compile(r"\b(?:meu|minha)\s+(?:bem|amor|rei|vida|beb[eê]|cora[cç][aã]o|gostos[oa]|querid[oa]|lind[oa]|princ[ei]p[ei]?)\b", re.I)


def alma_terceiros(texto):
    """Regra do Dono (16/11): a Alma, falando com a Parceira, a Mae ou qualquer outra pessoa, chama o Dono no maximo de Dono, Chefe, chefe ou senhor Dono.
    Apelidos intimos (querido, meu bem, meu amor, gostoso...) viram 'Chefe', mesmo se o modelo errar. Com o proprio Dono ela fala como quiser (esta funcao nao roda)."""
    if not texto:
        return texto
    t = _MEU.sub("Chefe", texto)
    return _SOLO.sub(lambda m: m.group(1) + "Chefe", t)
