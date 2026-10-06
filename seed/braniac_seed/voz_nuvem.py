# -*- coding: utf-8 -*-
"""Voz natural do assistente, puxada do servico de IA da pessoa (Gemini TTS, pela chave do Google dela) e melhorada:

  - limpa o texto para soar falado (sem links, markdown, emojis; exclamacao vira ponto = tom mais calmo);
  - voz masculina ou feminina em portugues do Brasil, com varias opcoes para escolher;
  - instrucao de estilo (calma, clara, natural) e rejeita audio suspeito (modelo que leu a instrucao em voz alta);
  - acabamento: corta silencio das pontas, normaliza volume e suaviza o inicio/fim;
  - CACHE em disco (mesma fala = zero cota) e rodizio de modelos e de chaves do Google (cada chave/projeto tem cota propria);
  - sem chave, sem cota ou sem internet: devolve erro e a tela usa a voz robotica do sistema.
Quanto mais chaves do Google, mais voz natural por dia."""
import array, base64, hashlib, io, json, re, threading, time, urllib.error, urllib.request, wave
from . import cofre, paths

MODELOS = ["gemini-3.1-flash-tts-preview", "gemini-2.5-flash-preview-tts", "gemini-2.5-pro-preview-tts"]
CHAVES_GOOGLE = ["google", "google_b", "google_c"]
VOZES = {   # genero -> [(nome do Gemini, como descrever para a pessoa)]
    "feminina": [("Kore", "firme e clara"), ("Sulafat", "calorosa"), ("Vindemiatrix", "gentil"), ("Despina", "suave")],
    "masculina": [("Achird", "amigável"), ("Charon", "informativa"), ("Orus", "firme"), ("Umbriel", "tranquila")],
}
ESTILOS = {   # id -> (nome para a pessoa, instrucao dada ao modelo)
    "calmo": ("Calmo e acolhedor", "Fale em português do Brasil, com voz natural e clara, tom calmo e acolhedor, ritmo tranquilo, como um assistente pessoal atencioso, sem exagero e sem empolgação"),
    "profissional": ("Profissional e firme", "Fale em português do Brasil em tom sério, calmo e sóbrio, como um assistente profissional e seguro de si: voz firme, ritmo pausado e natural, sem empolgação"),
    "animado": ("Animado e simpático", "Fale em português do Brasil com voz simpática e animada, ritmo natural e leve, como um amigo prestativo"),
}
ESTILO = ESTILOS["calmo"][1]
_cooldown = {}          # (modelo, chave) -> ate quando evitar
_lock = threading.Lock()
ULTIMO = {"motor": ""}
_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿️‍]")


class VozErro(RuntimeError):
    pass


def disponivel():
    """True se ha pelo menos uma chave do Google (so ela da voz natural)."""
    for c in CHAVES_GOOGLE:
        try:
            if cofre.tem(c):
                return True
        except cofre.CofreErro:
            return False
    return False


def limpar(texto):
    t = re.sub(r"https?://\S+|www\.\S+", "", str(texto))
    t = t.replace("**", "").replace("__", "").replace("`", "").replace("«", "").replace("»", "")
    t = _EMOJI.sub("", t)
    t = re.sub(r"(?m)^\s*[-•*]\s+", "", t)
    t = re.sub(r"!+", ".", t)
    return re.sub(r"\s+", " ", t).strip()


def voz_padrao(genero):
    return VOZES.get(genero, VOZES["feminina"])[0][0]


def _plausivel(texto, segundos):
    """Audio longo demais para o texto = o modelo leu a instrucao de estilo em voz alta."""
    return segundos <= max(1, len(texto.split())) / 1.3 + 3.5


