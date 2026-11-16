# -*- coding: utf-8 -*-
"""Titulo + hashtags do corte pela IA LOCAL (Ollama). Nada de IA paga; sem Ollama, usa um modelo de texto fixo."""
import json, re
import requests
from .. import power


def _padrao(canal, transcricao, titulo_base="", idioma="pt", nome=""):
    """Sem IA: titulo do clipe (dado pela comunidade) se for legivel; senao a 1a frase falada; senao um texto fixo."""
    base = re.sub(r"\s+", " ", titulo_base or "").strip()
    frase = re.split(r"(?<=[.!?])\s", (transcricao or "").strip())[0][:70].strip(" .,")
    nome = nome or canal.capitalize()
    tag_canal = f"#{re.sub(r'[^a-z0-9]', '', canal.lower())}"
    if len(re.sub(r"[^\w]", "", base)) >= 8:
        titulo = f"{base[:70]} | {nome}"
    elif len(frase) >= 12:
        titulo = frase[:1].upper() + frase[1:] + (f" | {nome}" if idioma == "en" else "")
    else:
        titulo = f"{nome} stream highlight" if idioma == "en" else f"Melhor momento da live do {nome}"
    if idioma == "en":
        return {"titulo": titulo, "hashtags": ["#shorts", "#twitch", tag_canal, "#twitchclips", "#streamer"]}
    return {"titulo": titulo, "hashtags": ["#shorts", "#twitch", tag_canal, "#cortes"]}


def _prompt_en(canal, nome, transcricao, jogo, titulo_base):
    return (f"You write titles for YouTube Shorts made from Twitch clips of the streamer {nome} (twitch.tv/{canal})"
            + (f", game {jogo}" if jogo else "") + ".\n"
            f"Original clip title (given by the viewers): \"{(titulo_base or '')[:100]}\"\n"
            "Transcript:\n\"\"\"" + (transcricao or "")[:1500] + "\"\"\"\n"
            "Reply ONLY with JSON: {\"titulo\": \"English, max 70 characters, include the streamer name, curiosity-driven and "
            "searchable, never claim something that is not in the clip, no ALL CAPS\", "
            "\"hashtags\": [\"#...\", 4 to 6 relevant English hashtags]}")


def _prompt_pt(canal, transcricao, jogo):
    return (f"Voce cria titulos de cortes (YouTube Shorts/TikTok) de live da Twitch do canal {canal}"
            + (f", jogo {jogo}" if jogo else "") + ".\nTranscricao do corte:\n\"\"\"" + (transcricao or "")[:1500] + "\"\"\"\n"
            "Responda SO um JSON: {\"titulo\": \"ate 70 caracteres, portugues do Brasil, chamativo, sem mentir sobre o conteudo\", "
            "\"hashtags\": [\"#...\", 4 a 6 hashtags]}")


def gerar(canal, transcricao, jogo="", modelo="qwen2.5:3b", usar_ia=True, titulo_base="", idioma="pt", nome=""):
    base = _padrao(canal, transcricao, titulo_base, idioma, nome)
    if not usar_ia or not transcricao or power.pausado():  # modo jogo: nao acorda o Ollama
        return base
    prompt = _prompt_en(canal, nome or canal, transcricao, jogo, titulo_base) if idioma == "en" else _prompt_pt(canal, transcricao, jogo)
    try:
        r = requests.post("http://127.0.0.1:11434/api/generate", timeout=90, json={
            "model": modelo, "prompt": prompt, "stream": False, "format": "json", "keep_alive": "2m", "options": {"temperature": 0.7}})
        d = json.loads(r.json().get("response", "{}"))
        titulo = str(d.get("titulo", "")).strip().strip('"')[:90]
        tags = [t if t.startswith("#") else "#" + t for t in (d.get("hashtags") or []) if isinstance(t, str) and t.strip()]
        if len(titulo) >= 8:
            tags = list(dict.fromkeys(["#shorts"] + [re.sub(r"\s+", "", t) for t in tags]))[:7]
            return {"titulo": titulo, "hashtags": tags}
    except (requests.RequestException, ValueError, AttributeError):
        pass
    return base
