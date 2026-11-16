# -*- coding: utf-8 -*-
"""Oficina local da Fornalha: o que o estúdio de cinema com IA faz (ideias do pro-cinematic-studio), só com Pillow e ffmpeg, sem API paga.
Livro de estilo por cliente, roteiro de vídeo por planos com tempo, acabamento (corte, cor, nitidez, loudness, capa),
placar de qualidade 0-100 (Cris), biblioteca de prompts vencedores, registro de desperdício e filtro de promessas na legenda."""
import json
import re
import subprocess
import sys
import time
from pathlib import Path

SEM_JANELA = 0x08000000 if sys.platform == "win32" else 0

# Um plano = um movimento de câmera; gancho nos 2 primeiros segundos; sem texto escrito na arte (regras do diretor de fotografia do estúdio).
ROTEIRO_VIDEO = ("Estruture o vídeo em 3 planos com tempo, no formato:\n"
                 "0-2s GANCHO: ... | 2-5s DESENVOLVIMENTO: ... | 5-8s FECHAMENTO: ...\n"
                 "Em cada plano diga enquadramento, lente (ex.: 35mm, macro), UM único movimento de câmera, luz e o que se move na cena. "
                 "Mantenha a mesma luz, cores e direção da câmera nos 3 planos (continuidade).")

PROMESSAS = [r"o melhor d[aeo]s? [\wçãõáéíóúâêô ]{2,25}", r"melhor d[aeo]s? (?:cidade|regi[aã]o|brasil)", r"\b100 ?% ?\w+", r"sem conservantes?", r"saud[aá]vel",
             r"emagrec\w+", r"\bcura\w*", r"garantid\w+", r"\bn[ºo°]\.? ?1\b", r"\bnúmero 1\b", r"zero (?:gl[uú]ten|lactose|a[cç][uú]car)", r"artesanal"]


def estilo(pasta, cliente):
    """Livro de estilo do cliente (data/empresa_mkt/estilo/<cliente>.md), escrito à mão ou pelo Ravi. Vazio se não existir."""
    f = Path(pasta) / "estilo" / (cliente.replace(" ", "-") + ".md")
    try:
        return f.read_text(encoding="utf-8")[:900]
    except OSError:
        return ""


def _run(cmd, t=300):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=t, creationflags=SEM_JANELA)


def sondar_video(f):
    """{w,h,dur,audio} via ffprobe; {} se não deu para ler."""
    try:
        r = _run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(f)], 30)
        d = json.loads(r.stdout or "{}")
        v = next(s for s in d["streams"] if s.get("codec_type") == "video")
        return {"w": int(v["width"]), "h": int(v["height"]), "dur": float(d["format"].get("duration") or 0),
                "audio": any(s.get("codec_type") == "audio" for s in d["streams"])}
    except Exception:
        return {}


# ---------------------------------------------------------------- acabamento (editor + colorista)
def alvo_imagem(tipo):
    return (1080, 1920) if tipo == "stories" else (1080, 1350)


def acabar_imagem(f, tipo):
    """Corta para 4:5 (stories 9:16), reduz a 1080 de largura se for maior, cor e nitidez leves. O original fica como <nome>_bruto."""
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps
    f = Path(f)
    im = Image.open(f).convert("RGB")
    bruto = f.with_name(f.stem + "_bruto" + f.suffix)
    if not bruto.exists():
        im.save(bruto)
    W, H = alvo_imagem(tipo)
    ratio = W / H
    w, h = im.size
    if w / h > ratio:
        nw = int(h * ratio)
        im = im.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    else:
        nh = int(w / ratio)
        im = im.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    if im.size[0] > W:
        im = im.resize((W, H), Image.LANCZOS)
    im = ImageOps.autocontrast(im, cutoff=0.5)
    im = ImageEnhance.Color(im).enhance(1.06)
    im = ImageEnhance.Contrast(im).enhance(1.03)
    im = im.filter(ImageFilter.UnsharpMask(radius=1.2, percent=60, threshold=3))
    im.save(f)
    return f"{im.size[0]}x{im.size[1]}"


