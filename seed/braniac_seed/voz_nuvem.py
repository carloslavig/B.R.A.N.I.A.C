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
_cooldown_motivo = {}   # (modelo, chave) -> 'cota' | 'outro' (para explicar a pessoa por que a voz natural esta fora)
_lock = threading.Lock()
ULTIMO = {"motor": ""}
_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿️‍]")


class VozErro(RuntimeError):
    def __init__(self, msg, motivo="outro"):
        super().__init__(msg)
        self.motivo = motivo


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


class _Falha(Exception):
    def __init__(self, motivo, msg):
        super().__init__(msg)
        self.motivo = motivo


TIMEOUT_TENTATIVA = 22      # os modelos de voz 'preview' as vezes travam: nao espera mais que isto por tentativa
HEDGE_S = 6                 # se a tentativa demora, a proxima (outro modelo/chave) ja comeca em paralelo


def _tentar(post, modelo, nome_chave, chave, prompt, voz, texto):
    corpo = {"contents": [{"parts": [{"text": prompt}]}],
             "generationConfig": {"responseModalities": ["AUDIO"],
                                  "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voz}}}}}
    try:
        _, dados = post(f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent", chave, corpo, timeout=TIMEOUT_TENTATIVA)
        pcm = base64.b64decode(dados["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
    except urllib.error.HTTPError as e:
        _cooldown[(modelo, nome_chave)] = time.time() + (900 if e.code == 429 else 120)   # sem cota: nao insiste por 15 min
        _cooldown_motivo[(modelo, nome_chave)] = "cota" if e.code == 429 else "outro"
        raise _Falha("cota" if e.code == 429 else "outro", f"{modelo}/{nome_chave}: HTTP {e.code}")
    except (KeyError, IndexError, ValueError):
        raise _Falha("outro", f"{modelo}/{nome_chave}: resposta vazia")
    except Exception as e:
        lento = "timed out" in str(e).lower() or "timeout" in str(e).lower()
        # travou: NAO fica em descanso (os modelos preview travam por acaso e na proxima costumam responder); quem decide tentar de novo e o chamador
        raise _Falha("lento" if lento else "rede", f"{modelo}/{nome_chave}: {str(e)[:40]}")
    if not _plausivel(texto, len(pcm) / 48000):
        raise _Falha("outro", f"{modelo}: áudio longo demais")
    return pcm


def sintetizar(texto, genero="feminina", voz=None, post=None, chaves=None, usar_cache=True, estilo="calmo"):
    """Devolve bytes WAV com a voz natural. Levanta VozErro (com .motivo: cota | lento | rede | outro) se nao for possivel:
    a tela mostra o motivo e cai na voz do sistema."""
    import concurrent.futures as cf
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
        raise VozErro("sem chave do Google: usando a voz do sistema", "sem_chave")
    prompt = f"{estilo_txt}: {texto}"
    fila = [(m, n, k) for m in MODELOS for n, k in chaves if _cooldown.get((m, n), 0) <= time.time()]
    if not fila:
        motivos_cd = {_cooldown_motivo.get((m, n), "cota") for m in MODELOS for n, _ in chaves}
        raise VozErro("a cota da voz natural acabou por agora (volta em alguns minutos)" if motivos_cd == {"cota"} else "a voz natural está indisponível por alguns minutos",
                      "cota" if motivos_cd == {"cota"} else "outro")
    erros, pend, pos, refeitas, duplicadas = [], {}, [0], {}, [0]
    ex = cf.ThreadPoolExecutor(max_workers=3)

    def lancar():
        m, n, k = fila[pos[0]]
        pos[0] += 1
        pend[ex.submit(_tentar, post, m, n, k, prompt, voz, texto)] = m

    try:
        lancar()
        while pend:
            feitos, _ = cf.wait(list(pend), timeout=HEDGE_S, return_when=cf.FIRST_COMPLETED)
            if not feitos:
                if len(pend) < 2:
                    if pos[0] < len(fila):
                        lancar()                              # a atual esta lenta: a proxima corre junto
                    elif duplicadas[0] < 1 and fila:
                        duplicadas[0] += 1                    # sem mais candidatos: repete o ultimo (os modelos preview as vezes travam e a repeticao responde em ~6 s)
                        fila.append(fila[pos[0] - 1])
                        lancar()
                continue
            for f in feitos:
                modelo = pend.pop(f)
                try:
                    pcm = f.result()
                except _Falha as e:
                    erros.append(e)
                    if e.motivo == "lento" and refeitas.get(modelo, 0) < 1:      # travou: tenta de novo o mesmo modelo UMA vez
                        refeitas[modelo] = refeitas.get(modelo, 0) + 1
                        fila.insert(pos[0], next(x for x in fila[:pos[0]] if x[0] == modelo))
                    if pos[0] < len(fila) and not pend:
                        lancar()
                    continue
                wav = polir(_para_wav(pcm))
                ULTIMO["motor"] = f"gemini:{modelo}:{voz}"
                if usar_cache:
                    arq.write_bytes(wav)
                return wav
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    motivos = {e.motivo for e in erros}
    motivo = "cota" if motivos == {"cota"} else "lento" if "lento" in motivos else "rede" if "rede" in motivos else "outro"
    raise VozErro("sem voz natural agora (" + "; ".join(str(e) for e in erros[:3]) + ")", motivo)
