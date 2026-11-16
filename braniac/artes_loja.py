# -*- coding: utf-8 -*-
"""ARTES DA LOJA para o Instagram, feitas 100% pelo Braniac (sem gastar tokens do Claude): fotos da pasta do Dono -> posts de feed (4:5),
stories (9:16) e um reel (mp4) com a identidade da loja; legendas escritas pelo CONSELHO de IAs (Gemini/ChatGPT pelas abas logadas, gratis) e VALIDADAS
(so precos e dias que existem no dossie); no fim, envia tudo ao contato 'Loja' (a Layla) pelo WhatsApp.

Uso:  python -m braniac.artes_loja            (gera + envia)        python -m braniac.artes_loja --sem-enviar     (so gera)
Regras: nada de preco/horario inventado; sem telefone nas artes (so o site); fotos originais nunca sao alteradas (trabalha em copias reduzidas)."""
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from .store import DATA

PASTA_FOTOS = Path(r"E:\.Fotografia\2026\Rendered\2026\Esphirraria")
LOGO = Path(__file__).resolve().parent.parent / "loja-esfiharia" / "img" / "logo.jpg"
SITE = "libanoesfiharia.vercel.app"
CONTATO = "Loja"
VERMELHO = (142, 27, 27)
CREME = (246, 231, 200)
OURO = (216, 169, 74)
ESCURO = (38, 10, 10)
FONTE_T = "C:/Windows/Fonts/ariblk.ttf"
FONTE_B = "C:/Windows/Fonts/arialbd.ttf"
FONTE_R = "C:/Windows/Fonts/arial.ttf"

# Fatos permitidos (dossie da loja). Qualquer 'R$ x' fora desta lista barra a legenda.
PRECOS_OK = {"12,50", "13,50", "21,90", "39,99", "68,90", "28,99", "55,99", "82,99", "99,98", "120,99", "146,99"}

# (id, tipo, foto, titulo, subtitulo, ideia para a legenda)
CONCEITOS = [
    ("feed1", "feed", "DSC_0726", "O doce que você respeita", "Esfiha de chocolate com morango", "doce irresistível, chocolate e morango; convide a pedir"),
    ("feed2", "feed", "DSC_0668", "Gratinada no ponto", "Esfiha aberta com queijo dourado", "queijo gratinado e recheio generoso"),
    ("feed3", "feed", "DSC_0735", "Salgada ou doce?", "22 sabores salgados e 10 doces. Qual é o seu?", "pergunta para gerar comentários sobre o sabor favorito"),
    ("feed4", "feed", "DSC_0744", "Segunda em Dobro", "2 esfihas por R$ 21,90 · só na segunda", "promoção do dia: Segunda em Dobro, 2 esfihas sem refri por R$ 21,90"),
    ("feed5", "feed", "DSC_0728", "Terça Imbatível", "3 esfihas + Coca lata por R$ 39,99 · só na terça", "promoção do dia: Terça Imbatível, 3 esfihas + Coca lata por R$ 39,99"),
    ("feed6", "feed", "DSC_0747", "Mega Quinta", "5 esfihas + Guaraná 1L + 1 doce por R$ 68,90 · só na quinta", "promoção do dia: Mega Quinta, 5 esfihas + Guaraná 1L + 1 doce por R$ 68,90"),
    ("feed7", "feed", "DSC_0739", "Confete, coco e chocolate", "Esfihas doces a R$ 13,50", "variedade de doces, esfiha doce custa R$ 13,50"),
    ("feed8", "feed", "DSC_0674", "Peça no delivery", "WhatsApp ou iFood · de quinta a terça", "pedido fácil pelo site e WhatsApp; atendemos de quinta a terça (fechado na quarta)"),
    ("story1", "story", "DSC_0678", "Chocolate crocante", "Aquele doce de fechar os olhos", "story rápido com chamada para pedir"),
    ("story2", "story", "DSC_0742", "Monte o seu combo", "Combos de 2 a 12 esfihas no site", "convite para montar combo no site"),
    ("story3", "story", "DSC_0665", "Bateu a fome de esfiha?", "Peça a sua pelo WhatsApp", "story com chamada direta"),
]
REEL = [  # (foto, texto grande, texto pequeno)
    ("DSC_0726", "Esfiha aberta,", "recheio generoso"),
    ("DSC_0668", "22 salgadas", "gratinadas no ponto"),
    ("DSC_0744", "10 doces", "pra fechar com chave de ouro"),
    ("DSC_0728", "Segunda em Dobro", "2 esfihas por R$ 21,90"),
    ("DSC_0735", "Qual é o seu sabor?", "conta nos comentários"),
    ("DSC_0742", "Loja", "Peça em " + SITE),
]


