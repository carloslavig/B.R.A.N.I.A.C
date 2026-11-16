# -*- coding: utf-8 -*-
"""ArtCraft DENTRO do Jarvis (17/10/2026): foto, vetor, PDF, Word, planilha, slides, audio, CAD e video (so ler) pelos CLIs sem janela
(~\\Apps\\ArtCraft\\<app>\\*\\<app>-cli.exe, Apache-2.0), sem gastar token do Claude. Os apps so escrevem em ArtCraft-Trabalho; o original nunca e alterado.
Edicao complexa (video, motion, diagramacao, ajuste fino) continua com delegar_ao_claude + skill artcraft."""
import json, re, subprocess
from pathlib import Path

APPS = Path.home() / "Apps" / "ArtCraft"
TRABALHO = Path.home() / "ArtCraft-Trabalho"
EXT_SAIDA = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".pdf", ".svg", ".docx", ".odt", ".txt", ".xlsx", ".csv", ".tsv", ".json", ".html",
             ".pptx", ".wav", ".flac", ".mp3", ".ogg", ".dxf", ".dwg"}
BLOQUEADO = ("\\.ssh", "\\appdata\\roaming\\microsoft", ".env", "id_rsa", "login data", "\\cookies")


class ArtCraftErro(RuntimeError):
    pass


def _exe(app):
    achados = sorted(APPS.glob(f"{app}/*/{app}-cli.exe"))
    if not achados:
        raise ArtCraftErro(f"O app {app} do ArtCraft não está instalado em {APPS}.")
    return str(achados[-1])


def _rodar(app, args, timeout=300):
    TRABALHO.mkdir(exist_ok=True)
    r = subprocess.run([_exe(app), *map(str, args)], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=timeout, creationflags=0x08000000, cwd=str(TRABALHO))
    if r.returncode:
        raise ArtCraftErro((r.stderr or r.stdout or "falhou").strip()[-300:])
    return r.stdout.strip()


def _entrada(caminho):
    c = Path(str(caminho).strip().strip('"')).expanduser().resolve()
    if any(b in str(c).lower() for b in BLOQUEADO):
        raise ArtCraftErro("Esse local é protegido; não abro por segurança.")
    if not c.is_file():
        raise ArtCraftErro(f"Não achei o arquivo: {c}")
    return str(c)


def _saida(nome, ext):
    n = re.sub(r"[^\w\-. ]", "_", Path(str(nome or "").strip().strip('"')).name) or "resultado"
    if Path(n).suffix.lower() not in EXT_SAIDA:
        n = Path(n).stem + ext
    TRABALHO.mkdir(exist_ok=True)
    return str(TRABALHO / n)


def _lista(v):
    return [x.strip() for x in re.split(r"[;\n]", str(v)) if x.strip()]


def _cartaz(texto, out, cores=""):
    achadas = re.findall(r"#[0-9a-fA-F]{6}", cores)
    fundo, cor_texto, destaque = (achadas + ["#1f1f3d", "#ffffff", "#f5a623"][len(achadas):])[:3]
    passos = [("shape.rectangle", {"x": 0, "y": 0, "width": 612, "height": 792}), ("paint.setFill", {"color": fundo}),
              ("shape.ellipse", {"x": 156, "y": 130, "width": 300, "height": 300}), ("paint.setFill", {"color": destaque}),
              ("text.create", {"x": 46, "y": 480, "text": texto, "size": 48, "color": cor_texto, "justify": "center",
                               "area": {"width": 520, "height": 220, "fit": "shrinkText"}})]
    a = ["run"]
    for c, p in passos:
        a += ["--cmd", c, "--params", json.dumps(p)]
    return a + ["--export", out, "--scale", 2]


def _foto(cmd, par=None):
    return lambda i, o, x: ["run", i, "--cmd", cmd] + (["--params", json.dumps(par(x))] if par else []) + ["--out", o]


GIROS = {"90": "edit.transform.rotate90Cw", "180": "edit.transform.rotate180", "270": "edit.transform.rotate90Ccw", "-90": "edit.transform.rotate90Ccw"}


def _girar(i, o, x):
    if (x or "90") not in GIROS:
        raise ArtCraftErro("Só giro em 90, 180 ou 270 graus.")
    return _foto(GIROS[x or "90"])(i, o, x)


