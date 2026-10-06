# -*- coding: utf-8 -*-
"""Chaves de API pedidas na instalacao. Pelo menos UMA valida e obrigatoria; as outras sao opcionais, e cada uma diz o que melhora.
QUANTO MAIS CHAVES, MELHOR: cada servico tem uma cota gratis diaria; com varias o assistente troca de um para o outro quando uma acaba,
usa o mais rapido que estiver livre e a voz natural (que gasta cota do Google) dura mais. Ordem de pedido: Google primeiro."""
import json, urllib.error, urllib.request
from . import cofre

_GOOGLE_TESTE = lambda k: ("https://generativelanguage.googleapis.com/v1beta/models?key=" + k, {})
_GOOGLE_PASSOS = [
    "Abra aistudio.google.com/apikey no navegador (use a sua conta Google).",
    "Se aparecer uma tela de termos, aceite. Clique em “Criar chave de API” (Create API key).",
    "Escolha “Criar chave em um novo projeto” (ou um projeto que você já tenha).",
    "A chave aparece na tela (começa com AIza…). Clique em copiar.",
    "Volte aqui, cole no campo abaixo e clique em “Testar e guardar”.",
]

PROVEDORES = {
    "google": {
        "titulo": "Google (Gemini)", "onde": "https://aistudio.google.com/apikey", "gratis": True, "formato": "começa com AIza…",
        "melhora": "Respostas de alta qualidade, análise de imagens e a VOZ NATURAL do assistente. É a mais importante: comece por ela.",
        "passos": _GOOGLE_PASSOS, "teste": _GOOGLE_TESTE, "voz": True,
    },
    "google_b": {
        "titulo": "Google (2ª chave)", "onde": "https://aistudio.google.com/apikey", "gratis": True, "formato": "começa com AIza…", "extra": True,
        "melhora": "Dobra a cota de voz natural e de respostas do Google. Crie em OUTRO projeto (ou outra conta Google): cada projeto tem cota própria.",
        "passos": ["Abra aistudio.google.com/apikey de novo.", "Clique em “Criar chave de API” e escolha “Criar chave em um novo projeto” (tem que ser um projeto DIFERENTE do da primeira chave).",
                   "Copie a chave nova e cole abaixo."],
        "teste": _GOOGLE_TESTE, "voz": True,
    },
    "google_c": {
        "titulo": "Google (3ª chave)", "onde": "https://aistudio.google.com/apikey", "gratis": True, "formato": "começa com AIza…", "extra": True,
        "melhora": "Mais uma cota de voz natural e respostas. Mesmo processo: outro projeto, outra chave.",
        "passos": ["Repita o processo da 2ª chave, em mais um projeto novo.", "Copie a chave e cole abaixo."],
        "teste": _GOOGLE_TESTE, "voz": True,
    },
    "openrouter": {
        "titulo": "OpenRouter", "onde": "https://openrouter.ai/keys", "gratis": True, "formato": "começa com sk-or-…",
        "melhora": "Acesso a vários modelos gratuitos. Funciona de reserva quando o Google atinge a cota do dia.",
        "passos": ["Abra openrouter.ai e clique em “Sign in” (dá para entrar com a conta Google).", "No menu, abra “Keys” (openrouter.ai/keys).",
                   "Clique em “Create Key”, dê um nome (ex.: BRANIAC) e confirme.", "Copie a chave (começa com sk-or-…; ela só aparece uma vez) e cole abaixo."],
        "teste": lambda k: ("https://openrouter.ai/api/v1/auth/key", {"Authorization": "Bearer " + k}),
    },
    "groq": {
        "titulo": "Groq", "onde": "https://console.groq.com/keys", "gratis": True, "formato": "começa com gsk_…",
        "melhora": "Respostas MUITO rápidas (a conversa por voz fica fluida) e transcrição de áudio.",
        "passos": ["Abra console.groq.com e crie a conta (pode ser com Google ou GitHub).", "No menu, abra “API Keys”.",
                   "Clique em “Create API Key”, dê um nome e confirme.", "Copie a chave (começa com gsk_…; só aparece uma vez) e cole abaixo."],
        "teste": lambda k: ("https://api.groq.com/openai/v1/models", {"Authorization": "Bearer " + k}),
    },
    "cerebras": {
        "titulo": "Cerebras", "onde": "https://cloud.cerebras.ai/", "gratis": True, "formato": "começa com csk-…",
        "melhora": "Outra fila de respostas rápidas: divide o uso e economiza a cota dos outros.",
        "passos": ["Abra cloud.cerebras.ai e crie a conta.", "No painel, abra “API Keys”.", "Clique para gerar uma chave nova.", "Copie e cole abaixo."],
        "teste": lambda k: ("https://api.cerebras.ai/v1/models", {"Authorization": "Bearer " + k}),
    },
    "mistral": {
        "titulo": "Mistral", "onde": "https://console.mistral.ai/api-keys", "gratis": True, "formato": "texto longo",
        "melhora": "Mais um modelo de reserva, bom em português.",
        "passos": ["Abra console.mistral.ai e crie a conta (pode pedir confirmação por celular).", "Escolha o plano gratuito (Experiment) se perguntar.",
                   "Abra “API Keys” e clique em “Create new key”.", "Copie e cole abaixo."],
        "teste": lambda k: ("https://api.mistral.ai/v1/models", {"Authorization": "Bearer " + k}),
    },
}
ORDEM = list(PROVEDORES)
AVISO_PASSOS = "Os nomes dos botões podem mudar um pouco com o tempo, mas o caminho é sempre este. Se travar, o assistente ajuda: é só pedir."
POR_QUE_MAIS = ("Quanto mais chaves, melhor: cada serviço dá uma cota gratuita por dia. Com várias, o assistente troca de uma para outra quando a cota acaba, "
                "usa a mais rápida que estiver livre e a voz natural dura o dia todo (ela gasta cota do Google; uma 2ª chave do Google dobra isso).")
SEM_CHAVE = ("Sem nenhuma chave de API, tudo roda só no seu PC (Ollama): funciona offline e é privado, "
             "mas é mais lento, menos preciso e a voz do assistente fica robótica. Por isso pelo menos UMA chave é obrigatória.")


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


def nivel(chaves):
    """Quanto mais chaves, melhor: mostra o progresso (Nenhuma / Basico / Bom / Excelente) e o que falta para subir."""
    n = len(chaves)
    google = sum(1 for c in chaves if c.startswith("google"))
    if n == 0:
        return {"n": 0, "nome": "Nenhuma", "pct": 0, "proximo": "Conecte a chave do Google: ela liga a voz natural.", "voz_natural": False}
    if n == 1:
        return {"n": n, "nome": "Básico", "pct": 34, "proximo": "Adicione OpenRouter ou Groq para ter reserva e respostas mais rápidas.", "voz_natural": google > 0}
    if n <= 3:
        return {"n": n, "nome": "Bom", "pct": 68, "proximo": "Mais chaves (inclusive uma 2ª do Google) deixam voz e respostas ainda mais constantes.", "voz_natural": google > 0}
    return {"n": n, "nome": "Excelente", "pct": 100, "proximo": "Está ótimo: o assistente tem várias reservas e voz natural o dia todo.", "voz_natural": google > 0}


def catalogo():
    return [{"id": p, "titulo": v["titulo"], "onde": v["onde"], "gratis": v["gratis"], "melhora": v["melhora"], "formato": v.get("formato", ""),
             "passos": v["passos"], "extra": bool(v.get("extra")), "voz": bool(v.get("voz")), "obrigatoria": False} for p, v in PROVEDORES.items()]
