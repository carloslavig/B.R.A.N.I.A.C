# -*- coding: utf-8 -*-
"""RECADO FALADO (05/11/2026, pedido do Dono): os recados chegavam robóticos ("📩 Recado de X: «...»"). Agora o Jarvis conversa em ÁUDIO,
com calor humano: "Oi, Dono! Tudo bom? Olha, sua mãe entrou em contato falando que..." e resume o que a pessoa disse de forma simples.
O texto da pessoa é conteúdo de WhatsApp: o resumo é feito SÓ pelo Ollama local (nada vai a IA online); sem Ollama, usa um roteiro fixo."""
import re

MODELO = "qwen2.5:3b"
MAX_FALA = 900          # ~1 min de audio


def quem(nome):
    """Como o Dono chama a pessoa: 'sua mãe', 'seu pai', 'a Parceira'. Os outros vão pelo nome."""
    from . import contexto
    for apelido, rotulo in (("mae", "sua mãe"), ("pai", "seu pai"), ("parceira", "a Parceira")):
        if contexto.contato(apelido) == nome:
            return rotulo
    return nome


def _limpar(t):
    t = re.sub(r"https?://\S+", "um link", t or "")
    t = re.sub(r"[🀀-🿿☀-➿←-⇿]", "", t)
    return " ".join(t.split())


def _resumir_local(rotulo, falas, respostas, timeout=40):
    """Ollama local resume em 2-4 frases simples. Devolve texto ou '' (indisponível)."""
    try:
        import requests
        msgs = "\n".join("- " + f for f in falas)
        resp = ("\nO Jarvis respondeu a ela(e): " + " / ".join(respostas)) if respostas else ""
        prompt = (f"Você é o Jarvis, assistente do Dono, contando a ele por áudio o que {rotulo} disse. Escreva SÓ a fala, em português do Brasil, "
                  "simples, direta e carinhosa, em 2 a 4 frases curtas, sem listas, sem emojis, sem aspas. Conte o que a pessoa disse (como ela está, "
                  "se pediu algo, se precisa de algo) e, se o Jarvis já respondeu, diga o que respondeu. Não invente nada além do que está abaixo. "
                  f"Não comece com saudação.\nO que {rotulo} disse:\n{msgs}{resp}")
        r = requests.post("http://127.0.0.1:11434/api/generate", timeout=timeout,
                          json={"model": MODELO, "prompt": prompt, "stream": False, "keep_alive": "2m", "options": {"temperature": 0.3}})
        r.raise_for_status()
        return _limpar(r.json().get("response", ""))
    except Exception:
        return ""


def roteiro(nome, falas, respostas=(), resumir=None):
    """Fala completa para o Dono. `falas` = o que a pessoa escreveu/disse (literal); `resumir` injetável nos testes."""
    rotulo = quem(nome)
    falas = [_limpar(f) for f in falas if _limpar(f)]
    respostas = [_limpar(r) for r in respostas if _limpar(r)]
    resumo = (resumir or _resumir_local)(rotulo, falas, respostas)
    if not resumo or len(resumo) < 15:                      # sem IA local: conta as palavras dela, curtas
        junto = " ".join(falas)[:500]
        resumo = {"seu pai": "Ele disse assim: "}.get(rotulo, "Ela disse assim: " if rotulo in ("sua mãe", "a Parceira") else "A mensagem foi: ") + junto
    return f"Oi, Dono! Tudo bom? Olha, {rotulo} entrou em contato. {resumo} Qualquer coisa, é só abrir o WhatsApp e olhar a conversa."[:MAX_FALA]
