# -*- coding: utf-8 -*-
"""ENTRELINHAS (FASE 1 - SO OBSERVA, NUNCA AGE): le o que o Dono diz e anota o que o Braniac ENTENDERIA e o que PROPORIA fazer.
Parecer do conselho de IAs (08/10): perceber (classificador barato e LOCAL) != decidir (codigo Python) != executar (ferramentas, so com consentimento).

Nesta fase NADA e enviado, buscado ou contatado: so grava em data/entrelinhas.jsonl (so no PC; nunca vai para IA online) para o Dono revisar
('python -m braniac.entrelinhas revisar') e para ajustarmos os limiares antes de ligar qualquer acao (fases 2 em diante).

Camadas: 1) regras (palavras + tom + ironia) -> barato, instantaneo; 2) modelo local pequeno (Ollama) so quando as regras acham um gatilho
OU quando ha ironia/ambiguidade, para confirmar; se o Ollama nao estiver de pe, valem so as regras (e a confianca cai)."""
import json
import re
import time
import unicodedata

from .store import DATA

ARQ = DATA / "entrelinhas.jsonl"
MODELO_LOCAL = "qwen2.5:3b"


def _n(t):
    return "".join(c for c in unicodedata.normalize("NFD", (t or "").lower()) if unicodedata.category(c) != "Mn")


# gatilhos por categoria (texto normalizado: sem acento, minusculo)
FINANCEIRO = re.compile(r"\b(sem grana|sem dinheiro|sem um real|duro|quebrado|contas?(?: \w+){0,2} (?:apertad\w*|atrasad\w*|pra pagar|para pagar|chegando)|apertad[oa] (?:de|com) (?:grana|dinheiro)|"
                        r"grana (?:curta|apertada|ta (?:curta|ruim))|preciso (?:de|juntar|ganhar) (?:grana|dinheiro|uma renda)|nao (?:tenho|to com) (?:dinheiro|grana)|"
                        r"dinheiro (?:acabou|curto|apertado)|(?:to|estou|ando) (?:falido|liso|na pindaiba)|boleto|fatura|aluguel atrasado|pagar as contas|"
                        r"renda extra|trabalho extra|bico|ganhar (?:mais )?(?:grana|dinheiro))\b")
EMOCIONAL = re.compile(r"\b(nao (?:to|estou|tou) (?:muito )?bem|nao (?:to|estou) me sentindo bem|(?:to|estou|tou) (?:meio |muito |bem )?(?:mal|mal mesmo|pra baixo|triste|desanimad[oa]|deprimid[oa]|ansios[oa]|estressad[oa]|sobrecarregad[oa])|"
                        r"(?:to|estou|tou) (?:meio |muito |bem )?(?:sem animo|sem forcas)|nao aguento mais|cabeca (?:cheia|a mil)|me sentindo (?:mal|sozinho|perdid[oa]|pra baixo)|"
                        r"chorei|vontade de chorar|ta pesado|dia (?:ruim|pesado|dificil)|to na pior|desabaf)\b")
RISCO = re.compile(r"\b(suicid|me matar|tirar (?:a )?minha vida|acabar com (?:tudo|a minha vida)|nao quero (?:mais )?viver|sumir pra sempre|me machucar|automutila|nao vejo saida|"
                   r"queria (?:morrer|desaparecer)|melhor (?:eu )?nao existir)\b")
CANSACO = re.compile(r"\b(cansad[oa]|exaust[oa]|esgotad[oa]|sem energia|sem dormir|dormi mal|noite em claro|nao dormi)\b")
PRESSA = re.compile(r"\b(urgente|rapido|o quanto antes|pra ontem|agora (?:mesmo)?|corre|depressa|hoje ainda|ja ja)\b")
PREOCUPACAO = re.compile(r"\b(preocupad[oa]|aflit[oa]|nervos[oa]|com medo|receio|nao sei (?:o que fazer|como vou)|(?:to|estou) perdid[oa]|nao sei se vai dar)\b")
PEDIDO_INDIRETO = re.compile(r"\b(seria bom se|queria (?:que|saber se)|sera que (?:da|voce consegue|tem como)|se (?:voce|vc) pudesse|tomara que|ia ser (?:bom|otimo|legal)|eu precisava (?:de|que))\b")
IRONIA = re.compile(r"(kkk+|haha+|rs+\b|😂|🤣|😅|\bsq\b|so que nao|so brincando|brincadeira|zoeira|vou vender (?:meu|um) rim|\bmeu deus ne\b|claro que sim ne|que maravilha ne|parabens pra mim)", re.I)
POSITIVO = re.compile(r"\b(tranquilo|de boa|tudo certo|tudo bem agora|ja passou|melhorei|resolvido|resolveu|passou|nao e nada)\b")
NEGACAO_RECENTE = re.compile(r"\b(deixa pra la|esquece|nao precisa|nao quero (?:ajuda|isso)|me deixa|so desabafando|nao e nada)\b")


