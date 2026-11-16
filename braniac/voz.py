# -*- coding: utf-8 -*-
"""Voz local do Jarvis: ouvir (faster-whisper) e falar (Piper, voz masculina faber). Tudo no CPU."""
import io, os as _os, re, threading, wave
from pathlib import Path

MODELOS = Path(__file__).parent / "modelos"
WHISPER = MODELOS / "whisper-small"
VOZ = MODELOS / "piper" / "pt" / "pt_BR" / "faber" / "medium" / "pt_BR-faber-medium.onnx"

_lock = threading.Lock()
_whisper = None


import contextvars
_AGENTE = contextvars.ContextVar("agente_da_voz", default=None)   # 16/11: quem esta falando (None/'jarvis' = Jarvis); ver vozes_agentes.py


def _escolha():
    """16/11: voz escolhida na pagina /vozes (data/voz_escolhida.json): {"motor","genero","vozes":{motor: voz}, "agentes":{id:{mesmo formato}}}.
    O Jarvis fica no topo do arquivo (formato antigo); os outros agentes ficam em "agentes"."""
    import json
    from .store import DATA   # lido na hora: os testes trocam o DATA
    try:
        d = json.loads((DATA / "voz_escolhida.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    ag = _AGENTE.get()
    return (d.get("agentes") or {}).get(ag, {}) if ag and ag != "jarvis" else d


def _escolha_voz(motor):
    return (_escolha().get("vozes") or {}).get(motor) or None


_GENERO_USADO = contextvars.ContextVar("genero_da_reserva", default=None)   # 16/11: genero da voz de RESERVA que falou (None = a primaria)


def _wav_cheio(wav):
    """Audio vazio ou quase vazio conta como falha (motor que 'responde' sem som nao pode passar)."""
    if not wav or (wav[:4] == b"RIFF" and len(wav) < 1000):   # WAV so com cabecalho (~0,02 s de som)
        raise RuntimeError("audio vazio")
    return wav


def _wav_com_voz(motor, voz_id, texto):
    """Gera com um motor e uma voz exatos (usado pelas vozes de reserva de /vozes)."""
    if motor == "kokoro":
        return _kokoro_wav(texto, voz_nome=voz_id)
    if motor == "piper":
        return _falar_wav_piper(texto, voz_id=voz_id)
    if motor == "edge":
        return _edge_wav(texto, voz_nome=voz_id)
    if motor == "gemini":
        return _gemini_wav(texto, voz_nome=voz_id)
    raise ValueError(f"motor sem reserva: {motor}")


def _log_voz(linha):
    try:
        from .store import DATA
        with (DATA / "voz.log").open("a", encoding="utf-8") as f:
            f.write(f"{_time.strftime('%Y-%m-%d %H:%M:%S')} | {_AGENTE.get() or 'jarvis'} | {linha}\n")
    except OSError:
        pass


MOTOR_WHISPER = ""   # 'gpu' (placa de video) ou 'cpu': diagnostico


def _dll_cuda():
    """cuBLAS/cuDNN instalados pelo pip (nvidia-cublas-cu12, nvidia-cudnn-cu12): o Windows precisa saber onde estao as DLLs."""
    import os, site
    for sp in site.getsitepackages():
        for sub in ("cublas", "cudnn"):
            d = os.path.join(sp, "nvidia", sub, "bin")
            if os.path.isdir(d):
                try:
                    os.add_dll_directory(d)
                except (OSError, AttributeError):
                    pass
                os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")


def _carregar_whisper():
    """Whisper na GPU (float16) se der; senao CPU com todos os nucleos. Testa de verdade com uma inferencia curta (as DLLs so carregam ai)."""
    global MOTOR_WHISPER
    import numpy as np
    from faster_whisper import WhisperModel
    _dll_cuda()
    try:
        m = WhisperModel(str(WHISPER), device="cuda", compute_type="float16")
        list(m.transcribe(np.zeros(16000, dtype=np.float32), language="pt", beam_size=1)[0])
        MOTOR_WHISPER = "gpu"
        return m
    except Exception:
        MOTOR_WHISPER = "cpu"
        import os
        return WhisperModel(str(WHISPER), device="cpu", compute_type="int8", cpu_threads=max(4, (os.cpu_count() or 8) // 2))


def preaquecer_whisper():
    """Carrega o Whisper agora (em segundo plano), para a primeira frase falada nao esperar o carregamento."""
    global _whisper
    with _lock:
        if _whisper is None:
            _whisper = _carregar_whisper()


def transcrever(caminho, rapido=False):
    """Audio (ogg/opus do Telegram, wav, mp3...) -> texto em portugues. rapido=True: frases curtas da conversa por voz (sem VAD extra)."""
    global _whisper
    with _lock:
        if _whisper is None:
            _whisper = _carregar_whisper()
        segs, _ = _whisper.transcribe(str(caminho), language="pt", vad_filter=not rapido, beam_size=1, without_timestamps=True,
                                       condition_on_previous_text=False,
                                       initial_prompt="Jarvis, Braniac, Dono, Parceira, Claudinho, Airbnb, WhatsApp.")
        return " ".join(s.text.strip() for s in segs).strip()


import time as _time

# Vozes masculinas do Gemini TTS. Achird = 'amigavel' (padrao); Umbriel = 'tranquila'; Charon = 'informativa'; Puck = 'animada'.
VOZES_MASCULINAS = {"Achird", "Umbriel", "Charon", "Puck", "Orus", "Fenrir", "Zubenelgenubi", "Algenib", "Alnilam",
                    "Enceladus", "Iapetus", "Sadaltager", "Rasalgethi", "Schedar", "Sadachbia"}
# Ordem: o mais natural primeiro. O 2.5 estava sem cota (429) e por isso a voz caia no Piper robotico; o 3.8 le o estilo em voz alta.
MODELOS_TTS = ["gemini-3.1-flash-tts-preview", "gemini-2.5-flash-preview-tts", "gemini-2.5-pro-preview-tts"]
ESTILO_BASE = ("Fale em português do Brasil em tom sério, calmo e sóbrio, como um assistente profissional e seguro de si: "
               "voz firme, ritmo pausado e natural, sem empolgação, sem entusiasmo exagerado e sem soar sorridente")
_cooldown = {}      # modelo -> ate quando evitar (cota esgotada/erro)
ULTIMO_MOTOR = ""   # diagnostico: qual motor falou por ultimo ('gemini:modelo:voz' ou 'piper:motivo')


def _cfg_voz():
    import json
    cfg = {"nome": "Achird", "modelos": list(MODELOS_TTS), "estilo": ESTILO_BASE}
    try:
        cfg.update(json.loads((Path(__file__).parent / "providers.json").read_text(encoding="utf-8-sig")).get("voz", {}))
    except (OSError, ValueError):
        pass
    try:
        from . import contexto
        cfg["nome"] = contexto.voz_nome() or cfg["nome"]
    except Exception:
        pass
    return cfg


def _estilo(cfg):
    """Estilo falado + o toque do nivel de humor do Jarvis (so aparece no tom da voz, nao no texto)."""
    try:
        from . import contexto
        humor = contexto.humor()
    except Exception:
        humor = 0
    extra = ", com leve ironia ocasional" if humor >= 60 else ""   # Dono (05/10): a voz estava feliz demais; so humor alto muda o tom
    return cfg["estilo"] + extra


def polir_wav(wav_bytes):
    """Acabamento do audio: tira silencio das pontas, normaliza o volume e suaviza o inicio/fim (sem cliques)."""
    import numpy as np
    with wave.open(io.BytesIO(wav_bytes)) as w:
        taxa, canais = w.getframerate(), w.getnchannels()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)
    if x.size == 0 or canais != 1:
        return wav_bytes
    pico = float(np.abs(x).max())
    if pico < 50:
        return wav_bytes
    idx = np.where(np.abs(x) > pico * 0.006)[0]
    if idx.size:
        x = x[max(0, idx[0] - int(taxa * 0.12)): min(x.size, idx[-1] + int(taxa * 0.18))]
    x = x * ((0.9 * 32767) / max(float(np.abs(x).max()), 1.0))
    n = int(taxa * 0.008)
    if x.size > 2 * n:
        x[:n] *= np.linspace(0, 1, n)
        x[-n:] *= np.linspace(1, 0, n)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(np.clip(x, -32768, 32767).astype(np.int16).tobytes())
    return buf.getvalue()


def _plausivel(texto, segundos):
    """Detecta modelo que LEU o estilo em voz alta (audio longo demais para o texto): ~2,5 palavras/s e a media da fala."""
    palavras = max(1, len(texto.split()))
    return segundos <= palavras / 1.3 + 3.5


def _gemini_wav(texto, voz_nome=None, timeout=60, modelos=None, estilo=None):
    """Voz natural do Gemini (Google): tenta os modelos em ordem, pula os sem cota, rejeita audio suspeito e poli o resultado."""
    import base64, os, requests
    global ULTIMO_MOTOR
    # 16/11: as GEMINI_TTS_KEY* (variaveis do Windows) funcionam; a GEMINI_API_KEY do .env estava invalida (HTTP 400). Valem primeiro.
    nomes_chave = ("GEMINI_TTS_KEY", "GEMINI_TTS_KEY_2", "GEMINI_TTS_KEY_3", "GEMINI_TTS_KEY_4", "GEMINI_TTS_KEY_5", "GEMINI_API_KEY", "GEMINI_API_KEY_2")
    chaves = [k for k in dict.fromkeys(os.environ.get(n, "").strip() for n in nomes_chave) if k]
    if not chaves:
        raise RuntimeError("sem GEMINI_API_KEY")
    cfg = _cfg_voz()
    nome = voz_nome or _escolha_voz("gemini") or cfg["nome"]
    prompt = f"{estilo or (_escolha().get('ajustes') or {}).get('estilo') or _estilo(cfg)}: {texto}"   # 16/11: o estilo falado pode ser escrito em /vozes, por agente
    erros = []
    for modelo in modelos or cfg["modelos"]:
        if _cooldown.get(modelo, 0) > _time.time():
            erros.append(f"{modelo}: em descanso")
            continue
        try:
            for chave in chaves:   # a 2a chave (outro projeto Google) tem cota propria: so entra se a 1a estourar
                r = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent",
                    headers={"x-goog-api-key": chave},
                    json={"contents": [{"parts": [{"text": prompt}]}],
                          "generationConfig": {"responseModalities": ["AUDIO"],
                                               "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": nome}}}}},
                    timeout=timeout)
                if r.status_code != 429:
                    break
        except requests.RequestException as e:
            erros.append(f"{modelo}: rede {str(e)[:40]}")
            continue
        if r.status_code != 200:
            _cooldown[modelo] = _time.time() + (900 if r.status_code == 429 else 120)  # sem cota: nao insiste por 15 min
            erros.append(f"{modelo}: HTTP {r.status_code}")
            continue
        try:
            pcm = base64.b64decode(r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
        except (KeyError, IndexError, ValueError):
            erros.append(f"{modelo}: resposta vazia")
            continue
        if not _plausivel(texto, len(pcm) / 48000):
            erros.append(f"{modelo}: audio longo demais (leu o estilo?)")
            continue
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(24000)
            w.writeframes(pcm)
        ULTIMO_MOTOR = f"gemini:{modelo}:{nome}"
        return polir_wav(buf.getvalue())
    raise RuntimeError("; ".join(erros))


VOZ_EDGE = "pt-BR-AntonioNeural"   # neural da Microsoft, sem chave e sem cota diaria: plano B natural quando o Gemini estoura (free tier = 10/dia por modelo)


VOZ_ELEVEN = "2CECaLAGTS5NRGxgbcxr"      # voz escolhida pelo Dono (15/10/2026); troque o id para mudar a voz
MODELO_ELEVEN = "eleven_multilingual_v2"  # multilingue: fala portugues


VOZ_KOKORO = "pm_alex"                   # vozes em portugues: pm_alex, pm_santa (masculinas) e pf_dora (feminina)
_KOKORO = None


def _rafael_wav(texto):
    """20/10: voz do RAFAEL (Pocket TTS, local, voz 'rafael' em portugues). Roda no venv proprio data/ptts (torch nao entra no Python do Braniac).
    shortcut: um processo por fala (~20 s carregando o modelo), serve para audio de WhatsApp e nao para conversa ao vivo; trocar por 'pocket-tts serve' se precisar de rapidez."""
    import os, subprocess, tempfile
    py = Path(__file__).parent / "data" / "ptts" / "Scripts" / "python.exe"
    if not py.exists():
        raise RuntimeError("venv do Pocket TTS ausente")
    out = Path(tempfile.mkdtemp()) / "rafael.wav"
    try:
        r = subprocess.run([str(py), "-m", "pocket_tts", "generate", "--voice", "rafael", "--language", "portuguese", "--text", texto, "--output-path", str(out), "--quiet"],
                           capture_output=True, timeout=240, env={**os.environ, "PYTHONUTF8": "1"}, creationflags=0x08000000)
        if r.returncode or not out.exists():
            raise RuntimeError((r.stderr or b"").decode("utf-8", "replace")[-120:])
        return out.read_bytes()
    finally:
        out.unlink(missing_ok=True)


def _xtts_wav(texto, tempos=None):
    """15/11: XTTS-v2 (Coqui) na placa de video, no venv proprio data/xtts. Clona a voz de data/xtts/referencia.wav (uso pessoal: licenca CPML aceita pelo Dono em 15/11/2026).
    shortcut: um processo por fala (carrega o modelo todo vez); se virar a voz principal, trocar por um servidor que fique com o modelo na placa.
    `tempos` (dict opcional) recebe carga_s/geracao_s para medir."""
    import json, os, subprocess, tempfile
    base = Path(__file__).parent
    py, ref = base / "data" / "xtts" / "Scripts" / "python.exe", base / "data" / "xtts" / "referencia.wav"
    if not py.exists() or not ref.exists():
        raise RuntimeError("venv ou referencia do XTTS ausentes")
    out = Path(tempfile.mkdtemp()) / "xtts.wav"
    try:
        r = subprocess.run([str(py), str(base / "xtts_gera.py"), "--texto", texto, "--ref", str(ref), "--saida", str(out)],
                           capture_output=True, timeout=300, env={**os.environ, "PYTHONUTF8": "1", "XTTS_LICENCA_OK": "1"}, creationflags=0x08000000)
        if r.returncode or not out.exists():
            raise RuntimeError((r.stderr or b"").decode("utf-8", "replace")[-160:])
        if tempos is not None:
            try:
                tempos.update(json.loads((r.stdout or b"").decode("utf-8", "replace").strip().splitlines()[-1]))
            except (ValueError, IndexError):
                pass
        return out.read_bytes()
    finally:
        out.unlink(missing_ok=True)


def _voicebox_wav(texto):
    """16/11: Voicebox (Qwen3-TTS, local) pela API em 127.0.0.1:17493; opt-in com BRANIAC_VOZ_VOICEBOX=1 e VOICEBOX_PERFIL=<id do perfil>.
    shortcut: servidor em CPU (build do instalador), lento; trocar pela build CUDA se a voz virar a principal."""
    import json, time, urllib.request
    base = _os.environ.get("VOICEBOX_URL", "http://127.0.0.1:17493").rstrip("/")
    perfil = _os.environ.get("VOICEBOX_PERFIL", "").strip()
    if not perfil:
        raise RuntimeError("voicebox: VOICEBOX_PERFIL ausente")

    def chamar(rota, corpo=None, bruto=False):
        req = urllib.request.Request(base + rota, data=None if corpo is None else json.dumps(corpo).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            dado = r.read()
        return dado if bruto else json.loads(dado)

    ger = chamar("/generate", {"profile_id": perfil, "text": texto, "language": "pt", "engine": "qwen", "model_size": "0.6B"})
    for _ in range(120):
        st = chamar(f"/generate/{ger['id']}/status")
        if str(st.get("status")) == "completed":
            return chamar(f"/audio/{ger['id']}", bruto=True)
        if str(st.get("status")) in ("failed", "cancelled"):
            raise RuntimeError(f"voicebox: {str(st.get('error'))[:100]}")
        time.sleep(2)
    raise RuntimeError("voicebox: demorou demais")


def _kokoro_wav(texto, voz_nome=None):
    """Kokoro (modelo neural LOCAL, grátis e sem limite de uso; github.com/nazdridoy/kokoro-tts). Muito mais natural que o Piper, que era a reserva robotica.
    Precisa de braniac/modelos/kokoro/{kokoro-v1.0.onnx,voices-v1.0.bin}; sem eles levanta e a cadeia segue."""
    import os
    global _KOKORO, ULTIMO_MOTOR
    pasta = Path(__file__).parent / "modelos" / "kokoro"
    modelo, vozes = pasta / "kokoro-v1.0.onnx", pasta / "voices-v1.0.bin"
    if not modelo.exists() or not vozes.exists():
        raise RuntimeError("kokoro: modelos nao instalados")
    if _KOKORO is None:
        from kokoro_onnx import Kokoro
        _KOKORO = Kokoro(str(modelo), str(vozes))
    voz = voz_nome or os.environ.get("KOKORO_VOZ", "").strip() or _escolha_voz("kokoro") or VOZ_KOKORO
    amostras, taxa = _KOKORO.create(texto, voice=voz, speed=1.0, lang="pt-br")
    import numpy as np
    pcm = (np.clip(amostras, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(taxa))
        w.writeframes(pcm)
    ULTIMO_MOTOR = f"kokoro:{voz}"
    return buf.getvalue()


def _eleven_wav(texto, timeout=45):
    """ElevenLabs (a voz mais natural). So roda se houver ELEVENLABS_API_KEY no braniac/.env; sem chave, levanta e a cadeia segue."""
    import os
    import requests
    global ULTIMO_MOTOR
    chave = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not chave:
        from .router import carregar_env
        carregar_env()
        chave = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not chave:
        raise RuntimeError("sem ELEVENLABS_API_KEY")
    voz = os.environ.get("ELEVENLABS_VOICE_ID", "").strip() or VOZ_ELEVEN
    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voz}",
        params={"output_format": "pcm_24000"},
        headers={"xi-api-key": chave, "Content-Type": "application/json"},
        json={"text": texto, "model_id": MODELO_ELEVEN,
              "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.0, "use_speaker_boost": True}},
        timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"elevenlabs HTTP {r.status_code}: {r.text[:120]}")
    pcm = r.content
    if len(pcm) < 2000:
        raise RuntimeError("elevenlabs: audio vazio")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:        # PCM 16-bit mono 24 kHz -> WAV
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(pcm)
    ULTIMO_MOTOR = f"elevenlabs:{voz}"
    return buf.getvalue()


def _edge_wav(texto, timeout=40, voz_nome=None):
    import asyncio, edge_tts, av
    global ULTIMO_MOTOR
    vn = voz_nome or _escolha_voz("edge") or VOZ_EDGE

    async def _go():
        buf = b""
        async for ch in edge_tts.Communicate(texto, vn, rate="-3%").stream():
            if ch["type"] == "audio":
                buf += ch["data"]
        return buf
    mp3 = asyncio.run(asyncio.wait_for(_go(), timeout))
    if len(mp3) < 2000:
        raise RuntimeError("edge: audio vazio")
    ent = av.open(io.BytesIO(mp3))
    saida = io.BytesIO()
    with wave.open(saida, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        res = av.AudioResampler(format="s16", layout="mono", rate=24000)
        for fr in ent.decode(audio=0):
            for f in res.resample(fr):
                w.writeframes(bytes(f.planes[0])[: f.samples * 2])
    ULTIMO_MOTOR = f"edge:{vn}"
    return polir_wav(saida.getvalue())


_EMOJI = re.compile("[\U0001F000-\U0001FAFF←-⇿⌀-⏿☀-➿⬀-⯿️‍]+")


def limpar_para_fala(texto):
    """Tira o que nao se fala: links, markdown, emojis, marcadores de lista. Mantem so o que soa natural."""
    t = re.sub(r"https?://\S+|www\.\S+", "", str(texto))
    t = t.replace("**", "").replace("__", "").replace("`", "").replace("«", "").replace("»", "")
    t = _EMOJI.sub("", t)
    t = re.sub(r"(?m)^\s*[-•*]\s+", "", t)
    t = re.sub(r"!+", ".", t)   # exclamacao vira ponto: a voz soa mais seria e menos empolgada (pedido do Dono)
    from .tratamento import corrigir
    return re.sub(r"\s+", " ", corrigir(t)).strip()   # 'Parceira'/'Parceira' -> 'Parceira' tambem na fala


GRAVE = 0.01   # voz 1% mais grave (o Dono testou 20% e 5%; agora 1%). 0 = voz original


def mais_grave(wav_bytes, fracao=None):
    """Abaixa o TOM da voz em `fracao` (0,20 = 20% mais grave, ~3,9 semitons) sem mudar a velocidade da fala. Se algo falhar, devolve o audio original."""
    fracao = GRAVE if fracao is None else fracao
    if not wav_bytes or fracao <= 0:
        return wav_bytes
    try:
        import math
        import numpy as np
        from pedalboard import Pedalboard, PitchShift
        with wave.open(io.BytesIO(wav_bytes)) as w:
            taxa, canais, n = w.getframerate(), w.getnchannels(), w.getnframes()
            x = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768.0
        x = x.reshape(-1, canais).T if canais > 1 else x.reshape(1, -1)
        y = Pedalboard([PitchShift(semitones=12 * math.log2(1.0 - fracao))])(x, taxa)
        pico = float(np.abs(y).max())
        if pico > 0.98:
            y = y * (0.98 / pico)                    # sem estourar
        pcm = np.clip(y.T.reshape(-1) * 32768.0, -32768, 32767).astype(np.int16).tobytes()
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(canais)
            w.setsampwidth(2)
            w.setframerate(taxa)
            w.writeframes(pcm)
        return buf.getvalue()
    except Exception:
        return wav_bytes


def aplicar_ajustes(wav_bytes, aj):
    """16/11: ajustes de voz por agente, depois que o motor falou. aj = {"velocidade": 0,7-1,3 (1 = normal), "tom": semitons (-6 a +3, negativo = mais grave), "calor": 0-100 (graves mais cheios, agudos mais macios)}.
    O "estilo" (texto) so vale no Gemini e e tratado no _gemini_wav. Se algo falhar, devolve o audio original."""
    aj = aj or {}
    vel, tom, calor = float(aj.get("velocidade") or 1.0), float(aj.get("tom") or 0.0), float(aj.get("calor") or 0.0)
    if not wav_bytes or (abs(vel - 1.0) < 0.01 and abs(tom) < 0.05 and calor < 1):
        return wav_bytes
    try:
        import numpy as np
        import pedalboard as pb
        vel, tom, calor = min(max(vel, 0.7), 1.3), min(max(tom, -6.0), 3.0), min(max(calor, 0.0), 100.0)
        with wave.open(io.BytesIO(wav_bytes)) as w:
            taxa, canais, n = w.getframerate(), w.getnchannels(), w.getnframes()
            x = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768.0
        x = x.reshape(-1, canais).T if canais > 1 else x.reshape(1, -1)
        if abs(vel - 1.0) >= 0.01 or abs(tom) >= 0.05:
            x = pb.time_stretch(x, taxa, stretch_factor=vel, pitch_shift_in_semitones=tom)
        if calor >= 1:
            k = calor / 100.0
            x = pb.Pedalboard([pb.LowShelfFilter(cutoff_frequency_hz=220, gain_db=4.0 * k), pb.HighShelfFilter(cutoff_frequency_hz=5500, gain_db=-4.0 * k),
                               pb.Compressor(threshold_db=-22, ratio=1.0 + 2.0 * k)])(x, taxa)
        pico = float(np.abs(x).max())
        if pico > 0.98:
            x = x * (0.98 / pico)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(canais)
            w.setsampwidth(2)
            w.setframerate(taxa)
            w.writeframes(np.clip(x.T.reshape(-1) * 32768.0, -32768, 32767).astype(np.int16).tobytes())
        return buf.getvalue()
    except Exception:
        return wav_bytes


def falar_wav(texto, permitir_nuvem=True, rapido=False, agente=None):
    """Texto -> WAV com voz masculina, ja 20% mais grave (GRAVE). `agente` ('alma', ...) usa a voz escolhida para ele em /vozes (ver vozes_agentes.py)."""
    if agente and agente != "jarvis":
        token = _AGENTE.set(agente)
        try:
            return falar_wav(texto, permitir_nuvem, rapido)
        finally:
            _AGENTE.reset(token)
    partes = _partes(texto)
    wavs = [_falar_wav_motores(p, permitir_nuvem, rapido) for p in partes]
    wav = wavs[0] if len(wavs) == 1 else _juntar_wavs(wavs)
    wav = wav if ULTIMO_MOTOR == "rafael" or _so_feminina() or (_GENERO_USADO.get() or _escolha().get("genero")) == "F" else mais_grave(wav)   # voz feminina escolhida: nao engrossar; a do Rafael ja e grave
    return aplicar_ajustes(wav, _escolha().get("ajustes"))


def falar_wav_voz_unica(texto):
    """Narracao de VIDEO (Dono Estudio): a MESMA voz do comeco ao fim. Cada motor tenta o texto inteiro; se falha em qualquer trecho,
    joga fora o que fez e o proximo motor refaz TUDO (o falar_wav comum troca de motor trecho a trecho). Devolve (wav, motor)."""
    from .router import SENSIVEL
    partes = [limpar_para_fala(p) or "Certo." for p in _partes(texto)]
    nuvem = [] if any(SENSIVEL.search(p) for p in partes) else (
        [("eleven", _eleven_wav)]
        + [(f"gemini:{m}", lambda p, m=m: _gemini_wav(p, modelos=[m])) for m in _cfg_voz()["modelos"]]   # modelo fixo: modelos diferentes soam diferente
        + [("edge", _edge_wav)])
    rafael = [("rafael", _rafael_wav)] if _os.environ.get("BRANIAC_VOZ_RAFAEL") == "1" else []
    erros = []
    for nome, motor in rafael + nuvem + [("kokoro", _kokoro_wav), ("piper", _falar_wav_piper)]:
        try:
            wavs = [motor(p) for p in partes]
        except Exception as e:
            erros.append(f"{nome}: {str(e)[:80]}")
            continue
        wav = wavs[0] if len(wavs) == 1 else _juntar_wavs(wavs)
        return (wav if nome == "rafael" else mais_grave(wav)), nome
    raise RuntimeError("nenhum motor narrou o texto inteiro: " + "; ".join(erros))


def _partes(texto, limite=800):
    """Textos longos viram pedacos de ate ~800 caracteres (fim de frase): o TTS do Gemini corta o audio depois da 1a frase quando o texto e muito longo (23/10/2026)."""
    frases, partes, atual = re.split(r"(?<=[.!?])\s+", texto.strip()), [], ""
    for f in frases:
        if atual and len(atual) + len(f) > limite:
            partes.append(atual)
            atual = ""
        atual = f"{atual} {f}".strip()
    return partes + [atual] if atual else [texto]


def _juntar_wavs(wavs):
    """Concatena WAVs do mesmo formato (o da 1a parte manda)."""
    saida = io.BytesIO()
    with wave.open(saida, "wb") as w:
        for i, b in enumerate(wavs):
            with wave.open(io.BytesIO(b)) as r:
                if i == 0:
                    w.setparams(r.getparams())
                w.writeframes(r.readframes(r.getnframes()))
    return saida.getvalue()


def _so_feminina():
    """16/11: agente que NUNCA pode falar com voz masculina (a Alma: `so_genero: "F"` em vozes_agentes.PADRAO)."""
    ag = _AGENTE.get()
    if not ag or ag == "jarvis":
        return False
    try:
        from . import vozes_agentes
        return any(a["id"] == ag and a.get("so_genero") == "F" for a in vozes_agentes.agentes())
    except Exception:
        return False


def _falar_feminina(texto, permitir_nuvem, motivo):
    """Ordem de sempre, mas SO com voz feminina: Gemini (cota por chave), Edge e Kokoro. O Piper e o Rafael sao masculinos e nao entram.
    Se nenhuma falar, levanta: quem pediu manda so o texto (melhor sem audio do que com voz de homem)."""
    from .router import SENSIVEL
    global ULTIMO_MOTOR
    nuvem = permitir_nuvem and not SENSIVEL.search(texto)
    tentativas = ([("gemini", lambda: _gemini_wav(texto, voz_nome=_escolha_voz("gemini") or "Kore")),
                   ("edge", lambda: _edge_wav(texto, voz_nome=_escolha_voz("edge") or "pt-BR-FranciscaNeural"))] if nuvem else []) + \
                  [("kokoro", lambda: _kokoro_wav(texto, voz_nome=_escolha_voz("kokoro") or "pf_dora"))]
    erros = [motivo] if motivo else []
    for nome, fn in tentativas:
        try:
            wav = fn()
            _log_voz(f"FEMININA {nome} | caiu: {'; '.join(erros)[:200]}") if erros else None
            return wav
        except Exception as e:
            erros.append(f"{nome}: {str(e)[:80]}")
    raise RuntimeError("nenhuma voz feminina falou: " + "; ".join(erros))


def _falar_wav_motores(texto, permitir_nuvem=True, rapido=False):
    """Texto -> WAV com voz masculina. Gemini (natural) primeiro; Piper local (mais robotico) so se o Google falhar ou o texto for sensivel."""
    from .router import SENSIVEL
    global ULTIMO_MOTOR
    texto = limpar_para_fala(texto) or "Certo."
    motivo = "texto sensivel (fica local)"
    if not rapido and not _so_feminina() and _os.environ.get("BRANIAC_VOZ_RAFAEL") == "1":   # 20/10: Rafael PAUSADO a pedido do Dono (volta a voz do Gemini); ligar com BRANIAC_VOZ_RAFAEL=1 no .env
        try:
            wav = _rafael_wav(texto)
            ULTIMO_MOTOR = "rafael"
            return wav
        except Exception as e:
            motivo = f"rafael: {str(e)[:80]}"
    if not rapido and not _so_feminina() and _os.environ.get("BRANIAC_VOZ_XTTS") == "1":   # 15/11: XTTS-v2 local (opt-in, como o Rafael)
        try:
            wav = _xtts_wav(texto)
            ULTIMO_MOTOR = "xtts"
            return wav
        except Exception as e:
            motivo = f"xtts: {str(e)[:80]}"
    if not rapido and not _so_feminina() and _os.environ.get("BRANIAC_VOZ_VOICEBOX") == "1":   # 16/11: Voicebox local (opt-in)
        try:
            wav = _voicebox_wav(texto)
            ULTIMO_MOTOR = "voicebox"
            return wav
        except Exception as e:
            motivo = f"voicebox: {str(e)[:80]}"
    pref = _escolha().get("motor")   # 16/11: o motor que o Dono escolheu em /vozes tenta primeiro (online so se o texto nao for sensivel)
    _GENERO_USADO.set(None)
    if pref in ("kokoro", "piper", "edge", "gemini") and not rapido and not (pref in ("edge", "gemini") and (not permitir_nuvem or SENSIVEL.search(texto))):
        try:
            wav = _wav_cheio(globals()[{"piper": "_falar_wav_piper"}.get(pref, f"_{pref}_wav")](texto))   # nome montado na hora: o motor escolhido sempre vale o que esta no modulo agora
            if pref == "piper":
                ULTIMO_MOTOR = "piper:escolhido"
            return wav
        except Exception as e:
            motivo = f"{pref}: {str(e)[:80]}"
    if pref and not rapido:   # 16/11: a primaria caiu (cota, fora do ar, erro, audio vazio) -> secundaria, depois terciaria (escolhidas em /vozes)
        for r in (_escolha().get("reservas") or [])[:2]:
            m, v = (r or {}).get("motor"), (r or {}).get("voz")
            if m not in ("kokoro", "piper", "edge", "gemini") or not v or (_so_feminina() and (r or {}).get("genero") != "F") or (m in ("edge", "gemini") and (not permitir_nuvem or SENSIVEL.search(texto))):
                continue
            try:
                wav = _wav_cheio(_wav_com_voz(m, v, texto))
            except Exception as e:
                motivo += f"; reserva {m}:{v}: {str(e)[:60]}"
                continue
            _GENERO_USADO.set(r.get("genero"))
            _log_voz(f"RESERVA {m}:{v} | caiu: {motivo}")
            return wav
        _log_voz(f"PRIMARIA E RESERVAS caíram, ordem de sempre | {motivo}")
    if _so_feminina():
        return _falar_feminina(texto, permitir_nuvem, motivo)
    if permitir_nuvem and not SENSIVEL.search(texto):
        try:    # 15/10: ElevenLabs e a 1a escolha quando ha chave (voz escolhida pelo Dono); sem chave, cai para os motores de sempre
            return _eleven_wav(texto)
        except Exception as e:
            motivo = f"eleven: {str(e)[:80]}"
        if rapido:   # conversa por voz ao vivo: a voz neural da Microsoft (~1 s) em vez do Gemini TTS (5 a 10 s)
            try:
                return _edge_wav(texto)
            except Exception:
                pass
        try:
            return _gemini_wav(texto)
        except Exception as e:
            motivo = str(e)[:160]  # Google instavel/sem cota
        if not SENSIVEL.search(texto):
            try:
                return _edge_wav(texto)
            except Exception as e:
                motivo += f"; edge: {str(e)[:60]}"
    try:    # 15/10: Kokoro local (neural, grátis) antes do Piper robótico; também atende texto sensível sem sair do PC
        return _kokoro_wav(texto)
    except Exception as e:
        motivo += f"; kokoro: {str(e)[:60]}"
    ULTIMO_MOTOR = f"piper:{motivo}"
    try:  # deixa rastro: voz robotica quase sempre e fallback silencioso
        from .store import DATA
        with (DATA / "voz.log").open("a", encoding="utf-8") as f:
            f.write(f"{_time.strftime('%Y-%m-%d %H:%M:%S')} | PIPER (robotico) | {motivo}\n")
    except OSError:
        pass
    return _falar_wav_piper(texto)


def piper_caminho(voz_id):
    """'faber/medium' -> .onnx do Piper em modelos/piper/pt/pt_BR/."""
    nome, qual = voz_id.split("/")
    return MODELOS / "piper" / "pt" / "pt_BR" / nome / qual / f"pt_BR-{nome}-{qual}.onnx"


_PIPERS = {}


def _falar_wav_piper(texto, voz_id=None):
    """Voz local do Piper (padrao: faber; a escolhida em /vozes vale se nao vier voz_id)."""
    voz_id = voz_id or _escolha_voz("piper") or "faber/medium"
    with _lock:
        if voz_id not in _PIPERS:
            from piper import PiperVoice
            _PIPERS[voz_id] = PiperVoice.load(str(piper_caminho(voz_id)))
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            _PIPERS[voz_id].synthesize_wav(texto, w)
        return buf.getvalue()


def wav_para_ogg_opus(wav_bytes):
    """Telegram so mostra como 'mensagem de voz' se for OGG/Opus. Usa o PyAV que veio com o faster-whisper."""
    import av
    entrada = av.open(io.BytesIO(wav_bytes))
    saida_buf = io.BytesIO()
    saida = av.open(saida_buf, mode="w", format="ogg")
    fluxo = saida.add_stream("libopus", rate=48000)
    fluxo.layout = "mono"
    rs = av.AudioResampler(format="s16", layout="mono", rate=48000)
    for frame in entrada.decode(audio=0):
        for f in rs.resample(frame):
            for pkt in fluxo.encode(f):
                saida.mux(pkt)
    for pkt in fluxo.encode(None):
        saida.mux(pkt)
    saida.close()
    return saida_buf.getvalue()


def falar_ogg(texto):
    return wav_para_ogg_opus(falar_wav(texto))
