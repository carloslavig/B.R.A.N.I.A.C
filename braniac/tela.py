# -*- coding: utf-8 -*-
"""Jarvis USA O NOTEBOOK do Dono como uma pessoa (24/10/2026): olha a tela, clica, digita e aperta teclas, passo a passo, ate cumprir a tarefa.
Ciclo: foto da tela -> IA com visao decide UMA acao (coordenadas 0-1000) -> executa -> repete (maximo MAX_PASSOS).
Travas: nao digita senha/cartao/codigo; PARA e pergunta antes de enviar, pagar, apagar, aceitar termos ou instalar; nao resolve CAPTCHA;
tela de WhatsApp/banco/senha NAO vai para IA online (para e avisa); atalhos perigosos barrados; 'parar()' ou o arquivo data/tela_parar interrompe na hora;
mouse no canto superior esquerdo tambem para. Tudo fica em data/tela.log (as fotos NAO sao guardadas)."""
import ctypes
import json
import re
import time
from ctypes import wintypes
from pathlib import Path

DADOS = Path(__file__).resolve().parent / "data"
MAX_PASSOS = 40
PARAR_ARQ = DADOS / "tela_parar"
_parar = [False]
SENSIVEL_JANELA = re.compile(r"(?i)whatsapp|banco|bradesco|ita[uú]|nubank|caixa econ|santander|inter\b|senha|password|login|entrar|gov\.br|paypal|cart[aã]o|pix|carteira|bitcoin|binance")
RISCO_TEXTO = re.compile(r"(?i)senha|password|cart[aã]o|cvv|cpf|token|c[oó]digo de verifica|pix|transfer|pagar|comprar|apagar|excluir|deletar|enviar|publicar|instalar|aceitar|concordo")
TECLAS_BARRADAS = {"alt+f4", "win+r", "ctrl+alt+delete", "ctrl+shift+esc", "win+x", "ctrl+shift+delete"}

user32 = ctypes.windll.user32
try:
    user32.SetProcessDPIAware()
except Exception:
    pass