def classificar_regras(texto):
    """Camada 1 (sem rede). -> dict com: categorias (lista), ironia, risco, tom, confianca (0-1)."""
    t = _n(texto)
    cats = []
    for nome, rx in (("financeiro", FINANCEIRO), ("emocional", EMOCIONAL), ("cansaco", CANSACO), ("preocupacao", PREOCUPACAO), ("pressa", PRESSA), ("pedido_indireto", PEDIDO_INDIRETO)):
        if rx.search(t):
            cats.append(nome)
    risco = bool(RISCO.search(t))
    ironia = bool(IRONIA.search(texto or "")) or bool(IRONIA.search(t))
    positivo = bool(POSITIVO.search(t))
    recuo = bool(NEGACAO_RECENTE.search(t))
    conf = 0.0
    if cats:
        conf = 0.55 + 0.15 * min(len(cats), 2)
        if len(t) > 25:
            conf += 0.05                                  # frase com contexto e mais confiavel que palavra solta
    if ironia:
        conf -= 0.35                                      # piada/zoeira: derruba a confianca (regra do conselho)
    if positivo or recuo:
        conf -= 0.25
    if risco:
        conf, cats = max(conf, 0.95), cats + ["risco"]
    return {"categorias": cats, "ironia": ironia, "risco": risco, "recuo": recuo or positivo, "confianca": round(max(0.0, min(conf, 0.99)), 2)}


def _perguntar_ollama(texto, ctx, timeout=25):
    """Camada 2 (LOCAL): confirma/ajusta. Devolve dict ou None se o Ollama nao estiver disponivel. Nada sai do PC."""
    try:
        import requests
        prompt = ("Analise a ultima mensagem de um usuario a seu assistente pessoal. Responda SOMENTE JSON com as chaves: "
                  "intencao (financeira|emocional|pedido_indireto|comando|conversa), sentimento (positivo|neutro|negativo), ironia (true|false), "
                  "urgencia (baixa|media|alta), necessidade_implicita (frase curta ou vazio), confianca (0 a 1).\n"
                  f"Contexto recente: {ctx[-3:] if ctx else []}\nMensagem: {texto}")
        r = requests.post("http://127.0.0.1:11434/api/generate", timeout=timeout,
                          json={"model": MODELO_LOCAL, "prompt": prompt, "stream": False, "format": "json", "keep_alive": "2m", "options": {"temperature": 0}})
        r.raise_for_status()
        d = json.loads(r.json().get("response", "{}"))
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def classificar(texto, ctx=None, usar_local=True, local=None):
    """Classificacao completa. `local` injetavel nos testes."""
    r = classificar_regras(texto)
    r["local"] = None
    duvida = r["categorias"] or r["ironia"]
    if usar_local and duvida and not r["risco"]:
        d = (local or _perguntar_ollama)(texto, ctx or [])
        if d:
            r["local"] = d
            try:
                c_local = float(d.get("confianca", 0.5))
            except (TypeError, ValueError):
                c_local = 0.5
            if d.get("ironia") in (True, "true", "True") and not r["ironia"]:
                r["ironia"] = True
                r["confianca"] = round(max(0.0, r["confianca"] - 0.3), 2)
            if str(d.get("intencao", "")).startswith(("financ", "emoc")):
                r["confianca"] = round(min(0.99, (r["confianca"] + c_local) / 2 + 0.1), 2)
            elif d.get("intencao") in ("conversa", "comando") and r["confianca"] < 0.9:
                r["confianca"] = round(max(0.0, r["confianca"] - 0.25), 2)       # o modelo local acha que e conversa comum: segura
    return r