def _fonte(caminho, tam):
    return ImageFont.truetype(caminho, tam)


def _quebrar(draw, texto, fonte, largura):
    linhas, atual = [], ""
    for palavra in texto.split():
        teste = (atual + " " + palavra).strip()
        if draw.textlength(teste, font=fonte) <= largura:
            atual = teste
        else:
            linhas.append(atual)
            atual = palavra
    if atual:
        linhas.append(atual)
    return linhas


def _preparar_fotos(saida):
    """Copias reduzidas (lado maior 2400 px) das fotos originais; o original nao e tocado."""
    pasta = saida / "_fotos"
    pasta.mkdir(parents=True, exist_ok=True)
    out = {}
    for f in sorted(PASTA_FOTOS.glob("*.jpg")):
        dest = pasta / f.name
        if not dest.exists():
            im = ImageOps.exif_transpose(Image.open(f)).convert("RGB")
            im.thumbnail((2400, 2400))
            im.save(dest, quality=92)
        out[f.stem] = dest
    return out


def _cobrir(im, w, h, fx=0.5, fy=0.5):
    """Recorta/redimensiona para preencher w x h (ponto focal fx, fy)."""
    r = max(w / im.width, h / im.height)
    nw, nh = int(im.width * r + 0.5), int(im.height * r + 0.5)
    im = im.resize((nw, nh), Image.LANCZOS)
    x = int((nw - w) * fx)
    y = int((nh - h) * fy)
    return im.crop((x, y, x + w, y + h))


