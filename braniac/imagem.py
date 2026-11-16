# -*- coding: utf-8 -*-
"""Imagens do Braniac: LER (descrever/transcrever o que ha na foto) e CRIAR (gerar/editar), como a voz faz com audio.

Ordem de tentativa: Gemini (chave GEMINI_API_KEY, tenta cada modelo, pula os sem cota) -> Ollama local (so leitura; modelo de visao).
Imagens de comprovante/cartao/documento: a descricao NUNCA repete numeros (regra no prompt); o resto do fluxo segue a trava de seguranca.
"""
import base64, os, time
from . import store

MODELOS_VISAO = ["gemini-flash-latest", "gemini-flash-lite-latest", "gemini-2.5-flash-lite"]
MODELOS_GERAR = ["gemini-2.5-flash-image", "gemini-3.1-flash-image", "gemini-3.1-flash-lite-image"]
MODELOS_LOCAIS = ["qwen2.5vl:3b", "moondream"]   # Ollama, o 1o instalado vale: qwen2.5vl (3,2 GB) le portugues e texto; moondream (1,7 GB) e o basico
MODELO_LOCAL_VISAO = MODELOS_LOCAIS[0]
URL = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"
LIMITE_BYTES = 6_000_000
ULTIMO_MOTOR = ""
LOCAL_PRIMEIRO = True     # Dono (25/10): ler imagem com o Ollama primeiro (privado, sem cota); Gemini so se o local falhar
_cooldown = {}

PROMPT_LER = (
    "Voce ajuda o atendimento de WhatsApp de um pequeno negocio no Brasil. Descreva esta imagem em portugues, objetivo e curto. "
    "Se houver TEXTO (print, cardapio, tabela de precos, taxa de entrega, endereco, recado), transcreva fielmente o texto e os valores. "
    "Se for foto de comida, produto, lugar ou pessoa, diga o que aparece em 1 ou 2 frases. "
    "Se parecer comprovante de pagamento, cartao, documento ou dado bancario, diga SO que e isso (tipo e valor total, se for comprovante) "
    "e NAO escreva numeros de cartao, conta, CPF ou chave. Nao invente nada que nao esteja visivel."
)


class SemImagem(RuntimeError):
    pass


def _chaves():
    ks = [os.environ.get(n, "").strip() for n in ("GEMINI_API_KEY", "GEMINI_API_KEY_2")]
    ks = [k for k in ks if k]
    if not ks:
        raise SemImagem("sem GEMINI_API_KEY")
    return ks


