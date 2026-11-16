# -*- coding: utf-8 -*-
"""CONSELHO DE IAs DO BRANIAC: a 'reuniao' entre as IAs parceiras (ChatGPT, Gemini, Grok, DeepSeek, Kimi) sobre um assunto.
O Dono, a Layla ou a Parceira pedem ('use o conselho', 'chama o conselho de IAs...') e o Braniac pergunta o mesmo tema
a cada IA (abas logadas, uma por vez), junta as respostas e produz uma sintese.
Seguranca: so vai o TEMA (nunca conteudo de WhatsApp, nomes de clientes, telefones, senhas ou dados financeiros)."""
import re
from . import contexto

# so dispara com VERBO de pedido antes de 'conselho' (e nunca em quem apenas cita o conselho: 'o conselho sugeriu...'): evita laco com a Layla
PEDIDO = re.compile(r"\b(?:use|usa|usar|usem|chama|chame|chamar|convoca|convoque|convocar|re[uú]ne|reuna|reunir|faz|fa[cç]a|fazer|pergunta|pergunte|consulta|consultar|consulte|consultem|pede|pe[cç]a)\b[^.!?\n]{0,40}\bconselho\b", re.I)
# comandos de envio/aviso (Jarvis manda mensagem...) NAO sao pedido de conselho, mesmo que o texto a enviar cite o conselho
_ENVIO = re.compile(r"^\s*(?:jarvis[,. ]+)?(?:manda|mande|envia|envie|avisa|avise|fala|fale|diz|diga)\b", re.I)
IAS = ("chatgpt", "gemini", "grok", "deepseek", "kimi")
PAPEL = {"chatgpt": "raciocínio e ideias", "gemini": "criatividade e alternativas", "grok": "checagem de fatos", "deepseek": "análise técnica e lógica passo a passo", "kimi": "pesquisa e textos longos", "meta": "imagens realistas (gerar_imagem)"}
QUEM_PODE = ("dono", "parceira", "parceira", "layla", "lyla", "loja esphiraria", "loja")


def pode_convocar(chat):
    """Dono (chat dele), Parceira e Layla. Qualquer outra pessoa nao aciona o conselho."""
    n = contexto._norm(chat or "")
    return n == "eu" or any(q in n for q in QUEM_PODE) or contexto.prioritario(chat)


def pediu(texto):
    return bool(PEDIDO.search(texto or "")) and not _ENVIO.match(texto or "")


def tema_de(texto):
    """Tira o 'use o conselho de IAs' e deixa o assunto."""
    t = PEDIDO.sub(" ", texto or "")
    t = re.sub(r"^(?:jarvis[,. ]+)?(?:pra|para|e|com|do|sobre|a respeito de|[:,-])*\s*", "", t.strip(), flags=re.I)
    return t.strip(" .,:;-")


def para_enviar(rel, limite=1200):
    """Versao para WhatsApp: so a sintese quando existir; senao corta no fim de um paragrafo (nunca no meio da frase)."""
    if "✅ Síntese:" in rel:
        return rel.split("✅ Síntese:", 1)[1].strip()[:limite]
    if len(rel) <= limite:
        return rel
    corte = rel[:limite]
    i = max(corte.rfind("\n\n"), corte.rfind(". "))
    return corte[:i + 1].strip() if i > 200 else corte.rsplit(" ", 1)[0]


def sintetizar_padrao(prompt):
    """Sintese pelo roteador de IAs do Braniac (usada quando o pedido vem do WhatsApp, onde nao ha roteador a mao)."""
    from .router import Router
    global _ROUTER
    if _ROUTER is None:
        _ROUTER = Router()
    return _ROUTER.responder("conselho-ias", prompt)[0]


_ROUTER = None


def reunir(tema, consultar, sintetizar=None, formato=None):
    """consultar(ia, pergunta) -> texto; sintetizar(texto_com_respostas) -> texto ou None. Devolve o relatorio do conselho."""
    if len(tema) < 12:
        return "Qual o assunto do conselho de IAs do Braniac? Me passa o tema completo."
    pergunta = (f"Você participa de um conselho de IAs. Dê sua opinião objetiva (até 8 linhas, em português) sobre: {tema}. "
                "Seu papel no conselho: <PAPEL>.")   # replace, nao format: tema com chaves {} quebrava (automelhoria 24/10)
    respostas = {}
    for ia in IAS:
        r = consultar(ia, pergunta.replace("<PAPEL>", PAPEL[ia]))
        if r and not r.startswith(("nao consegui", "pergunta barrada", "IA desconhecida")):
            respostas[ia] = r.strip()
        else:
            respostas[ia] = None
            if r and r.startswith("pergunta barrada"):
                return "Conselho cancelado: " + r
    ok = {k: v for k, v in respostas.items() if v}
    if not ok:
        return "O conselho de IAs não conseguiu se reunir agora (nenhuma IA respondeu)."
    corpo = "\n\n".join(f"• {k}: {v}" for k, v in ok.items())
    ausentes = [k for k, v in respostas.items() if not v]
    sintese = None
    if sintetizar:
        try:
            sintese = sintetizar(f"Tema: {tema}\n\nOpiniões do conselho:\n{corpo}\n\n"
                                + (f"Responda EXATAMENTE no formato que foi pedido: {formato}" if formato else "Faça uma síntese curta (até 6 linhas) com a decisão recomendada e os pontos de divergência."))
        except Exception:
            sintese = None
    rel = "🏛 Conselho de IAs do Braniac\n\n" + corpo
    if ausentes:
        rel += f"\n\n(não responderam: {', '.join(ausentes)})"
    if sintese:
        rel += "\n\n✅ Síntese: " + sintese.strip()
    return rel