def acabar_video(f):
    """9:16 1080x1920, cor e nitidez leves, loudness -16 LUFS (se tiver áudio) e capa JPG do meio do vídeo."""
    f = Path(f)
    info = sondar_video(f)
    if not info:
        raise RuntimeError("não consegui ler o vídeo (ffprobe)")
    saida = f.with_name(f.stem + "_acab.mp4")
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(f), "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,eq=contrast=1.04:saturation=1.08,unsharp=3:3:0.4",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    cmd += ["-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "128k"] if info["audio"] else ["-an"]
    r = _run(cmd + [str(saida)])
    if r.returncode or not saida.exists() or saida.stat().st_size < 10_000:
        raise RuntimeError("ffmpeg falhou: " + (r.stderr or "")[-120:])
    bruto = f.with_name(f.stem + "_bruto.mp4")
    if not bruto.exists():
        f.replace(bruto)
    saida.replace(f)
    capa = f.with_name(f.stem + "_capa.jpg")
    _run(["ffmpeg", "-y", "-v", "error", "-ss", str(max(0.5, info["dur"] / 2)), "-i", str(f), "-frames:v", "1", "-q:v", "3", str(capa)], 60)
    return f"{info['w']}x{info['h']} -> 1080x1920, capa {'ok' if capa.exists() else 'não gerada'}"


# ---------------------------------------------------------------- placar de qualidade (Cris)
def placar_imagem(f, tipo):
    """(nota 0-100, [notas]). Resolução 30 + formato 15 + brilho 20 + nitidez 20 + contraste 15. Imagem em branco reprova direto."""
    from PIL import Image, ImageFilter, ImageStat
    im = Image.open(f).convert("RGB")
    w, h = im.size
    cinza = im.convert("L")
    st = ImageStat.Stat(cinza)
    media, desvio = st.mean[0], st.stddev[0]
    borda = ImageStat.Stat(cinza.filter(ImageFilter.FIND_EDGES)).var[0]
    W, H = alvo_imagem(tipo)
    mn = min(w, h)
    res = 30 if mn >= 1000 else 25 if mn >= 720 else 20 if mn >= 512 else 0
    fmt = 15 if abs(w / h - W / H) < .02 else 6 if abs(w / h - W / H) < .15 else 0
    bri = 20 if 50 <= media <= 205 else 10 if 30 <= media <= 225 else 0
    nit = 20 if borda >= 80 else 10 if borda >= 25 else 0
    con = 15 if desvio >= 30 else 8 if desvio >= 15 else 0
    notas = []
    if res < 20:
        notas.append(f"resolução baixa ({w}x{h})")
    if fmt < 15:
        notas.append(f"formato fora de {W}:{H}")
    if bri < 20:
        notas.append("muito " + ("escura" if media < 50 else "clara"))
    if nit < 20:
        notas.append("sem nitidez (borrada)")
    if con < 15:
        notas.append("pouco contraste")
    if desvio < 8:
        return 0, ["imagem praticamente em branco"]
    return res + fmt + bri + nit + con, notas


def placar_video(f):
    """(nota, [notas]): duração 3-20s (30), altura >=720 (25), formato 9:16 (20), tem faixa de vídeo (10), tamanho (15)."""
    f = Path(f)
    i = sondar_video(f)
    if not i:
        return (60, ["sem ffprobe: só conferi o tamanho"]) if f.stat().st_size > 100_000 else (0, ["vídeo ilegível"])
    dur = 30 if 3 <= i["dur"] <= 20 else 12 if i["dur"] >= 1.5 else 0
    alt = 25 if i["h"] >= 1280 else 15 if i["h"] >= 720 else 0
    fmt = 20 if abs(i["w"] / i["h"] - 9 / 16) < .02 else 0
    tam = 15 if f.stat().st_size >= 100_000 else 0
    notas = []
    for ok, t in ((dur == 30, f"duração {i['dur']:.1f}s fora de 3-20s"), (alt >= 25, f"altura {i['h']}px"), (fmt == 20, "formato não é 9:16"), (tam == 15, "arquivo pequeno")):
        if not ok:
            notas.append(t)
    return dur + alt + fmt + 10 + tam, notas


# ---------------------------------------------------------------- promessas na legenda (checklist legal do estúdio, versão marketing)
def tirar_promessas(legenda, briefing):
    """Remove da legenda promessas/superlativos que o briefing não autorizou. Devolve (texto, [removidos])."""
    bl = (briefing or "").lower()
    achados = []
    for rx in PROMESSAS:
        for m in re.finditer(rx, legenda or "", re.I):
            if m.group(0).lower() not in bl:
                achados.append(m.group(0))
    txt = legenda or ""
    for a in sorted(set(achados), key=len, reverse=True):
        txt = re.sub(re.escape(a) + r"[,.!]?\s*", "", txt, flags=re.I)
    return re.sub(r"[ \t]{2,}", " ", txt).strip(), sorted(set(achados))


# ---------------------------------------------------------------- biblioteca de prompts vencedores e desperdício (continuidade)
def _anexar(arq, obj):
    arq.parent.mkdir(parents=True, exist_ok=True)
    with arq.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _linhas(arq):
    out = []
    try:
        for ln in arq.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(ln))
            except ValueError:
                pass
    except OSError:
        pass
    return out


def guardar_vencedor(pasta, p, nota):
    _anexar(Path(pasta) / "biblioteca.jsonl", {"ts": time.time(), "cliente": p["cliente"], "tipo": p["tipo"], "nota": nota, "prompt": (p.get("prompt") or "")[:1500]})


def melhores(pasta, cliente, tipo, n=2):
    L = [x for x in _linhas(Path(pasta) / "biblioteca.jsonl") if x["cliente"] == cliente and x["tipo"] == tipo and x.get("prompt")]
    return [x["prompt"] for x in sorted(L, key=lambda x: (x["nota"], x["ts"]), reverse=True)[:n]]


def registrar_desperdicio(pasta, p, causa):
    _anexar(Path(pasta) / "desperdicio.jsonl", {"ts": time.time(), "pedido": p["id"], "cliente": p["cliente"], "tipo": p["tipo"], "causa": causa[:200]})


def desperdicio(pasta, dias=7):
    return sum(1 for x in _linhas(Path(pasta) / "desperdicio.jsonl") if time.time() - x["ts"] < dias * 86400)
