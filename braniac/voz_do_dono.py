# -*- coding: utf-8 -*-
"""VOZ DO DONO (27/10/2026): o bloco da Alma que guarda COMO o Dono fala e entrega isso ao Jarvis como um trecho de prompt ("guia de voz").
1) Estatisticas locais do que ele diz (tamanho das frases, giria, perguntas, pontuacao, emoji, tratamento): codigo comum, so neste PC.
2) De vez em quando a Alma pede ao CONSELHO (ChatGPT, via Braniac) que transforme uma descricao ABSTRATA desse jeito (numeros e tracos, nunca frases dele nem nomes)
   num guia curto de comportamento. O guia fica em data/alma/guia_de_voz.md e o roteador o anexa ao prompt de sistema do Jarvis.
Privacidade: nada do que o Dono escreveu sai deste PC; so a descricao abstrata vai ao conselho."""
import json
import re
import time
from collections import Counter

from .store import DATA

PASTA = DATA / "alma"
AMOSTRAS = PASTA / "estilo_amostras.jsonl"
GUIA = PASTA / "guia_de_voz.md"
ESTADO = PASTA / "voz_estado.json"
MIN_AMOSTRAS = 30
CADA_S = 7 * 86400
GIRIAS = ("né", "tá", "pra", "vc", "bora", "cara", "beleza", "blz", "valeu", "vlw", "opa", "então", "mano", "poha", "uai", "kkk", "rapidão", "rapido", "show", "massa")
FORMAL = ("por favor", "obrigado", "obrigada", "bom dia", "boa tarde", "boa noite", "agradeço", "gostaria")


def _amostras():
    out = []
    try:
        for l in AMOSTRAS.read_text(encoding="utf-8").splitlines():
            t = (json.loads(l).get("texto") or "").strip()
            if t and not re.search(r"AVALIACAO-AUTOMATICA|Conversa recente|RESULTADO DE FERRAMENTA", t):
                out.append(t)
    except (OSError, ValueError):
        pass
    return out


def estatisticas(textos=None):
    """Tracos do jeito de falar (so numeros e listas de palavras comuns). Pura quando recebe `textos`."""
    textos = _amostras() if textos is None else textos
    if not textos:
        return {}
    n = len(textos)
    palavras = [re.findall(r"[\wÀ-ÿ']+", t.lower()) for t in textos]
    media = sum(len(p) for p in palavras) / n
    baixo = " ".join(textos).lower()
    cont = Counter(w for p in palavras for w in p if w in GIRIAS)
    return {"amostras": n, "palavras_por_mensagem": round(media, 1),
            "pergunta": round(sum("?" in t for t in textos) / n, 2), "exclamacao": round(sum("!" in t for t in textos) / n, 2),
            "emoji": round(sum(bool(re.search("[\U0001F300-\U0001FAFF☀-➿]", t)) for t in textos) / n, 2),
            "comeca_minuscula": round(sum(t[:1].islower() for t in textos) / n, 2), "termina_sem_ponto": round(sum(not re.search(r"[.!?…]$", t) for t in textos) / n, 2),
            "girias": [w for w, _ in cont.most_common(6)], "formal": [f for f in FORMAL if f in baixo][:3],
            "imperativo": round(sum(bool(re.match(r"(?i)^(?:jarvis\W*)?(?:me\s+)?(?:manda|mande|faz|faça|cria|crie|abre|vê|ve|coloca|poe|bota|olha|pesquisa|mostra)\b", t)) for t in textos) / n, 2)}


