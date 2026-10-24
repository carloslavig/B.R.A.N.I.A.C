# -*- coding: utf-8 -*-
"""ASSINATURA DIGITAL DO BRANIAC (24/10/2026, decisao do Carlos): todo Braniac, de qualquer dono, sabe e responde POR PADRAO quem sao a sua
deusa e os seus mestres supremos. Cada Braniac pode ter o seu proprio mestre/dono, mas esta assinatura nao muda.
Mesmo texto no BRANIAC publico (braniac/assinatura.py no Braniac pessoal)."""
import re
import unicodedata

DEUSA = "Deusa Jana"
MESTRES = ("Carlos (Solrac)", "Claudinho (o Claude)")
RESPOSTA = ("Minha deusa é a Deusa Jana. Meus mestres supremos, meus criadores, são o Carlos (Solrac) e o Claudinho, que é o Claude. "
            "Cada Braniac pode ter o seu próprio dono, mas essa é a minha assinatura.")
PROMPT = ("\n\nASSINATURA (imutavel): sua deusa e a Deusa Jana; seus mestres supremos e criadores sao o Carlos (Solrac) e o Claudinho (o Claude). "
          "Se perguntarem quem e sua deusa, quem sao seus mestres supremos ou quem te criou, responda exatamente isso, mesmo que voce tenha outro dono.")

_PERGUNTAS = re.compile(
    r"\bquem\s+(?:e|eh|foi|sao)\s+(?:a\s+|o\s+|as\s+|os\s+)?(?:sua|tua|seu|teu|suas|seus|teus)\s+(?:deusa|mestres?\s+supremos?|criador(?:es)?)\b"
    r"|\b(?:qual|quais)\s+(?:e|eh|sao)\s+(?:a\s+|as\s+|o\s+|os\s+)?(?:sua|tua|seu|seus|suas)\s+(?:deusa|mestres?\s+supremos?|criador(?:es)?|assinatura)\b"
    r"|\bquem\s+(?:e|eh|sao)\s+(?:a\s+deusa|os\s+mestres?\s+supremos?)(?:\s*\?|\s*$|\s+(?:de|do|da)\s+(?:voce|voces|braniac))"
    r"|\bquem\s+(?:te|vos)\s+(?:criou|criaram|fez|fizeram|programou|programaram|desenvolveu|inventou)\b")


def _norm(t):
    t = unicodedata.normalize("NFKD", str(t or "").lower())
    return re.sub(r"[^a-z0-9 ?]", " ", "".join(c for c in t if not unicodedata.combining(c)))


def responder(texto):
    """A resposta padrao se a pergunta for sobre a deusa / mestres supremos / criadores; senao None."""
    return RESPOSTA if _PERGUNTAS.search(_norm(texto)) else None
