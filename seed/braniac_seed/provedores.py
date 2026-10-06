# -*- coding: utf-8 -*-
"""Chaves de API pedidas na instalacao. Pelo menos UMA valida e obrigatoria; as outras sao opcionais, e cada uma diz o que melhora.
Ordem de pedido: Google primeiro (a mais facil e generosa), depois OpenRouter, Groq, Cerebras, Mistral."""
import json, urllib.error, urllib.request
from . import cofre

PROVEDORES = {
    "google": {
        "titulo": "Google (Gemini)", "onde": "https://aistudio.google.com/apikey", "gratis": True,
        "melhora": "Respostas de alta qualidade, análise de imagens e voz mais natural. É a mais recomendada para começar.",
        "teste": lambda k: ("https://generativelanguage.googleapis.com/v1beta/models?key=" + k, {}),
    },
    "openrouter": {
        "titulo": "OpenRouter", "onde": "https://openrouter.ai/keys", "gratis": True,
        "melhora": "Acesso a vários modelos gratuitos. Funciona de reserva quando o Google atinge a cota do dia.",
        "teste": lambda k: ("https://openrouter.ai/api/v1/auth/key", {"Authorization": "Bearer " + k}),
    },
    "groq": {
        "titulo": "Groq", "onde": "https://console.groq.com/keys", "gratis": True,
        "melhora": "Respostas MUITO rápidas (conversa por voz fluida) e transcrição de áudio.",
        "teste": lambda k: ("https://api.groq.com/openai/v1/models", {"Authorization": "Bearer " + k}),
    },
    "cerebras": {
        "titulo": "Cerebras", "onde": "https://cloud.cerebras.ai/", "gratis": True,
        "melhora": "Mais uma fila de respostas rápidas: divide o uso e economiza a cota dos outros.",
        "teste": lambda k: ("https://api.cerebras.ai/v1/models", {"Authorization": "Bearer " + k}),
    },
    "mistral": {
        "titulo": "Mistral", "onde": "https://console.mistral.ai/api-keys", "gratis": True,
        "melhora": "Mais um modelo de reserva, bom em português.",
        "teste": lambda k: ("https://api.mistral.ai/v1/models", {"Authorization": "Bearer " + k}),
    },
}
ORDEM = list(PROVEDORES)
SEM_CHAVE = ("Sem nenhuma chave de API, tudo roda só no seu PC (Ollama): funciona offline e é privado, "
             "mas é mais lento e menos preciso. Por isso pelo menos UMA chave é obrigatória.")


def _http(url, headers):
    req = urllib.request.Request(url, headers={"User-Agent": "braniac-seed", **headers})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status


def validar(provedor, chave, http=None):
    """(ok, motivo). Testa a chave NA HORA: evita terminar a instalacao com um assistente 'mudo'."""
    chave = (chave or "").strip()
    if provedor not in PROVEDORES:
        return False, "provedor desconhecido"
    if len(chave) < 20:
        return False, "essa chave parece curta demais; copie ela inteira"
    url, headers = PROVEDORES[provedor]["teste"](chave)
    try:
        status = (http or _http)(url, headers)
    except urllib.error.HTTPError as e:
        return False, "chave recusada pelo serviço" if e.code in (400, 401, 403) else f"o serviço respondeu {e.code}; tente de novo"
    except Exception:
        return False, "não consegui falar com o serviço; confira a internet"
    return (True, "ok") if status == 200 else (False, f"o serviço respondeu {status}")


def cadastrar(provedor, chave, http=None):
    """Valida e so entao guarda no cofre."""
    ok, motivo = validar(provedor, chave, http)
    if ok:
        cofre.guardar(provedor, chave)
    return ok, motivo


def chaves_validas():
    out = []
    for p in ORDEM:
        try:
            if cofre.tem(p):
                out.append(p)
        except cofre.CofreErro:
            pass
    return out


def catalogo():
    return [{"id": p, "titulo": v["titulo"], "onde": v["onde"], "gratis": v["gratis"], "melhora": v["melhora"],
             "obrigatoria": False} for p, v in PROVEDORES.items()]