def _mime(dados):
    if dados[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if dados[:4] == b"RIFF" and dados[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def _reduzir(dados, lado=1568):
    """Encolhe fotos grandes (menos cota e mais rapido). Sem Pillow ou imagem ilegivel: devolve como veio."""
    if len(dados) <= 400_000:
        return dados
    try:
        import io
        from PIL import Image
        im = Image.open(io.BytesIO(dados))
        im.thumbnail((lado, lado))
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "JPEG", quality=85)
        return buf.getvalue()
    except Exception:
        return dados


def _post(modelo, corpo, timeout):
    import requests
    r = None
    for k in _chaves():   # a 2a chave (outro projeto Google) tem cota propria: so e usada se a 1a estourar
        r = requests.post(URL.format(modelo), headers={"x-goog-api-key": k}, json=corpo, timeout=timeout)
        if r.status_code != 429:
            break
    return r


def _partes(resp):
    try:
        return resp.json()["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, ValueError):
        return []


def _descrever_gemini(dados, instrucao, timeout):
    import requests
    global ULTIMO_MOTOR
    corpo = {"contents": [{"parts": [{"text": instrucao},
                                     {"inlineData": {"mimeType": _mime(dados), "data": base64.b64encode(dados).decode()}}]}],
             "generationConfig": {"temperature": 0.2, "maxOutputTokens": 700}}
    erros = []
    for modelo in MODELOS_VISAO:
        if _cooldown.get(modelo, 0) > time.time():
            erros.append(f"{modelo}: em descanso")
            continue
        try:
            r = _post(modelo, corpo, timeout)
        except requests.RequestException as e:
            erros.append(f"{modelo}: rede {str(e)[:40]}")
            continue
        if r.status_code != 200:
            _cooldown[modelo] = time.time() + (900 if r.status_code == 429 else 120)
            erros.append(f"{modelo}: HTTP {r.status_code}")
            continue
        txt = " ".join(p.get("text", "") for p in _partes(r)).strip()
        if txt:
            ULTIMO_MOTOR = f"gemini:{modelo}"
            return txt
        erros.append(f"{modelo}: resposta vazia")
    raise SemImagem("; ".join(erros))


PROMPT_LOCAL = "Describe this image in detail. Transcribe any text you see."   # o moondream so entende pedidos curtos em ingles


def _instalados():
    import requests
    try:
        return {m["name"] for m in requests.get("http://127.0.0.1:11434/api/tags", timeout=3).json().get("models", [])}
    except Exception:
        return set()


def _descrever_local(dados, instrucao, timeout):
    import requests
    global ULTIMO_MOTOR
    inst = _instalados()
    modelo = next((m for m in MODELOS_LOCAIS if m in inst or m + ":latest" in inst), None)
    if not modelo:
        raise SemImagem("ollama sem modelo de visao (baixe com: ollama pull " + MODELOS_LOCAIS[0] + ")")
    forte = modelo.startswith("qwen")
    try:
        r = requests.post("http://127.0.0.1:11434/api/generate", timeout=max(timeout, 150) if forte else timeout,
                          json={"model": modelo, "prompt": instrucao if forte else PROMPT_LOCAL, "stream": False,
                                "images": [base64.b64encode(dados).decode()], "options": {"temperature": 0.2}})
    except requests.RequestException as e:
        raise SemImagem(f"ollama indisponivel: {str(e)[:50]}")
    if r.status_code != 200:
        raise SemImagem(f"ollama {modelo}: HTTP {r.status_code}")
    txt = (r.json().get("response") or "").strip()
    if not txt:
        raise SemImagem("ollama: resposta vazia")
    ULTIMO_MOTOR = f"ollama:{modelo}"
    return txt if forte else "(leitura local, aproximada, em inglês) " + txt


def descrever(dados, instrucao=None, timeout=60):
    """Bytes da imagem -> texto (descricao + transcricao do que estiver escrito). Levanta SemImagem se nada funcionar."""
    if not dados:
        raise SemImagem("imagem vazia")
    dados = _reduzir(dados)
    if len(dados) > LIMITE_BYTES:
        raise SemImagem("imagem grande demais")
    instrucao = instrucao or PROMPT_LER
    erros = []
    for f in ((_descrever_local, _descrever_gemini) if LOCAL_PRIMEIRO else (_descrever_gemini, _descrever_local)):
        try:
            return f(dados, instrucao, timeout)
        except SemImagem as e:
            erros.append(str(e))
    raise SemImagem(" | ".join(erros))


def gerar(prompt, referencia=None, timeout=120, referencias=None, pollinations=True):
    """Prompt (e, opcional, imagem de referencia para editar) -> (bytes PNG, caminho salvo em data/imagens). Levanta SemImagem."""
    import requests
    global ULTIMO_MOTOR
    if not (prompt or "").strip():
        raise SemImagem("sem descricao da imagem")
    partes = [{"text": prompt.strip()}]
    refs = list(referencias or []) + ([referencia] if referencia else [])
    for ref in refs[:4]:     # imagens de exemplo do Dono como contexto (ate 4)
        ref = _reduzir(ref)
        partes.append({"inlineData": {"mimeType": _mime(ref), "data": base64.b64encode(ref).decode()}})
    referencia = refs[0] if refs else None
    corpo = {"contents": [{"parts": partes}], "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]}}
    erros = []
    for modelo in MODELOS_GERAR:
        if _cooldown.get(modelo, 0) > time.time():
            erros.append(f"{modelo}: em descanso")
            continue
        try:
            r = _post(modelo, corpo, timeout)
        except requests.RequestException as e:
            erros.append(f"{modelo}: rede {str(e)[:40]}")
            continue
        if r.status_code != 200:
            _cooldown[modelo] = time.time() + (900 if r.status_code == 429 else 120)
            erros.append(f"{modelo}: HTTP {r.status_code}")
            continue
        for p in _partes(r):
            d = (p.get("inlineData") or p.get("inline_data") or {}).get("data")
            if d:
                img = base64.b64decode(d)
                pasta = store.DATA / "imagens"
                pasta.mkdir(parents=True, exist_ok=True)
                ext = ".png" if _mime(img) == "image/png" else ".jpg"
                caminho = pasta / f"{time.strftime('%Y%m%d_%H%M%S')}{ext}"
                caminho.write_bytes(img)
                ULTIMO_MOTOR = f"gemini:{modelo}"
                return img, caminho
        erros.append(f"{modelo}: sem imagem na resposta (recusou?)")
    if pollinations and not referencia:   # plano B gratis (sem chave, so cria; qualidade basica e traz marca d'agua): Pollinations
        try:
            return _gerar_pollinations(prompt.strip(), min(timeout, 90))
        except SemImagem as e:
            erros.append(str(e))
    raise SemImagem("; ".join(erros))


def _gerar_pollinations(prompt, timeout):
    import requests, urllib.parse
    global ULTIMO_MOTOR
    try:
        r = requests.get("https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt[:900]), timeout=timeout,
                         params={"width": 1024, "height": 1024, "nologo": "true", "model": "flux"})
    except requests.RequestException as e:
        raise SemImagem(f"pollinations: rede {str(e)[:40]}")
    if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image/") or len(r.content) < 2000:
        raise SemImagem(f"pollinations: HTTP {r.status_code}")
    pasta = store.DATA / "imagens"
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / f"{time.strftime('%Y%m%d_%H%M%S')}.jpg"
    caminho.write_bytes(r.content)
    ULTIMO_MOTOR = "pollinations:flux"
    return r.content, caminho