def descricao_abstrata(e):
    """Texto neutro (sem frases dele) com os tracos, para o conselho transformar em guia. Pura."""
    if not e:
        return ""
    p = lambda v: f"{round(v * 100)}%"
    return (f"Pessoa que escreve mensagens de {e['palavras_por_mensagem']} palavras em média ({e['amostras']} mensagens analisadas). "
            f"{p(e['pergunta'])} das mensagens são perguntas, {p(e['exclamacao'])} têm exclamação, {p(e['emoji'])} têm emoji; "
            f"{p(e['comeca_minuscula'])} começam em minúscula e {p(e['termina_sem_ponto'])} terminam sem ponto final. "
            f"{p(e['imperativo'])} são pedidos diretos no imperativo. "
            + (f"Gírias/expressões frequentes: {', '.join(e['girias'])}. " if e["girias"] else "Quase não usa gírias. ")
            + (f"Fórmulas de cortesia usadas: {', '.join(e['formal'])}." if e["formal"] else "Raramente usa fórmulas de cortesia."))


def guia_local(e):
    """Regras de voz derivadas das estatisticas, sem IA (o minimo que ja ajuda o Jarvis)."""
    if not e or e["amostras"] < 8:
        return ""
    r = []
    r.append("frases curtas e diretas" if e["palavras_por_mensagem"] <= 14 else "frases de tamanho médio, explicando o necessário")
    r.append("tom informal e natural" if e["girias"] or e["comeca_minuscula"] > .4 else "tom educado e claro")
    if e["girias"]:
        r.append("pode usar expressões como " + ", ".join(e["girias"][:4]))
    if e["termina_sem_ponto"] > .6:
        r.append("sem ponto final nas frases curtas")
    if e["emoji"] < .1:
        r.append("quase sem emoji")
    if e["imperativo"] > .3:
        r.append("vai direto ao ponto: faz o que foi pedido e confirma em uma frase")
    return "Ao escrever ou responder em nome do Dono: " + "; ".join(r) + "."


def guia():
    """Trecho de prompt (<= 900 caracteres) que o roteador anexa ao sistema do Jarvis. '' se ainda nao ha o que dizer."""
    try:
        refinado = GUIA.read_text(encoding="utf-8").strip()
    except OSError:
        refinado = ""
    base = guia_local(estatisticas())
    return (refinado[:700] + ("\n" + base if base and not refinado else "")).strip()[:900] if (refinado or base) else ""


def _estado():
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def refinar(consultar, agora=None, forcar=False):
    """consultar(ia, pergunta) -> texto (jarvis.consultar_reuniao). No maximo 1x por semana e so com amostras suficientes. Devolve True se atualizou o guia."""
    agora = agora or time.time()
    e = estatisticas()
    est = _estado()
    if not forcar and (not e or e["amostras"] < MIN_AMOSTRAS or agora - est.get("ts", 0) < CADA_S):
        return False
    desc = descricao_abstrata(e)
    pergunta = ("Você é especialista em redação e persona de assistentes. Abaixo está uma descrição ESTATÍSTICA do jeito como uma pessoa escreve (sem nenhum texto dela). "
                "Escreva um GUIA DE VOZ para um assistente de IA responder e redigir mensagens do jeito dela: no máximo 8 regras curtas e práticas (tom, tamanho, abertura, "
                "fechamento, expressões, pontuação), em português do Brasil, sem inventar fatos sobre a pessoa. Responda só com as regras em lista.\n\nDESCRIÇÃO: " + desc)
    try:
        r = (consultar("chatgpt", pergunta) or "").strip()
    except Exception:
        return False
    if len(r) < 80 or r.lower().startswith("nao consegui") or "não consegui falar" in r.lower():
        return False
    PASTA.mkdir(parents=True, exist_ok=True)
    GUIA.write_text("Guia de voz do Dono (use ao responder a ele e ao redigir mensagens em nome dele):\n" + r[:1500], encoding="utf-8")
    est.update({"ts": agora, "amostras": e["amostras"]})
    ESTADO.write_text(json.dumps(est), encoding="utf-8")
    return True


if __name__ == "__main__":
    import sys
    e = estatisticas()
    print(json.dumps(e, ensure_ascii=False, indent=1))
    print(descricao_abstrata(e))
    if "--refinar" in sys.argv:
        from . import jarvis
        print("guia atualizado:", refinar(jarvis.consultar_reuniao, forcar=True))
    print("\nGUIA ATUAL:\n" + (guia() or "(vazio)"))