# ---------- desenho livre (a IA descreve a imagem como formas) ----------
DESENHO_AJUDA = ('Imagem 612x792 (x para a direita, y para BAIXO). "formas" = lista JSON, de baixo para cima (a primeira fica no fundo). Cada forma: '
                 '{"t":"rect","x":0,"y":0,"w":612,"h":792,"cor":"#112233","raio":10} | {"t":"elipse","x","y","w","h","cor"} | {"t":"poligono","cx","cy","r","lados":6,"cor"} | '
                 '{"t":"estrela","cx","cy","r1","r2","pontas":5,"cor"} | {"t":"linha","x1","y1","x2","y2","borda":"#000000","largura":3} | '
                 '{"t":"caminho","d":"M10 10 L50 80 Q90 10 120 80 Z","cor","borda","largura"} (d = caminho SVG) | {"t":"texto","x","y","texto","tam":40,"cor"}. '
                 'Cores #rrggbb; "borda" (contorno) e "largura" opcionais; sem "cor" a forma fica sem preenchimento.')
_COR = re.compile(r"^#[0-9a-fA-F]{6}$")
_SVG_D = re.compile(r"^[MmLlHhVvCcSsQqTtAaZz0-9\s,.\-eE+]{1,4000}$")


def _passos_desenho(formas):
    if isinstance(formas, str):
        try:
            formas = json.loads(formas)
        except ValueError:
            raise ArtCraftErro("A lista de formas não é um JSON válido.")
    if isinstance(formas, dict):
        formas = formas.get("formas") or [formas]
    if not isinstance(formas, list) or not formas or len(formas) > 200:
        raise ArtCraftErro("Mande de 1 a 200 formas numa lista.")

    def cor(f, k="cor"):
        v = f.get(k)
        if v in (None, "", "nenhuma"):
            return None
        if not isinstance(v, str) or not _COR.match(v):
            raise ArtCraftErro(f"Cor inválida '{v}': use #rrggbb.")
        return v

    def num(f, k, padrao=None):
        try:
            return float(f[k]) if k in f else float(padrao)
        except (TypeError, ValueError):
            raise ArtCraftErro(f"Número inválido em '{k}'.")

    passos = []
    for f in formas:
        t = (f.get("t") or "").lower() if isinstance(f, dict) else ""
        if t == "rect":
            passos.append(("shape.rectangle", {"x": num(f, "x"), "y": num(f, "y"), "width": num(f, "w"), "height": num(f, "h"), "radius": num(f, "raio", 0)}))
        elif t in ("elipse", "circulo"):
            passos.append(("shape.ellipse", {"x": num(f, "x"), "y": num(f, "y"), "width": num(f, "w"), "height": num(f, "h", f.get("w"))}))
        elif t == "poligono":
            passos.append(("shape.polygon", {"cx": num(f, "cx"), "cy": num(f, "cy"), "radius": num(f, "r"), "sides": int(num(f, "lados", 6))}))
        elif t == "estrela":
            passos.append(("shape.star", {"cx": num(f, "cx"), "cy": num(f, "cy"), "radius1": num(f, "r1"), "radius2": num(f, "r2"), "points": int(num(f, "pontas", 5))}))
        elif t == "linha":
            passos.append(("shape.line", {"x1": num(f, "x1"), "y1": num(f, "y1"), "x2": num(f, "x2"), "y2": num(f, "y2")}))
            f = {**f, "borda": f.get("borda") or f.get("cor") or "#000000", "cor": None}
        elif t == "caminho":
            if not isinstance(f.get("d"), str) or not _SVG_D.match(f["d"]):
                raise ArtCraftErro("Caminho 'd' inválido (só comandos SVG M L H V C S Q T A Z e números).")
            passos.append(("path.create", {"d": f["d"]}))
        elif t == "texto":
            if not str(f.get("texto", "")).strip():
                raise ArtCraftErro("Texto vazio.")
            passos.append(("text.create", {"x": num(f, "x"), "y": num(f, "y"), "text": str(f["texto"])[:300], "size": num(f, "tam", 40), "color": cor(f) or "#000000"}))
            continue
        else:
            raise ArtCraftErro(f"Forma desconhecida '{t}'. Use rect, elipse, poligono, estrela, linha, caminho ou texto.")
        c, b = cor(f), cor(f, "borda")
        passos.append(("paint.setFill", {"color": c} if c else {"none": True}))
        passos.append(("paint.setStroke", {"color": b} if b else {"none": True}))
        if b:
            passos.append(("stroke.set", {"weight": num(f, "largura", 2)}))
    return passos


