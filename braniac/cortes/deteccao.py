# -*- coding: utf-8 -*-
"""Deteccao de momentos virais SEM IA: pico de volume (audio) + pico de mensagens no chat (com peso para memes de hype).

Cada sinal vira um z-score robusto em relacao a vizinhanca (5 min), entao uma live que e sempre barulhenta nao vira
"tudo pico": conta o que destoa do resto daquele trecho."""
import json, re, subprocess, sys
import numpy as np

SEM_JANELA = 0x08000000 if sys.platform == "win32" else 0
HYPE = re.compile(r"\b(kekw|lul|lmao|omegalul|pog|pogchamp|poggers|pogu|monkas|pepelaugh|lol|clip|clipa|clipou|w+|gg|aaa+|nossa|caraca|"
                   r"meu deus|mds|socorro)\b|k{4,}|\?{3,}|!{3,}|hah(a)+|rsrs", re.I)
IGNORAR_INICIO_S = 60  # tela de "comecando" nao e momento viral


def energia_por_segundo(arquivo, sr=8000):
    """Volume (dBFS) de cada segundo do audio, lendo o arquivo em streaming pelo ffmpeg (aguenta live de horas)."""
    p = subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-i", str(arquivo), "-vn", "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"],
                         stdout=subprocess.PIPE, creationflags=SEM_JANELA)
    db, bloco = [], sr * 2 * 60
    resto = b""
    while True:
        dado = p.stdout.read(bloco)
        if not dado:
            break
        dado = resto + dado
        n = len(dado) // (sr * 2) * (sr * 2)
        dado, resto = dado[:n], dado[n:]
        if n:
            a = np.frombuffer(dado, dtype=np.int16).astype(np.float32).reshape(-1, sr) / 32768.0
            db.extend(20 * np.log10(np.sqrt((a ** 2).mean(axis=1)) + 1e-6))
    p.wait()
    return np.array(db, dtype=np.float32)


def chat_por_segundo(arquivo_jsonl, total_s, atraso_s=6):
    """Mensagens por segundo (memes de hype contam 2), deslocadas `atraso_s` para tras: o chat reage depois do lance."""
    v = np.zeros(int(total_s) + 1, dtype=np.float32)
    hype = {}
    try:
        with open(arquivo_jsonl, encoding="utf-8") as f:
            for ln in f:
                try:
                    d = json.loads(ln)
                except ValueError:
                    continue
                i = int(float(d.get("t", 0)) - atraso_s)
                if 0 <= i < len(v):
                    achou = HYPE.findall(d.get("msg", ""))
                    v[i] += 2.0 if achou else 1.0
                    if achou:
                        hype[i] = hype.get(i, 0) + 1
    except OSError:
        return None, {}
    return (v if v.sum() >= 30 else None), hype  # chat quase vazio nao e sinal confiavel


def _media_movel(x, n):
    if n <= 1 or len(x) < n:
        return x.astype(np.float32)
    # borda repetida (nao zeros): em dB, zero seria "volume maximo" e o fim do arquivo viraria pico falso
    xp = np.pad(np.asarray(x, dtype=np.float32), (n // 2, n - 1 - n // 2), mode="edge")
    return np.convolve(xp, np.ones(n, dtype=np.float32) / n, mode="valid")


def z_robusto(x, janela=300, passo=30, piso=1e-3):
    """(x - mediana local) / max(1.4826 * MAD local, piso), com mediana/MAD calculadas a cada `passo` s e interpoladas.
    O piso evita que um trecho muito constante (ruido parado, chat morto) transforme qualquer variacao minima em "pico"."""
    n = len(x)
    if n == 0:
        return x
    centros, meds, mads = [], [], []
    for c in range(0, n, passo):
        w = x[max(0, c - janela // 2): c + janela // 2 + 1]
        m = float(np.median(w))
        centros.append(c)
        meds.append(m)
        mads.append(max(float(np.median(np.abs(w - m))) * 1.4826, piso))
    idx = np.arange(n)
    return (x - np.interp(idx, centros, meds)) / np.interp(idx, centros, mads)


def pontuar(audio_db, chat=None, peso_audio=1.0, peso_chat=1.4):
    """Score por segundo. Audio: media de 4 s (grito/risada sustentados, nao um estalo). Chat: soma de 10 s."""
    za = z_robusto(_media_movel(audio_db, 4), piso=2.0)  # 2 dB: variacao menor que isso nao e "momento"
    za = np.clip(za, -3, 8)
    if chat is None:
        return za * peso_audio, za, None
    n = min(len(za), len(chat))
    zc = np.clip(z_robusto(_media_movel(chat[:n], 10) * 10, passo=30, piso=3.0), -3, 10)  # piso: 3 msgs em 10 s
    return peso_audio * za[:n] + peso_chat * zc, za[:n], zc


def escolher_janelas(score, quantos=6, minimo=2.0, antes=22, depois=10, dur_min=25, dur_max=58, total=None):
    """Os `quantos` maiores picos, sem sobreposicao, cada um virando uma janela [ini, fim] em segundos."""
    total = total or len(score)
    sc = np.array(score, dtype=np.float32)
    sc[:IGNORAR_INICIO_S] = -1e9
    janelas = []
    for pico in np.argsort(-sc):
        if len(janelas) >= quantos or sc[pico] < minimo:
            break
        ini, fim = pico - antes, pico + depois
        if fim - ini < dur_min:
            fim = ini + dur_min
        fim = min(fim, ini + dur_max)
        ini, fim = max(0, ini), min(total, fim)
        if fim - ini < dur_min * 0.6:
            continue
        if any(ini < f + 5 and fim > i - 5 for i, f, *_ in janelas):
            continue
        janelas.append((float(ini), float(fim), float(sc[pico]), int(pico)))
    return sorted(janelas)


def detectar(arquivo, chat_jsonl=None, cfg=None):
    """Lista de dicts {inicio, fim, score, motivo} para um video/audio (e o chat, se houver)."""
    cfg = cfg or {}
    db = energia_por_segundo(arquivo)
    chat, hype = (None, {})
    if chat_jsonl:
        chat, hype = chat_por_segundo(chat_jsonl, len(db), cfg.get("atraso_chat_s", 6))
    score, za, zc = pontuar(db, chat, cfg.get("peso_audio", 1.0), cfg.get("peso_chat", 1.4))
    js = escolher_janelas(score, cfg.get("cortes_por_live", 6), cfg.get("score_minimo", 2.0), cfg.get("antes_do_pico_s", 22),
                          cfg.get("depois_do_pico_s", 10), cfg.get("duracao_min_s", 25), cfg.get("duracao_max_s", 58), len(score))
    saida = []
    for ini, fim, s, pico in js:
        motivo = f"audio {za[pico]:+.1f}σ"
        if zc is not None:
            nh = sum(hype.get(i, 0) for i in range(pico - 5, pico + 15))
            motivo += f", chat {zc[pico]:+.1f}σ" + (f" ({nh} msgs de hype)" if nh else "")
        saida.append({"inicio": ini, "fim": fim, "score": round(s, 2), "motivo": motivo})
    return saida
