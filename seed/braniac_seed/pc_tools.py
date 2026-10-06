# -*- coding: utf-8 -*-
"""Ferramentas do assistente no PC. TODAS passam pelo sistema de permissoes (permissoes.exigir) e, quando perigosas, pedem CONFIRMACAO da pessoa.
Cada ferramenta devolve texto (ou texto + imagem) para a PESSOA; o resultado nunca volta para uma IA decidir o proximo passo
(isso fecha a porta para 'injecao de comando' escondida em arquivos ou mensagens)."""
import ctypes, os, re, shutil, subprocess, sys, time, webbrowser
from pathlib import Path
from . import permissoes

BLOQUEADOS = ("\\.ssh", "\\appdata\\roaming\\microsoft\\credentials", "\\appdata\\roaming\\microsoft\\protect", "login data", "\\cookies",
              "braniac-dados", "\\navegador\\", ".kdbx", "id_rsa", "\\.aws", "\\.gnupg")
APPS = {"calculadora": "calc.exe", "bloco de notas": "notepad.exe", "explorador": "explorer.exe", "paint": "mspaint.exe", "configuracoes": "ms-settings:",
        "navegador": "msedge.exe", "edge": "msedge.exe", "chrome": "chrome.exe", "spotify": "spotify.exe", "word": "winword.exe", "excel": "excel.exe"}
PERIGOSOS = re.compile(r"format-volume|diskpart|\bformat\s+[a-z]:|remove-item\s+.*-recurse\s+[a-z]:\\\s*$|\bdel\s+/s\s+/q\s+[a-z]:\\|\bcipher\s+/w|bcdedit|"
                       r"reg\s+delete\s+hk(lm|cu)\\?\s*$|set-executionpolicy|\bnet\s+user\b", re.I)


class FerramentaErro(RuntimeError):
    pass


def _caminho(p, existe=True):
    cam = Path(os.path.expandvars(os.path.expanduser(p.strip().strip('"')))).resolve()
    if any(b in str(cam).lower() for b in BLOQUEADOS):
        raise FerramentaErro("Esse local é protegido (credenciais/dados do assistente); não acesso por segurança.")
    if existe and not cam.exists():
        raise FerramentaErro(f"Não achei: {cam}")
    return cam


# ---------- ferramentas (devolvem str, ou (str, bytes_png) para imagens) ----------

def status_pc():
    from . import hardware
    info = hardware.detectar()
    return (f"Hora: {time.strftime('%d/%m/%Y %H:%M')} · Memória: {info['ram_gb']} GB · Disco livre: {info['disco_livre_gb']} GB · "
            f"Núcleos: {info['cpus']}" + (f" · Placa de vídeo: {info['gpu']['nome']}" if info.get("gpu") else ""))


def abrir(alvo):
    alvo = alvo.strip()
    if re.match(r"https?://", alvo, re.I):
        webbrowser.open(alvo)
        return f"Abri {alvo}."
    app = APPS.get(alvo.lower())
    if app:
        os.startfile(app)  # noqa: S606 (so apps conhecidos)
        return f"Abri {alvo}."
    cam = _caminho(alvo)
    os.startfile(str(cam))  # noqa: S606
    return f"Abri {cam}."


def listar_pasta(caminho):
    cam = _caminho(caminho)
    if not cam.is_dir():
        raise FerramentaErro("Isso não é uma pasta.")
    itens = sorted(cam.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    linhas = [("📁 " if p.is_dir() else "📄 ") + p.name for p in itens[:60]]
    return f"{cam} ({len(itens)} itens)\n" + "\n".join(linhas) + ("\n…" if len(itens) > 60 else "")


def ler_arquivo(caminho, max_chars=3500):
    cam = _caminho(caminho)
    if not cam.is_file():
        raise FerramentaErro("Isso não é um arquivo.")
    if cam.stat().st_size > 2_000_000:
        raise FerramentaErro("Arquivo grande demais para ler por aqui (limite 2 MB).")
    bruto = cam.read_bytes()
    if b"\x00" in bruto[:2000]:
        raise FerramentaErro("Parece um arquivo binário (não é texto).")
    return bruto.decode("utf-8", "replace")[:max_chars]


def escrever_arquivo(caminho, texto):
    cam = _caminho(caminho, existe=False)
    cam.parent.mkdir(parents=True, exist_ok=True)
    existia = cam.exists()
    cam.write_text(texto, encoding="utf-8")
    return f"{'Substituí' if existia else 'Criei'} {cam} ({len(texto)} caracteres)."


def apagar(caminho):
    """Manda para a LIXEIRA (da para restaurar)."""
    cam = _caminho(caminho)
    metodo = "DeleteDirectory" if cam.is_dir() else "DeleteFile"
    cmd = (f"Add-Type -AssemblyName Microsoft.VisualBasic; [Microsoft.VisualBasic.FileIO.FileSystem]::{metodo}"
           f"('{str(cam).replace(chr(39), chr(39) * 2)}','OnlyErrorDialogs','SendToRecycleBin')")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=30, creationflags=0x08000000)
    if r.returncode != 0:
        raise FerramentaErro("não consegui mover para a lixeira: " + r.stderr.strip()[:150])
    return f"Movi para a lixeira: {cam}"


