# -*- coding: utf-8 -*-
"""Cerebro minimo da instalacao: usa a 1a chave valida (Google, OpenRouter, Groq...) e, se nao houver, o Ollama LOCAL.
(O roteador completo, com hedging e banco unificado, vem do nucleo do Braniac; aqui so o necessario para a instalacao conversar.)"""
import json, urllib.request
from . import cofre, hardware

OPENAI = {   # provedor -> (url, modelo)
    "google": ("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "gemini-flash-latest"),
    "groq": ("https://api.groq.com/openai/v1/chat/completions", "openai/gpt-oss-120b"),
    "openrouter": ("https://openrouter.ai/api/v1/chat/completions", "nvidia/nemotron-3-ultra-550b-a55b:free"),
    "cerebras": ("https://api.cerebras.ai/v1/chat/completions", "gpt-oss-120b"),
    "mistral": ("https://api.mistral.ai/v1/chat/completions", "mistral-small-latest"),
}
OLLAMA = "http://127.0.0.1:11434/api/chat"


class LLMErro(RuntimeError):
    pass


def _post(url, corpo, headers=None, timeout=90):
    req = urllib.request.Request(url, json.dumps(corpo).encode("utf-8"), {"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def responder(prompt, sistema="Você é um assistente pessoal. Responda em português do Brasil, de forma objetiva.", post=None, chaves=None):
    post = post or _post
    msgs = [{"role": "system", "content": sistema}, {"role": "user", "content": prompt}]
    erros = []
    for prov in (chaves if chaves is not None else list(OPENAI)):
        try:
            chave = cofre.ler(prov)
        except cofre.CofreErro:
            chave = None
        if not chave:
            continue
        url, modelo = OPENAI[prov]
        try:
            return post(url, {"model": modelo, "messages": msgs}, {"Authorization": "Bearer " + chave})["choices"][0]["message"]["content"].strip(), prov
        except Exception as e:
            erros.append(f"{prov}: {e}")
    try:   # sem chave (ou todas falharam): modelo local
        perf = hardware.PERFIS[hardware.recomendar(hardware.detectar())[0]]
        return post(OLLAMA, {"model": perf["ollama"], "messages": msgs, "stream": False}, timeout=180)["message"]["content"].strip(), "ollama"
    except Exception as e:
        raise LLMErro("nenhuma IA respondeu (" + "; ".join(erros + [f"ollama: {e}"]) + ")")