# ---- o que o Braniac PROPORIA (fase 1: so anota). Quanto maior o impacto, maior a confianca exigida.
LIMIARES = {"buscar_vagas": 0.65, "perguntar_como_esta": 0.6, "oferecer_avisar_alguem": 0.8, "acolher_e_indicar_ajuda": 0.0}


def propor(r, historico_recente=()):
    """-> lista de acoes que o Braniac PROPORIA (ainda nao executa). Cada uma: tipo, motivo, confianca, impacto, requer_consentimento."""
    acoes = []
    c = r["confianca"]
    cats = set(r["categorias"])
    if "risco" in cats:
        return [{"tipo": "acolher_e_indicar_ajuda", "motivo": "sinal de risco: acolher, indicar ajuda humana (CVV 188, pessoas proximas) e nao insistir", "confianca": c,
                 "impacto": "alto", "requer_consentimento": False}]
    if r["ironia"] or r["recuo"]:
        return []
    # recorrencia: o tema ja apareceu antes? (reduz falso positivo de desabafo passageiro)
    rec = sum(1 for h in historico_recente if set(h.get("categorias", [])) & cats)
    if "financeiro" in cats and c + 0.05 * min(rec, 2) >= LIMIARES["buscar_vagas"]:
        acoes.append({"tipo": "buscar_vagas", "motivo": "reclamou de dinheiro/contas", "confianca": c, "impacto": "baixo", "requer_consentimento": False})
    if cats & {"emocional", "cansaco", "preocupacao"}:
        if c + 0.05 * min(rec, 2) >= LIMIARES["perguntar_como_esta"]:
            acoes.append({"tipo": "perguntar_como_esta", "motivo": "disse que nao esta bem/cansado/preocupado", "confianca": c, "impacto": "baixo", "requer_consentimento": False})
        if c >= LIMIARES["oferecer_avisar_alguem"]:
            acoes.append({"tipo": "oferecer_avisar_alguem", "motivo": "emocional forte: oferecer avisar a Parceira (so se ele disser sim)", "confianca": c, "impacto": "medio", "requer_consentimento": True})
    return acoes


def _ler_log(n=200):
    try:
        linhas = ARQ.read_text(encoding="utf-8").splitlines()[-n:]
    except OSError:
        return []
    out = []
    for l in linhas:
        try:
            out.append(json.loads(l))
        except ValueError:
            pass
    return out


def observar(texto, ctx=None, usar_local=True, local=None, agora=None):
    """Chamado a cada mensagem do Dono. Nunca levanta excecao e NUNCA age: so grava. Devolve o registro (ou None se nada a anotar)."""
    try:
        texto = (texto or "").strip()
        if len(texto) < 4 or texto.startswith("/"):
            return None
        r = classificar(texto, ctx, usar_local, local)
        if not r["categorias"] and not r["ironia"]:
            return None                                     # conversa comum: nao enche o log
        agora = agora if agora is not None else time.time()
        recentes = [h for h in _ler_log(30) if agora - h.get("ts", 0) < 48 * 3600]
        reg = {"ts": agora, "texto": texto[:300], **r, "proporia": propor(r, recentes), "executou": []}   # executou fica sempre vazio na fase 1
        DATA.mkdir(exist_ok=True)
        with ARQ.open("a", encoding="utf-8") as f:
            f.write(json.dumps(reg, ensure_ascii=False) + "\n")
        return reg
    except Exception:
        return None


def revisar(n=15):
    """Texto legivel do que foi observado (para o Dono conferir)."""
    reg = _ler_log(n)
    if not reg:
        return "Ainda não anotei nada."
    linhas = []
    for h in reg:
        quando = time.strftime("%d/%m %H:%M", time.localtime(h["ts"]))
        prop = ", ".join(a["tipo"] for a in h.get("proporia", [])) or "nada (seguro)"
        linhas.append(f"{quando} | \"{h['texto'][:80]}\" -> {'+'.join(h['categorias']) or 'ironia'}{' [ironia]' if h['ironia'] else ''} conf={h['confianca']} | proporia: {prop}")
    return "\n".join(linhas)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "revisar":
        print(revisar())
    else:
        frase = " ".join(sys.argv[1:])
        r = classificar(frase, usar_local=False)
        print(json.dumps({**r, "proporia": propor(r)}, ensure_ascii=False, indent=2))