def _selo(canvas, x, y, d=150):
    if not LOGO.exists():
        return
    lg = Image.open(LOGO).convert("RGB")
    lado = min(lg.size)
    lg = lg.crop(((lg.width - lado) // 2, (lg.height - lado) // 2, (lg.width + lado) // 2, (lg.height + lado) // 2)).resize((d, d), Image.LANCZOS)
    m = Image.new("L", (d, d), 0)
    ImageDraw.Draw(m).ellipse((0, 0, d - 1, d - 1), fill=255)
    borda = Image.new("RGB", (d + 10, d + 10), CREME)
    mb = Image.new("L", (d + 10, d + 10), 0)
    ImageDraw.Draw(mb).ellipse((0, 0, d + 9, d + 9), fill=255)
    canvas.paste(borda, (x - 5, y - 5), mb)
    canvas.paste(lg, (x, y), m)


def _degrade(w, h, topo, cor=ESCURO, a_max=235):
    g = Image.new("RGBA", (w, h), cor + (0,))
    px = g.load()
    for yy in range(h):
        a = 0 if yy < topo else int(a_max * ((yy - topo) / max(1, h - topo)) ** 0.8)
        for xx in range(w):
            px[xx, yy] = cor + (a,)
    return g


def _texto_bloco(canvas, titulo, sub, y_base, largura=940, x=70, tam_t=84, tam_s=40):
    """Titulo (Arial Black, creme) + subtitulo (ouro) terminando em y_base (o bloco cresce para cima)."""
    d = ImageDraw.Draw(canvas)
    ft = _fonte(FONTE_T, tam_t)
    fs = _fonte(FONTE_B, tam_s)
    lt = _quebrar(d, titulo, ft, largura)
    ls = _quebrar(d, sub, fs, largura)
    alt = len(lt) * int(tam_t * 1.08) + 18 + len(ls) * int(tam_s * 1.3)
    y = y_base - alt
    for l in lt:
        d.text((x + 3, y + 3), l, font=ft, fill=(0, 0, 0))
        d.text((x, y), l, font=ft, fill=CREME)
        y += int(tam_t * 1.08)
    y += 18
    for l in ls:
        d.text((x, y), l, font=fs, fill=OURO)
        y += int(tam_s * 1.3)


def _barra_cta(canvas, texto, y, h=96):
    d = ImageDraw.Draw(canvas)
    d.rectangle((0, y, canvas.width, y + h), fill=VERMELHO)
    d.rectangle((0, y, canvas.width, y + 5), fill=OURO)
    f = _fonte(FONTE_B, 34)
    tw = d.textlength(texto, font=f)
    d.text(((canvas.width - tw) / 2, y + (h - 34) / 2 + 2), texto, font=f, fill=CREME)


def render_feed(foto, titulo, sub, destino, fx=0.5, fy=0.5):
    W, H = 1080, 1350
    base = _cobrir(Image.open(foto).convert("RGB"), W, H, fx, fy)
    c = base.convert("RGBA")
    c.alpha_composite(_degrade(W, H, int(H * 0.42)))
    c = c.convert("RGB")
    _selo(c, 60, 60)
    _barra_cta(c, f"Peça pelo WhatsApp  •  {SITE}", H - 96)
    _texto_bloco(c, titulo, sub, H - 96 - 50)
    c.save(destino, quality=93)


def render_story(foto, titulo, sub, destino, cta=f"Peça pelo WhatsApp  •  {SITE}"):
    W, H = 1080, 1920
    im = Image.open(foto).convert("RGB")
    fundo = _cobrir(im, W, H).filter(ImageFilter.GaussianBlur(38))
    fundo = Image.blend(fundo, Image.new("RGB", (W, H), ESCURO), 0.55)
    c = fundo
    cartao = _cobrir(im, 980, 1000)
    mask = Image.new("L", (980, 1000), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, 979, 999), 46, fill=255)
    c.paste(cartao, (50, 380), mask)
    d = ImageDraw.Draw(c)
    d.rounded_rectangle((46, 376, 1034, 1384), 50, outline=OURO, width=5)
    _selo(c, (W - 170) // 2, 120, 170)
    _texto_bloco(c, titulo, sub, 1384 + 400, tam_t=82, tam_s=40)
    _barra_cta(c, cta, H - 130, 96)
    c.save(destino, quality=93)


def render_reel(fotos, destino, dur=3.2, fade=0.5):
    """Reel 1080x1920 (mp4, sem audio: o Instagram deixa por a musica): slides com zoom suave e transicao."""
    tmp = destino.parent / "_reel"
    tmp.mkdir(exist_ok=True)
    quadros = []
    for i, (nome, t1, t2) in enumerate(REEL):
        q = tmp / f"q{i}.png"
        render_story(fotos[nome], t1, t2, q, cta=(f"{SITE}" if i == len(REEL) - 1 else "Loja  •  delivery"))
        quadros.append(q)
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    for q in quadros:
        cmd += ["-i", str(q)]
    filtros, ult = [], None
    for i in range(len(quadros)):
        filtros.append(f"[{i}:v]scale=1188:2112,zoompan=z='1+0.00027*on':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={int((dur + fade) * 30)}:s=1080x1920:fps=30,setsar=1[v{i}]")
    ult = "v0"
    for i in range(1, len(quadros)):
        off = i * dur
        filtros.append(f"[{ult}][v{i}]xfade=transition=fade:duration={fade}:offset={off:.2f}[x{i}]")
        ult = f"x{i}"
    cmd += ["-filter_complex", ";".join(filtros), "-map", f"[{ult}]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-movflags", "+faststart", str(destino)]
    r = subprocess.run(cmd, capture_output=True, text=True, creationflags=0x08000000)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg falhou: " + r.stderr[-400:])
    shutil.rmtree(tmp, ignore_errors=True)


# ---------------- legendas pelo conselho (gratis) + validacao ----------------

def validar_legenda(txt):
    """Barra preco/horario que nao existe no dossie, telefone e texto longo demais."""
    if not txt or len(txt) > 700:
        return False
    for v in re.findall(r"R\$\s*(\d+[.,]\d{2})", txt):
        if v.replace(".", ",") not in PRECOS_OK:
            return False
    if re.search(r"\d{4,}", txt) or re.search(r"\b\d{1,2}\s*h\b|\d{1,2}h\d{0,2}", txt, re.I):
        return False      # nada de horario nem telefone nas legendas geradas por IA
    return True


def legenda_padrao(titulo, sub):
    return f"{titulo}. {sub}.\n\nPeça pelo WhatsApp ou pelo site {SITE} 🧡\n\n#esfiha #esfihaaberta #barradogarcas #delivery #libanoesfiharia"


def pedir_legendas(conc, perguntar=None):
    """Pede ao Gemini (e ao ChatGPT de reserva) as legendas de todos os posts numa unica pergunta. Devolve {id: legenda} so com as validas."""
    if perguntar is None:
        from . import ia_web
        perguntar = ia_web.perguntar
    briefs = "\n".join(f"### {c[0]} | {c[3]} | {c[4]} | ideia: {c[5]}" for c in conc)
    pergunta = (
        "Você é social media de uma esfiharia de delivery em Cidade-MT chamada Loja (esfihas abertas, 22 salgadas e 10 doces). "
        "Escreva a LEGENDA de Instagram de cada post abaixo: tom caloroso e apetitoso, 2 a 4 linhas, até 3 emojis, uma chamada para pedir pelo WhatsApp ou pelo site libanoesfiharia.vercel.app, "
        "e 5 a 7 hashtags no fim (#esfiha #barradogarcas etc.). REGRAS: use SOMENTE os preços e dias que aparecem no resumo de cada post, NÃO invente preço, horário, telefone, sabor ou promoção. "
        "Responda exatamente neste formato, sem comentários extras:\n### id\ntexto da legenda\n(repita para cada id)\n\nPOSTS:\n" + briefs + "\n### reel | vídeo de 20 s mostrando as esfihas, 22 salgadas, 10 doces e a Segunda em Dobro por R$ 21,90")
    for ia in ("gemini", "chatgpt"):
        try:
            bruto = perguntar(ia, pergunta, timeout_s=240)
        except Exception as e:
            print(f"  conselho/{ia} indisponivel: {str(e)[:80]}")
            continue
        legs = {}
        partes = re.split(r"(?mi)^[ \t]*(?:#{1,4}[ \t]*)?(feed\d+|story\d+|reel)\b[^\n]*\n", bruto)   # o site do chat remove os ###: o id vem sozinho numa linha
        for ident, corpo in zip(partes[1::2], partes[2::2]):
            corpo = re.sub(r"(?mi)^\s*(escrita|texto|legenda)\s*$", "", corpo).strip()
            if validar_legenda(corpo):
                legs[ident.strip().lower()] = corpo
        if legs:
            print(f"  legendas do conselho ({ia}): {len(legs)} validas")
            return legs
    return {}


def gerar(saida=None, conselho=True, perguntar=None):
    saida = Path(saida) if saida else DATA / "artes_loja" / datetime.now().strftime("%Y%m%d_%H%M")
    saida.mkdir(parents=True, exist_ok=True)
    fotos = _preparar_fotos(saida)
    faltam = [c[2] for c in CONCEITOS if c[2] not in fotos] + [r[0] for r in REEL if r[0] not in fotos]
    if faltam:
        raise RuntimeError(f"fotos nao encontradas em {PASTA_FOTOS}: {sorted(set(faltam))}")
    legs = pedir_legendas(CONCEITOS, perguntar) if conselho else {}
    arquivos, legendas = [], []
    for ident, tipo, nome, tit, sub, _ in CONCEITOS:
        dest = saida / f"{ident}_{tipo}.jpg"
        (render_feed if tipo == "feed" else render_story)(fotos[nome], tit, sub, dest)
        arquivos.append(dest)
        legendas.append(f"[{ident}] {tit}\n{legs.get(ident) or legenda_padrao(tit, sub)}\n")
    reel = saida / "reel_esfihas.mp4"
    render_reel(fotos, reel)
    arquivos.insert(0, reel)
    legendas.append("[reel] Vídeo (sem música: coloque uma música do Instagram)\n" + (legs.get("reel") or legenda_padrao("Esfiha aberta, recheio generoso", "22 salgadas, 10 doces e Segunda em Dobro por R$ 21,90")) + "\n")
    leg = saida / "legendas.txt"
    leg.write_text("\n".join(legendas), encoding="utf-8")
    shutil.rmtree(saida / "_fotos", ignore_errors=True)
    return arquivos, leg


def enviar(arquivos, leg, contato=CONTATO, espaco_s=6):
    from . import whatsapp, wpp_arquivo
    with whatsapp.LOCK:
        whatsapp.enviar(contato, "Oi! Aqui é o Jarvis, a pedido do Dono. Seguem as ARTES PRONTAS para o Instagram da Loja: 1 vídeo (reel), 8 posts de feed e 3 stories, mais o arquivo com as legendas sugeridas. Pode publicar!")
    resultados = []
    for a in list(arquivos) + [leg]:
        time.sleep(espaco_s)
        with whatsapp.LOCK:
            r = wpp_arquivo.enviar_arquivo(contato, str(a), "")
        resultados.append((Path(a).name, str(r)[:60]))
        print("  ", Path(a).name, "->", str(r)[:70])
    return resultados


if __name__ == "__main__":
    arqs, leg = gerar(conselho="--sem-conselho" not in sys.argv)
    print(f"{len(arqs)} artes em {leg.parent}")
    if "--sem-enviar" not in sys.argv:
        res = enviar(arqs, leg)
        ok = sum(1 for _, r in res if r.startswith("✅"))
        print(f"enviados {ok}/{len(res)}")