VK = {"enter": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B, "backspace": 0x08, "delete": 0x2E, "space": 0x20, "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
      "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22, "ctrl": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B}
for _i in range(1, 13):
    VK[f"f{_i}"] = 0x6F + _i


def _canto():
    p = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x < 3 and p.y < 3


def parar():
    _parar[0] = True
    return "Parei de mexer no notebook."


def _log(msg):
    try:
        DADOS.mkdir(exist_ok=True)
        with open(DADOS / "tela.log", "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {msg}\n")
    except OSError:
        pass


def janela_ativa():
    h = user32.GetForegroundWindow()
    n = user32.GetWindowTextLengthW(h)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(h, buf, n + 1)
    return buf.value


def tamanho():
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def foto():
    """PNG da tela inteira (reduzido para ~1280 de largura: a IA responde em 0-1000, entao a escala nao importa)."""
    import io
    from PIL import ImageGrab
    im = ImageGrab.grab(all_screens=False)
    if im.width > 1280:
        im = im.resize((1280, int(im.height * 1280 / im.width)))
    b = io.BytesIO()
    im.convert("RGB").save(b, "JPEG", quality=80)
    return b.getvalue()


def _mover(x, y):
    user32.SetCursorPos(int(x), int(y))


def clicar(nx, ny, duplo=False, direito=False):
    w, h = tamanho()
    _mover(nx / 1000 * w, ny / 1000 * h)
    time.sleep(0.15)
    down, up = (0x0008, 0x0010) if direito else (0x0002, 0x0004)
    for _ in range(2 if duplo else 1):
        user32.mouse_event(down, 0, 0, 0, 0)
        user32.mouse_event(up, 0, 0, 0, 0)
        time.sleep(0.08)


def rolar(nx, ny, quanto):
    w, h = tamanho()
    _mover(nx / 1000 * w, ny / 1000 * h)
    user32.mouse_event(0x0800, 0, 0, int(-quanto * 120) & 0xFFFFFFFF, 0)


def digitar(texto):
    """Digita texto Unicode (SendInput KEYEVENTF_UNICODE) no campo que estiver com foco."""
    class KI(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("extra", ctypes.c_void_p)]

    class MI(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("d", wintypes.DWORD), ("f", wintypes.DWORD), ("t", wintypes.DWORD), ("e", ctypes.c_void_p)]

    class U(ctypes.Union):
        _fields_ = [("ki", KI), ("mi", MI)]

    class IN(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", U)]
    for ch in texto:
        for flags in (0x0004, 0x0004 | 0x0002):
            i = IN(1, U(ki=KI(0, ord(ch), flags, 0, None)))
            user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(IN))
            time.sleep(0.012)   # sem pausa entre apertar e soltar, apps lentos (Bloco de Notas) perdiam e repetiam letras
        time.sleep(0.02)


def tecla(combo):
    partes = [p.strip().lower() for p in re.split(r"\+", combo) if p.strip()]
    if "+".join(partes) in TECLAS_BARRADAS:
        raise ValueError(f"atalho barrado: {combo}")
    codigos = [VK.get(p) or (ord(p.upper()) if len(p) == 1 else None) for p in partes]
    if None in codigos:
        raise ValueError(f"tecla desconhecida: {combo}")
    for c in codigos:
        user32.keybd_event(c, 0, 0, 0)
    for c in reversed(codigos):
        user32.keybd_event(c, 0, 2, 0)
    time.sleep(0.1)


PROMPT = """Voce controla o notebook do Dono para cumprir a TAREFA. Olhe a tela e escolha UMA proxima acao.
TAREFA: {tarefa}
JA FEITO: {historico}
Responda SO um JSON, sem texto fora dele, num destes formatos (coordenadas x,y de 0 a 1000: 0,0 = canto superior esquerdo, 1000,1000 = inferior direito):
{{"acao":"clicar","x":500,"y":500,"porque":"..."}}  |  {{"acao":"duplo_clique","x":..,"y":..}}  |  {{"acao":"clicar_direito","x":..,"y":..}}
{{"acao":"digitar","texto":"..."}}  (digita no campo com foco; clique nele antes)  |  {{"acao":"tecla","combo":"enter"}}  (ex.: ctrl+l, tab, esc)
{{"acao":"rolar","x":500,"y":500,"quanto":-3}}  (negativo = sobe)  |  {{"acao":"esperar"}}
{{"acao":"perguntar","pergunta":"..."}}  quando precisar de decisao do Dono OU for enviar, pagar, apagar, aceitar termos, instalar, ou pedir senha/cartao/codigo/CAPTCHA
{{"acao":"fim","resultado":"o que foi feito/encontrado, curto"}}  quando a tarefa estiver cumprida (ou impossivel: diga por que)
Regras: nunca digite senha, cartao, CPF ou codigo; nunca invente dados; se a tela nao mudou, tente outra coisa; ao terminar de ler algo, devolva em "fim"."""


def _decidir(tarefa, historico, dados):
    from . import imagem
    from .router import carregar_env
    carregar_env()   # chave Gemini (no servidor ja esta; aqui garante em execucao avulsa)
    txt = imagem.descrever(dados, PROMPT.format(tarefa=tarefa, historico="; ".join(historico[-8:]) or "nada ainda"), timeout=60)
    m = re.search(r"\{.*\}", txt, re.S)
    if not m:
        raise ValueError(f"resposta sem JSON: {txt[:80]}")
    return json.loads(m.group(0), strict=False)


def _executar(a):
    k = a.get("acao")
    if k == "clicar":
        clicar(a["x"], a["y"])
    elif k == "duplo_clique":
        clicar(a["x"], a["y"], duplo=True)
    elif k == "clicar_direito":
        clicar(a["x"], a["y"], direito=True)
    elif k == "digitar":
        t = str(a.get("texto", ""))
        if RISCO_TEXTO.search(t) and re.search(r"(?i)senha|password|cvv|cpf|token|cart[aã]o", t):
            raise ValueError("nao digito senha/cartao/CPF/codigo")
        digitar(t)
    elif k == "tecla":
        tecla(a.get("combo", ""))
    elif k == "rolar":
        rolar(a.get("x", 500), a.get("y", 500), float(a.get("quanto", -3)))
    elif k == "esperar":
        time.sleep(2)
    else:
        raise ValueError(f"acao desconhecida: {k}")


def tarefa(objetivo, avisar=None, decidir=None, max_passos=MAX_PASSOS, pausa=1.2):
    """Cumpre `objetivo` mexendo na tela. Devolve o texto final (resultado, pergunta ao Dono, ou motivo de ter parado)."""
    objetivo = (objetivo or "").strip()
    if not objetivo:
        return "Diga o que fazer no notebook."
    if re.search(r"(?i)senha|password|cvv|cart[aã]o de cr[eé]dito|captcha", objetivo):
        return "Nao mexo com senha, cartao ou CAPTCHA: isso e com voce."
    _parar[0] = False
    PARAR_ARQ.unlink(missing_ok=True)
    decidir = decidir or _decidir
    feitos = []
    _log(f"INICIO: {objetivo}")
    for passo in range(1, max_passos + 1):
        if _parar[0] or PARAR_ARQ.exists() or _canto():
            _log("PARADO pelo Dono")
            return "Parei, como pediu. " + ("Ate aqui: " + "; ".join(feitos[-4:]) if feitos else "")
        titulo = janela_ativa()
        if SENSIVEL_JANELA.search(titulo):
            _log(f"parou: janela sensivel '{titulo}'")
            return f"Parei: a janela '{titulo}' pode ter dado pessoal ou financeiro e eu nao mando essa tela para IA online. Continue voce ou me diga para seguir por outro caminho."
        try:
            a = decidir(objetivo, feitos, foto())
        except Exception as e:
            _log(f"passo {passo}: erro ao decidir: {str(e)[:100]}")
            if passo > 2 and len(feitos) == 0:
                return f"Nao consegui enxergar a tela agora ({str(e)[:80]}). Tente de novo em instantes."
            feitos.append("(nao entendi a tela, tentando de novo)")
            time.sleep(2)
            continue
        _log(f"passo {passo} [{titulo[:40]}]: {json.dumps(a, ensure_ascii=False)[:200]}")
        k = a.get("acao")
        if k == "fim":
            return a.get("resultado") or "Pronto."
        if k == "perguntar":
            return "Preciso de voce: " + (a.get("pergunta") or "posso continuar?") + " (me diga e eu sigo)"
        try:
            _executar(a)
        except Exception as e:
            feitos.append(f"falhou {k}: {str(e)[:60]}")
            _log(f"passo {passo}: falhou: {e}")
            if "barrado" in str(e) or "nao digito" in str(e):
                return f"Parei: {e}."
            continue
        feitos.append(f"{k} {a.get('porque') or a.get('texto') or a.get('combo') or ''}".strip()[:80])
        if avisar and passo % 5 == 0:
            avisar(f"…ainda no notebook (passo {passo}): {feitos[-1]}")
        time.sleep(pausa)
    return "Cheguei no limite de passos sem terminar. Ate aqui: " + "; ".join(feitos[-5:])