def _prompt_desenho(descricao):
    return ("Você é ilustrador vetorial. Desenhe: " + str(descricao)[:400] + "\n" + DESENHO_AJUDA + "\nUse de 10 a 30 formas, composição bonita e cores harmoniosas, "
            "o assunto bem reconhecível e grande, fundo primeiro. Responda SOMENTE a lista JSON, sem texto antes ou depois, sem markdown.")


def formas_de_descricao(descricao, gerar):
    """Pede a uma IA (gerar(prompt) -> texto) as formas do desenho; tenta 2 vezes e devolve a lista ja validada."""
    erro = ""
    for _ in range(2):
        texto = gerar(_prompt_desenho(descricao) + erro) or ""
        m = re.search(r"\[.*\]", texto, re.S)
        try:
            formas = json.loads(m.group(0))
            _passos_desenho(formas)
            return formas
        except (ValueError, AttributeError, ArtCraftErro) as e:
            erro = f"\nSua resposta anterior foi inválida ({str(e)[:120]}). Responda apenas o JSON válido da lista."
    raise ArtCraftErro("A IA não conseguiu montar o desenho agora; tente de novo em instantes.")


def desenhar(descricao, gerar):
    """Descricao em texto -> PNG vetorial (caminho). 'gerar' e a funcao que consulta a IA."""
    formas = formas_de_descricao(descricao, gerar)
    slug = re.sub(r"[^a-z0-9]+", "-", str(descricao).lower())[:30].strip("-") or "imagem"
    out = _saida(f"desenho-{slug}", ".png")
    _rodar("vectorcraft", _desenhar(formas, out))
    if not Path(out).exists():
        raise ArtCraftErro("O app não gerou a imagem.")
    return out


def _desenhar(formas, out):
    a = ["run"]
    for c, par in _passos_desenho(formas):
        a += ["--cmd", c, "--params", json.dumps(par)]
    return a + ["--export", out, "--scale", 2]


# acao -> (app, ext padrao da saida, monta os argumentos (entrada, saida, extra), descricao)
ACOES = {
    "vetor_cartaz": ("vectorcraft", ".png", lambda i, o, x: _cartaz(i, o, x), "entrada = TEXTO do cartaz; extra = cores opcionais (#fundo #texto #destaque)"),
    "vetor_desenhar": ("vectorcraft", ".png", lambda i, o, x: _desenhar(i, o), "entrada = JSON com as formas do desenho livre. " + DESENHO_AJUDA),
    "vetor_converter": ("vectorcraft", ".png", lambda i, o, x: ["convert", i, o], "svg/pdf/ai/eps para png, pdf ou svg"),
    "foto_converter": ("photocraft", ".png", lambda i, o, x: ["convert", i, o] + (["--quality", int(x)] if x.isdigit() else []), "converte formato; extra = qualidade 1-100"),
    "foto_redimensionar": ("photocraft", ".png", _foto("image.imageSize", lambda x: {"width": int(float(x))}), "extra = largura em px"),
    "foto_girar": ("photocraft", ".png", _girar, "extra = 90, 180 ou 270"),
    "foto_preto_e_branco": ("photocraft", ".png", _foto("image.mode.grayscale"), "preto e branco"),
    "foto_revelar": ("lightcraft", ".jpg", lambda i, o, x: ["render", i, "-o", o], "revela uma foto (RAW/JPG) com o LightCraft"),
    "pdf_texto": ("pdfcraft", ".txt", lambda i, o, x: ["text", i] + (["--page", int(x)] if x.isdigit() else []), "texto do PDF; extra = página"),
    "pdf_juntar": ("pdfcraft", ".pdf", lambda i, o, x: ["combine", *[_entrada(a) for a in _lista(i)], "--out", o], "entrada = caminhos separados por ponto e vírgula"),
    "pdf_extrair": ("pdfcraft", ".pdf", lambda i, o, x: ["extract", i, "--pages", re.sub(r"[^\d,]", "", x), "--out", o], "extra = páginas (1,3,5)"),
    "pdf_dividir": ("pdfcraft", ".pdf", lambda i, o, x: ["split", i, "--every", int(x or 1), "--out-dir", str(Path(o).with_suffix(""))], "extra = páginas por parte"),
    "pdf_imagem": ("pdfcraft", ".png", lambda i, o, x: ["render", i, "--page", int(x or 1), "--dpi", 110, "--out", o], "extra = página"),
    "word_converter": ("wordcraft", ".pdf", lambda i, o, x: ["convert", i, o], "docx/odt/txt para pdf, docx etc."),
    "word_criar": ("wordcraft", ".docx", lambda i, o, x: _word_criar(i, o), "CRIA um documento Word novo; entrada = o TEXTO do documento (markdown: # titulo, - itens); saida = nome do arquivo"),
    "word_texto": ("wordcraft", ".txt", lambda i, o, x: ["text", i], "texto de um documento Word"),
    "planilha_converter": ("gridcraft", ".csv", lambda i, o, x: ["convert", i, o], "xlsx/csv/tsv/json/html entre si"),
    "planilha_ler": ("gridcraft", ".csv", lambda i, o, x: ["cat", i, "--csv"] + (["--range", x] if x else []), "extra = faixa (A1:D20)"),
    "slides_converter": ("deckcraft", ".pdf", lambda i, o, x: ["convert", i, o], "pptx para pdf etc."),
    "slides_imagem": ("deckcraft", ".png", lambda i, o, x: ["render", i, "--slide", int(x or 1), o], "extra = número do slide"),
    "audio_converter": ("soundcraft", ".wav", lambda i, o, x: ["convert", i, o] + (["--normalize"] if "norm" in x.lower() else []), "converte áudio; extra = 'normalizar'"),
    "audio_info": ("soundcraft", ".txt", lambda i, o, x: ["info", i], "dados do áudio"),
    "cad_converter": ("cadcraft", ".pdf", lambda i, o, x: ["convert", i, o], "dxf para pdf, png, svg ou dwg"),
    "video_info": ("filmcraft", ".txt", lambda i, o, x: ["probe", i], "dados do vídeo (duração, codec)"),
}
SO_TEXTO = {"pdf_texto", "word_texto", "planilha_ler", "audio_info", "video_info"}   # a saida e o proprio texto; nao cria arquivo


