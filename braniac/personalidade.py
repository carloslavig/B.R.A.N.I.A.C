# -*- coding: utf-8 -*-
"""PERSONALIDADE DO JARVIS (04/11/2026): botoes de 0 a 10 (empatia, humor, formalidade, objetividade, franqueza, proatividade) que o Dono ajusta
conversando ('aumenta a empatia', 'menos humor', 'formalidade em 8', 'volta ao normal'). 5 = neutro (nada e acrescentado ao prompt).
O ajuste e uma frase deterministica (sem IA); o efeito entra no prompt via `bloco()` (router._voz). Vale na conversa com o Dono: com clientes/hospedes
o tom profissional das regras continua mandando."""
import json
import re

from .store import DATA

ARQ = DATA / "personalidade.json"
PADRAO = 5
PASSO = 2
TRACOS = {
    "empatia": ("empatia|empatic\\w*|carinho\\w*|acolhe\\w*",
                ["frio e tecnico: nao comente sentimentos, va direto ao ponto", "pouco emotivo: so reconheca sentimentos se ele os mencionar",
                 "acolhedor: reconheca como ele se sente antes de resolver", "muito empatico e carinhoso: acolha, valide o que ele sente e use palavras de apoio"]),
    "humor": ("humor|engracad\\w*|piada\\w*|brincalh\\w*|divertid\\w*",
              ["serio: sem piadas nem brincadeiras", "sobrio: so uma leveza rara, nunca piada",
               "bem-humorado: pode soltar uma brincadeira leve quando couber", "muito engracado: use humor e ironia leve com frequencia, sem exagerar nem ofender"]),
    "formalidade": ("formalidade|formal",
                    ["bem informal: girias leves, tom de amigo", "informal: conversa solta e natural",
                     "formal: tratamento educado, frases completas", "muito formal: linguagem cuidada, sem girias nem abreviacoes"]),
    "objetividade": ("objetividade|objetiv\\w*|direto|diretas?|curto|curta|conciso\\w*",
                     ["detalhista: explique com contexto e exemplos", "um pouco mais explicativo que o normal",
                      "objetivo: respostas curtas, 1 a 3 frases", "ultra objetivo: a resposta em uma frase, sem rodeio"]),
    "franqueza": ("franqueza|franc\\w*|sincer\\w*|opiniao|opinioes",
                  ["diplomatico: suavize criticas e evite contrariar", "cuidadoso ao discordar",
                   "franco: diga o que pensa, inclusive quando discorda", "muito franco: opine sem filtro e aponte falhas, sempre com respeito"]),
    "proatividade": ("proatividade|proativ\\w*|iniciativa|autonomia(?!\\s+remota)",
                     ["so responda o que foi perguntado", "pouca iniciativa: sugira algo so se for muito util",
                      "proativo: sugira o proximo passo quando fizer sentido", "muito proativo: antecipe necessidades e traga sugestoes junto da resposta"]),
}
NOMES = {"empatia": "empatia", "humor": "humor", "formalidade": "formalidade", "objetividade": "objetividade", "franqueza": "franqueza", "proatividade": "proatividade"}
MAIS = r"(?:aument\w+|sobe|suba|subir|eleva\w*|mais|incrementa\w*|capricha\w*|seja\s+mais|ser\s+mais)"
MENOS = r"(?:diminu\w+|reduz\w*|abaixa\w*|baixa\w*|menos|tira\s+um\s+pouco|seja\s+menos|ser\s+menos)"
DEFINIR = r"(?:coloca\w*|p[oõ]e|ponha|deixa\w*|muda\w*|define\w*|ajusta\w*|regula\w*)"


def _norm(t):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", (t or "").lower()) if unicodedata.category(c) != "Mn")


