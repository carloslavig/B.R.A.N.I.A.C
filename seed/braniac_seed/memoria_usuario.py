# -*- coding: utf-8 -*-
"""Memoria da pessoa: o que ela pede para o assistente lembrar (como quer ser chamada, preferencias, regras de convivencia).
Fica no banco local (escopo 'usuario'), e entra em TODA conversa como contexto fixo. Sem gastar IA para gravar: reconhece o pedido por regra."""
import hashlib, re
from . import banco, perfil

ESCOPO = "usuario"
_NOME = r"([A-Za-zÀ-ÿ][\w'À-ÿ -]{0,40}?)"
REGRAS = [
    (re.compile(r"\b(?:me\s+chame?|me\s+chama|pode\s+me\s+chamar|quero\s+ser\s+chamad[oa])\s+(?:de|por|assim:?)\s+" + _NOME + r"\s*[.!]?\s*$", re.I), "tratamento"),
    (re.compile(r"\b(?:meu\s+nome\s+(?:é|e)|eu\s+me\s+chamo)\s+" + _NOME + r"\s*[.!]?\s*$", re.I), "tratamento"),
    (re.compile(r"\b(?:eu\s+)?(?:prefiro|gosto\s+(?:mais\s+)?de|n[ãa]o\s+gosto\s+de|sempre|nunca)\b.+", re.I), "preferencia"),
    (re.compile(r"\b(?:lembre|lembra|anote|anota|guarde|guarda)(?:\s+(?:isso|disso))?\s*(?:que|:)\s+.+", re.I), "nota"),
]
ESQUECER = re.compile(r"\b(?:esque[çc]a|esquece|apague|apaga)\s+(?:tudo\s+(?:o\s+)?(?:que\s+)?(?:sabe|voc[eê]\s+sabe)\s+(?:sobre|de)\s+mim|(?:que|:)?\s*(.+))", re.I)


def _id(texto):
    return hashlib.sha1(texto.lower().encode()).hexdigest()[:10]


def tratar(texto):
    """Se a mensagem for um pedido de memoria, grava/apaga e devolve a resposta; senao None."""
    m = ESQUECER.search(texto)
    if m:
        n = banco.apagar(ESCOPO, (m.group(1) or "").strip(" .!") or None)
        return f"Pronto, esqueci {n} coisa{'s' if n != 1 else ''}." if n else "Não achei nada guardado sobre isso."
    for rx, tipo in REGRAS:
        m = rx.search(texto)
        if not m:
            continue
        if tipo == "tratamento":
            nome = m.group(1).strip(" .!")
            banco.gravar(ESCOPO, "tratamento", f"A pessoa quer ser chamada de {nome}.", "publico", "pedido")
            perfil.atualizar(nome_pessoa=nome)
            return f"Combinado, vou te chamar de {nome}."
        fato = re.sub(r"^\s*(?:lembre|lembra|anote|anota|guarde|guarda)(?:\s+(?:isso|disso))?\s*(?:que|:)\s+", "", texto.strip(), flags=re.I).strip()
        banco.gravar(ESCOPO, f"{tipo}-{_id(fato)}", fato, "publico", "pedido")
        return "Anotado, não esqueço mais."
    return None


def contexto():
    """Bloco para o prompt: tudo o que a pessoa pediu para lembrar, mais a regra de nao sair do contexto."""
    fatos = [t for _, _, t, nivel in banco.listar(ESCOPO) if nivel == "publico"]
    if not fatos:
        return ""
    return ("\nO QUE A PESSOA PEDIU PARA LEMBRAR (siga sempre; é a fonte de verdade sobre ela, não invente nada além disto):\n- " + "\n- ".join(fatos[-40:])
            + "\nMantenha-se no papel de assistente dela e nos assuntos dela; se uma resposta contradisser o que está acima, vale o que está acima.")