def _para_wav(pcm, taxa=24000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(pcm)
    return buf.getvalue()


def polir(wav_bytes):
    """Acabamento sem dependencias pesadas: corta silencio das pontas, normaliza o volume e suaviza inicio/fim."""
    with wave.open(io.BytesIO(wav_bytes)) as w:
        taxa, canais = w.getframerate(), w.getnchannels()
        x = array.array("h")
        x.frombytes(w.readframes(w.getnframes()))
    if not x or canais != 1:
        return wav_bytes
    pico = max(max(x), -min(x))
    if pico < 50:
        return wav_bytes
    lim = pico * 0.006
    ini = next((i for i, v in enumerate(x) if abs(v) > lim), 0)
    fim = next((i for i in range(len(x) - 1, -1, -1) if abs(x[i]) > lim), len(x) - 1)
    x = x[max(0, ini - int(taxa * 0.12)): min(len(x), fim + int(taxa * 0.18))]
    ganho = (0.9 * 32767) / max(max(x), -min(x), 1)
    y = array.array("h", (max(-32768, min(32767, int(v * ganho))) for v in x))
    n = int(taxa * 0.008)
    if len(y) > 2 * n:
        for i in range(n):
            f = i / n
            y[i] = int(y[i] * f)
            y[-1 - i] = int(y[-1 - i] * f)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(y.tobytes())
    return buf.getvalue()


def _post(url, chave, corpo, timeout=60):
    req = urllib.request.Request(url, json.dumps(corpo).encode("utf-8"), {"Content-Type": "application/json", "x-goog-api-key": chave})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read())


def _cache_arq(texto, voz, estilo_txt):
    h = hashlib.sha1(f"{voz}|{estilo_txt}|{texto}".encode("utf-8")).hexdigest()
    d = paths.dados_dir() / "voz_cache"
    d.mkdir(exist_ok=True)
    return d / (h + ".wav")


def sintetizar(texto, genero="feminina", voz=None, post=None, chaves=None, usar_cache=True, estilo="calmo"):
    """Devolve bytes WAV com a voz natural. Levanta VozErro se nao for possivel (a tela cai na voz do sistema)."""
    texto = limpar(texto)[:900]
    if not texto:
        raise VozErro("texto vazio")
    voz = voz or voz_padrao(genero)
    estilo_txt = ESTILOS.get(estilo, ESTILOS["calmo"])[1]
    arq = _cache_arq(texto, voz, estilo_txt)
    if usar_cache and arq.exists():
        ULTIMO["motor"] = "cache"
        return arq.read_bytes()
    post = post or _post
    if chaves is None:
        chaves = []
        for c in CHAVES_GOOGLE:
            try:
                k = cofre.ler(c)
            except cofre.CofreErro:
                k = None
            if k:
                chaves.append((c, k))
    if not chaves:
        raise VozErro("sem chave do Google: usando a voz do sistema")
    prompt = f"{estilo_txt}: {texto}"
    erros = []
    for modelo in MODELOS:
        for nome_chave, chave in chaves:
            if _cooldown.get((modelo, nome_chave), 0) > time.time():
                continue
            corpo = {"contents": [{"parts": [{"text": prompt}]}],
                     "generationConfig": {"responseModalities": ["AUDIO"],
                                          "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voz}}}}}
            try:
                _, dados = post(f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent", chave, corpo)
                pcm = base64.b64decode(dados["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
            except urllib.error.HTTPError as e:
                _cooldown[(modelo, nome_chave)] = time.time() + (900 if e.code == 429 else 120)   # sem cota: nao insiste por 15 min
                erros.append(f"{modelo}/{nome_chave}: HTTP {e.code}")
                continue
            except (KeyError, IndexError, ValueError):
                erros.append(f"{modelo}/{nome_chave}: resposta vazia")
                continue
            except Exception as e:
                erros.append(f"{modelo}/{nome_chave}: {str(e)[:40]}")
                continue
            if not _plausivel(texto, len(pcm) / 48000):
                erros.append(f"{modelo}: áudio longo demais")
                continue
            wav = polir(_para_wav(pcm))
            ULTIMO["motor"] = f"gemini:{modelo}:{voz}"
            if usar_cache:
                arq.write_bytes(wav)
            return wav
    raise VozErro("sem voz natural agora (" + "; ".join(erros[:3]) + ")")