def _word_criar(texto, o):
    md = Path(o).with_suffix(".md")
    md.write_text(texto, encoding="utf-8")
    return ["convert", str(md), o]


def catalogo():
    return "; ".join(f"{n} ({d})" for n, (_, _, _, d) in ACOES.items())


def executar(acao, entrada, saida="", extra=""):
    """Roda a acao e devolve o texto para o Dono. Levanta ArtCraftErro com mensagem clara."""
    if acao not in ACOES:
        import difflib   # modelos gratis erram o nome ('desenhar', 'vetor_desenho'): aceita o mais parecido
        perto = difflib.get_close_matches(str(acao).strip().lower().replace(" ", "_").replace("-", "_"), ACOES, n=1, cutoff=0.6)
        if not perto:
            raise ArtCraftErro(f"Ação desconhecida. Disponíveis: {', '.join(ACOES)}.")
        acao = perto[0]
    app, ext, monta, _ = ACOES[acao]
    entrada, extra = str(entrada or "").strip(), str(extra or "").strip()
    if not entrada:
        raise ArtCraftErro("Faltou informar a entrada (arquivo ou texto).")
    i = entrada if acao in ("vetor_cartaz", "vetor_desenhar", "pdf_juntar", "word_criar") else _entrada(entrada)
    base = "documento" if acao == "word_criar" else "cartaz" if acao == "vetor_cartaz" else "desenho" if acao == "vetor_desenhar" else Path(entrada.split(";")[0]).stem[:30]
    o = _saida(saida or f"{acao.split('_')[0]}-{base}", ext)
    try:
        out = _rodar(app, monta(i, o, extra))
    except (ValueError, KeyError) as e:
        raise ArtCraftErro(f"Parâmetro inválido: {e}")
    except subprocess.TimeoutExpired:
        raise ArtCraftErro("Demorou demais e foi interrompido.")
    if acao in SO_TEXTO:
        return (out[:3500] + ("…" if len(out) > 3500 else "")) or "(sem conteúdo)"
    alvo = Path(o).with_suffix("") if acao == "pdf_dividir" else Path(o)
    if not alvo.exists():   # o app pode sair sem erro e sem gerar nada (formato nao suportado)
        raise ArtCraftErro(f"O app não gerou o arquivo ({out[-150:] or 'sem mensagem'}).")
    return f"Pronto. Resultado em {alvo} (o original não foi alterado)."
