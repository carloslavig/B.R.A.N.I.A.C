# -*- coding: utf-8 -*-
"""Vigia de voz: fica de pe desde que o Windows liga e escuta SO a frase 'Jarvis, ta acordado?' enquanto o Braniac esta FECHADO.
Ao ouvir a frase: faz um bip, sobe o Chrome do agente e o servidor do Braniac e pede para ele acordar (o servidor cumprimenta falando e abre a tela de voz).
Com o Braniac no ar, o vigia solta o microfone (quem escuta e a escuta do servidor) e volta a escutar quando o Braniac for fechado.
Uso:  pythonw -m braniac.sentinela   (o atalho na pasta Inicializar do Windows faz isso)"""
import json, socket, subprocess, sys, time, urllib.request
from pathlib import Path
from . import escuta
from .store import DATA

RAIZ = Path(__file__).resolve().parent.parent
LOG = DATA / "sentinela.log"
PORTA_BRANIAC = 8765
PORTA_TRAVA = 8767          # uma instancia so


def _log(txt):
    DATA.mkdir(exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {txt}\n")


def braniac_no_ar():
    for _ in range(2):      # 10/11: durante o Whisper o status passou de 1,5 s e a sentinela ligava/desligava o microfone a cada minuto
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORTA_BRANIAC}/api/status", timeout=5).read(10)
            return True
        except Exception:
            time.sleep(1)
    return False


def porta_aberta(porta):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", porta)) == 0


def _subir_auxiliares(sem_janela):
    """14/10: depois de reiniciar o PC o Ollama (IA local) ficava parado. O OmniRoute foi desligado em 13/11 (sem chave de API, a pedido do Dono)."""
    import shutil
    ollama = shutil.which("ollama")
    if ollama and not porta_aberta(11434):
        subprocess.Popen([ollama, "serve"], creationflags=sem_janela, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _log("subindo o Ollama")


def subir_braniac(esperar_s=90):
    """Abre o Chrome do agente (se preciso) e o servidor do Braniac, sem janela. Devolve True se o Braniac respondeu."""
    sem_janela = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    if not porta_aberta(9222):
        bat = RAIZ / "monitor" / "start-chrome-debug.bat"
        if bat.exists():
            subprocess.Popen(["cmd", "/c", str(bat)], cwd=str(bat.parent), creationflags=sem_janela,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            _log("subindo o Chrome do agente")
    _subir_auxiliares(sem_janela)
    if not braniac_no_ar():
        py = Path(sys.executable)
        pyw = py.with_name("pythonw.exe")
        subprocess.Popen([str(pyw if pyw.exists() else py), "-m", "braniac.server"], cwd=str(RAIZ), creationflags=sem_janela,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _log("subindo o servidor do Braniac")
    fim = time.time() + esperar_s
    while time.time() < fim:
        if braniac_no_ar():
            return True
        time.sleep(1.5)
    return False


def pedir_acordar():
    """Pede ao servidor que acorde: ele cumprimenta falando e abre a tela de voz."""
    req = urllib.request.Request(f"http://127.0.0.1:{PORTA_BRANIAC}/api/escuta-acao", json.dumps({"acao": "acordar"}).encode(),
                                 {"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=20).read()


class Sentinela(escuta.Escuta):
    """Mesma escuta (microfone + Whisper), mas ao reconhecer 'Jarvis, ta acordado?' sobe o Braniac em vez de conversar."""
    def __init__(self, subir=None, acordar_servidor=None, bip=None, **kw):
        super().__init__(**kw)
        self._subir = subir or subir_braniac
        self._acordar_servidor = acordar_servidor or pedir_acordar
        self._bip = bip or self._bip_padrao
        self._subindo = False

    @staticmethod
    def _bip_padrao():
        try:
            import winsound
            winsound.Beep(880, 140)
        except Exception:
            pass

    def acordar(self):   # sobrescreve: nao fala nada aqui, o servidor e quem cumprimenta
        if self._subindo:
            return None
        self._subindo = True
        self._bip()
        _log("FRASE DE ACORDAR ouvida: subindo o Braniac")
        try:
            if self._subir():
                time.sleep(1.5)
                self._acordar_servidor()
                _log("Braniac no ar e acordado")
            else:
                _log("o Braniac nao subiu a tempo")
        except Exception as e:
            _log(f"ERRO ao subir/acordar: {e!r}")
        finally:
            self._subindo = False
        return None


def main():
    trava = socket.socket()
    try:
        trava.bind(("127.0.0.1", PORTA_TRAVA))
    except OSError:
        return          # ja ha um vigia rodando
    _log("vigia de voz iniciado")
    s = Sentinela()
    chrome_fora = servidor_fora = 0
    while True:
        try:
            # 10/11: o Dono fechou o Chrome do Braniac sem querer (2x) e nada reabria: guarda de 2 min no Chrome, 3 min no servidor
            chrome_fora = 0 if porta_aberta(9222) else chrome_fora + 1
            servidor_fora = 0 if porta_aberta(PORTA_BRANIAC) else servidor_fora + 1
            if chrome_fora == 12 or servidor_fora == 18:
                _log("Chrome ou servidor fora do ar ha minutos: religando tudo")
                from . import ligar_tudo
                ligar_tudo.ligar(abrir_interface=False)
                chrome_fora = servidor_fora = 0
        except Exception as e:
            _log(f"ERRO na guarda: {e!r}")
        try:
            if escuta.modo_tela() == "mini":    # modo minimizado: o orbe flutuante fica na tela mesmo com o Braniac fechado
                from . import orbe
                orbe.iniciar_processo()
            if braniac_no_ar():
                if s.estado != "parada":
                    s.desligar()
                    _log("Braniac no ar: vigia solta o microfone")
            elif s.estado == "parada":
                s.ligar()
                _log("Braniac fechado: vigia escutando")
        except Exception as e:
            _log(f"ERRO no laco: {e!r}")
        time.sleep(5)


if __name__ == "__main__":
    main()