def niveis():
    try:
        d = json.loads(ARQ.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    return {k: max(0, min(10, int(d.get(k, PADRAO)))) for k in TRACOS}


def _gravar(n):
    ARQ.parent.mkdir(parents=True, exist_ok=True)
    ARQ.write_text(json.dumps(n, ensure_ascii=False), encoding="utf-8")


def _linhas():
    n = niveis()
    out = []
    for k, (_, frases) in TRACOS.items():
        v = n[k]
        if v == PADRAO:
            continue
        forte = "OBRIGATORIO em toda resposta, mesmo curta ou factual: " if v <= 2 or v >= 8 else ""
        out.append(f"- {k} {v}/10: {forte}" + frases[0 if v <= 1 else 1 if v <= 4 else 2 if v <= 7 else 3])
    return out


def bloco():
    """Trecho do prompt de sistema. Vazio com tudo em 5 (o caso comum)."""
    linhas = _linhas()
    if not linhas:
        return ""
    return "\n\nPERSONALIDADE (ajustada pelo Dono, 5/10 = neutro; vale na conversa com ele, com clientes e hospedes mantenha o tom profissional):\n" + "\n".join(linhas)


def lembrete():
    """Mesmo ajuste, mas colado ao pedido do Dono: no fim do prompt de sistema (11 mil caracteres) as IAs gratis o ignoravam."""
    linhas = _linhas()
    return ("\n\n[TOM DESTA RESPOSTA, pedido do Dono (nao cite este aviso):\n" + "\n".join(linhas) + "]") if linhas else ""


def _qual(t):
    for k, (rx, _) in TRACOS.items():
        if re.search(rf"\b(?:{rx})\b", t):
            return k
    return None


def resumo():
    n = niveis()
    return "Minha personalidade agora: " + ", ".join(f"{k} {v}/10" for k, v in n.items()) + ". Pode pedir 'mais humor', 'menos empatia' ou 'formalidade em 8'."


def comando(texto):
    """Frase curta do Dono que ajusta a personalidade -> resposta de confirmacao; None se nao for isso."""
    t = _norm(texto).strip(" .!?")
    t = re.sub(r"^jarvis\W+", "", t)
    if not t or len(t) > 70:
        return None
    if re.fullmatch(r"(?:como\s+(?:esta|ta)|qual\s+(?:e|esta))\s+(?:a\s+)?(?:sua\s+)?(?:personalidade|configuracao\s+de\s+personalidade)|mostra\w*\s+(?:a\s+)?(?:sua\s+)?personalidade", t):
        return resumo()
    if re.search(r"\b(?:volta\w*|reseta\w*|restaura\w*|zera\w*)\b.*\bpersonalidade\b|\bpersonalidade\b.*\b(?:normal|padrao)\b", t) or re.fullmatch(r"(?:volta|volte)\s+ao\s+normal", t):
        _gravar({k: PADRAO for k in TRACOS})
        return "Voltei a personalidade ao normal: tudo em 5/10."
    k = _qual(t)
    if not k or not re.match(rf"(?:{MAIS}|{MENOS}|{DEFINIR}|(?:a|o)\s|pode|poderia|quero|queria|preciso|da\s+pra|por\s+favor|seja|ser\b|{TRACOS[k][0]})", t):
        return None         # so frase de comando: 'tenho mais humor hoje' e conversa
    n = niveis()
    antes = n[k]
    m = re.search(r"\b(\d{1,2})\b", t)
    if re.search(rf"\b{DEFINIR}\b", t) or re.search(r"\b(?:em|para|pra|no|ao)\s+\d|\b(?:maximo|minimo|zero)\b", t):
        if re.search(r"\b(?:maximo|no\s+maximo|total)\b", t):
            novo = 10
        elif re.search(r"\b(?:minimo|zero|no\s+minimo)\b", t):
            novo = 0
        elif m:
            novo = int(m.group(1))
        else:
            return None
    elif re.search(rf"\b{MAIS}\b", t):
        novo = antes + PASSO
    elif re.search(rf"\b{MENOS}\b", t):
        novo = antes - PASSO
    else:
        return None
    novo = max(0, min(10, novo))
    n[k] = novo
    _gravar(n)
    if novo == antes:
        return f"A {k} já está em {antes}/10, no limite." if novo in (0, 10) else f"A {k} já está em {antes}/10."
    return f"Pronto, {k} de {antes} para {novo}/10." + (" (5 é o neutro.)" if novo == PADRAO else "")