def executar(comando):
    if PERIGOSOS.search(comando):
        raise FerramentaErro("Esse comando pode apagar ou danificar o sistema; recusei por segurança.")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", comando], capture_output=True, text=True, timeout=30, creationflags=0x08000000)
    saida = ((r.stdout or "") + (("\n" + r.stderr) if r.stderr else "")).strip()
    return f"(código {r.returncode})\n{saida[:3000] or '(sem saída)'}"


def captura_tela():
    from PIL import ImageGrab
    import io
    img = ImageGrab.grab(all_screens=True)
    img.thumbnail((1600, 1000))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return "Tela do PC agora:", buf.getvalue()


def whatsapp_nao_lidas():
    from . import whatsapp
    pend = whatsapp.nao_lidas()
    if not pend:
        return "Nenhuma conversa com mensagem não lida. ✅"
    return "Não lidas:\n" + "\n".join(f"• {c['nome']} ({c['nao_lidas']})" for c in pend)


def whatsapp_ler(nome, n=8):
    from . import whatsapp
    quem, msgs = whatsapp.ler_conversa(nome, int(n))
    if not msgs:
        return f"{quem}: sem mensagens de texto recentes."
    return f"Conversa com {quem}:\n" + "\n".join(f"{'Eu' if m['de'] == 'eu' else quem.split()[0]}: {m['texto'][:300]}" for m in msgs if m["texto"])


def whatsapp_enviar(nome, texto):
    from . import whatsapp
    return f"✅ Mensagem enviada para {whatsapp.enviar(nome, texto)}."


# nome -> (descricao para a IA planejar, argumentos, permissao exigida, pede confirmacao, funcao)
FERRAMENTAS = {
    "status_pc": ("Mostra hora, memória e disco do PC.", [], "sistema.status", False, status_pc),
    "abrir": ("Abre um site (http...), um programa conhecido (calculadora, bloco de notas, chrome, spotify...) ou um arquivo/pasta.", ["alvo"], "programas.abrir", False, abrir),
    "listar_pasta": ("Lista os arquivos de uma pasta.", ["caminho"], "arquivos.ler", False, listar_pasta),
    "ler_arquivo": ("Lê um arquivo de texto.", ["caminho"], "arquivos.ler", False, ler_arquivo),
    "escrever_arquivo": ("Cria ou substitui um arquivo de texto.", ["caminho", "texto"], "arquivos.escrever", True, escrever_arquivo),
    "apagar": ("Move um arquivo ou pasta para a lixeira.", ["caminho"], "arquivos.apagar", True, apagar),
    "executar": ("Roda um comando do PowerShell e mostra a saída.", ["comando"], "programas.executar", True, executar),
    "captura_tela": ("Tira um print da tela do PC e envia.", [], "sistema.tela", False, captura_tela),
    "whatsapp_nao_lidas": ("Lista as conversas do WhatsApp com mensagens não lidas.", [], "whatsapp.ler", False, whatsapp_nao_lidas),
    "whatsapp_ler": ("Lê as últimas mensagens de uma conversa do WhatsApp.", ["nome"], "whatsapp.ler", False, whatsapp_ler),
    "whatsapp_enviar": ("Envia uma mensagem de WhatsApp para uma conversa.", ["nome", "texto"], "whatsapp.enviar", True, whatsapp_enviar),
}


def catalogo_para_ia():
    """Texto com as ferramentas que a pessoa LIBEROU (as outras nem aparecem para a IA)."""
    return "\n".join(f"- {n}({', '.join(a)}): {d}" for n, (d, a, perm, _, _) in FERRAMENTAS.items() if permissoes.permitido(perm))


def descrever(nome, args):
    d = FERRAMENTAS[nome]
    return f"{nome}(" + ", ".join(f"{k}={str(v)[:80]!r}" for k, v in args.items()) + ")"


def precisa_confirmar(nome):
    return FERRAMENTAS[nome][3]


def executar_ferramenta(nome, args):
    """Valida a permissao e executa. Levanta PermissaoNegada / FerramentaErro. Devolve (texto, imagem_png|None)."""
    if nome not in FERRAMENTAS:
        raise FerramentaErro("Não conheço essa ação.")
    desc, nomes_args, perm, _, fn = FERRAMENTAS[nome]
    permissoes.exigir(perm)
    faltam = [a for a in nomes_args if not str(args.get(a, "")).strip()]
    if faltam:
        raise FerramentaErro("Faltou informar: " + ", ".join(faltam))
    r = fn(**{a: args[a] for a in nomes_args})
    return r if isinstance(r, tuple) else (r, None)
