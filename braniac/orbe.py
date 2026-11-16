# -*- coding: utf-8 -*-
"""Orbe mini do Jarvis: janelinha sem borda, TRANSPARENTE, sempre por cima, do tamanho do icone de rede da bandeja (+4 px), que voce arrasta pela tela.
Mostra se o Jarvis esta dormindo/ouvindo e se mexe com a sua voz (ouvindo) e com a voz dele (falando), lendo /api/escuta-estado.
  - arrastar (botao esquerdo): move; a posicao fica salva
  - duplo clique: abre a interface completa (e este orbe fecha)
  - botao direito: menu (abrir interface, acordar/descansar, desligar microfone, fechar orbe)
Uso:  pythonw -m braniac.orbe"""
import ctypes, json, math, random, socket, subprocess, sys, threading, time, urllib.request
import tkinter as tk
from pathlib import Path
from .store import DATA

URL = "http://127.0.0.1:8765"
POS = DATA / "orbe_pos.json"
PORTA_TRAVA = 8768
CHAVE = "#010203"            # cor transparente (nao usar no desenho)
TAM_ICONE = 16               # icone de rede da bandeja a 100%
EXTRA = 4                    # o orbe fica 4 px maior (pedido do Dono: 3 a 5 px)


def _dpi():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        return ctypes.windll.user32.GetDpiForSystem() / 96.0
    except Exception:
        return 1.0


def _post(caminho, corpo):
    req = urllib.request.Request(URL + caminho, json.dumps(corpo).encode(), {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=5).read())


def _mix(c1, c2, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def _hex(c):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(v))) for v in c)


class Orbe:
    def __init__(self):
        self.escala = _dpi()
        self.S = max(16, round((TAM_ICONE + EXTRA) * self.escala))     # 20 px a 100%
        self.raiz = tk.Tk()
        r = self.raiz
        r.overrideredirect(True)
        r.attributes("-topmost", True)
        r.config(bg=CHAVE)
        try:
            r.attributes("-transparentcolor", CHAVE)
        except tk.TclError:
            pass
        self.cv = tk.Canvas(r, width=self.S, height=self.S, bg=CHAVE, highlightthickness=0, bd=0)
        self.cv.pack()
        x, y = self._posicao_inicial()
        r.geometry(f"{self.S}x{self.S}+{x}+{y}")
        self.dados = {"estado": "parada", "atividade": "idle", "entrada": 0.0, "fala": 0.0}
        self.vivo = {"e": 0.0, "acordado": 0.0}
        self.fase = 0.0
        self.pontos = [random.uniform(0, 6.283) for _ in range(7)]
        self._arrasto = None
        self._menu = tk.Menu(r, tearoff=0)
        self._menu.add_command(label="Abrir interface", command=self.abrir_interface)
        self._menu.add_command(label="Acordar / Descansar", command=self.alternar)
        self._menu.add_command(label="Desligar / ligar microfone", command=self.microfone)
        self._menu.add_separator()
        self._menu.add_command(label="Fechar orbe", command=self.ocultar)
        for ev, fn in (("<ButtonPress-1>", self._ini), ("<B1-Motion>", self._mover), ("<ButtonRelease-1>", self._fim),
                       ("<Double-Button-1>", lambda e: self.abrir_interface()), ("<Button-3>", self._abrir_menu)):
            self.cv.bind(ev, fn)
        threading.Thread(target=self._consultar, daemon=True).start()
        self.ultimo = time.time()
        self._quadro()

    # ---------- posicao / arrasto ----------
    def _posicao_inicial(self):
        try:
            p = json.loads(POS.read_text(encoding="utf-8"))
            x, y = int(p["x"]), int(p["y"])
            if 0 <= x < self.raiz.winfo_screenwidth() - 4 and 0 <= y < self.raiz.winfo_screenheight() - 4:
                return x, y
        except Exception:
            pass
        return self.raiz.winfo_screenwidth() - round(310 * self.escala), self.raiz.winfo_screenheight() - round(34 * self.escala)

    def _ini(self, e):
        self._arrasto = (e.x_root - self.raiz.winfo_x(), e.y_root - self.raiz.winfo_y())

    def _mover(self, e):
        if self._arrasto:
            self.raiz.geometry(f"+{e.x_root - self._arrasto[0]}+{e.y_root - self._arrasto[1]}")

    def _fim(self, e):
        self._arrasto = None
        try:
            DATA.mkdir(exist_ok=True)
            POS.write_text(json.dumps({"x": self.raiz.winfo_x(), "y": self.raiz.winfo_y()}), encoding="utf-8")
        except OSError:
            pass

    # ---------- acoes ----------
    def _abrir_menu(self, e):
        self._menu.tk_popup(e.x_root, e.y_root)

    def abrir_interface(self):
        """Duplo clique: abre a interface completa MAXIMIZADA e na frente. O orbe continua na tela (e sempre da para reabrir por aqui)."""
        try:
            _post("/api/orbe", {"acao": "abrir"})
        except Exception:
            pass

    def alternar(self):
        try:
            _post("/api/escuta-acao", {"acao": "descansar" if self.dados.get("estado") == "acordado" else "acordar"})
        except Exception:
            pass

    def microfone(self):
        try:
            _post("/api/escuta-acao", {"acao": "ligar" if self.dados.get("estado") == "parada" else "desligar"})
        except Exception:
            pass

    def ocultar(self):
        """'Fechar orbe' de verdade: sai do modo mini (senao o vigia reabriria o orbe em 5 s)."""
        try:
            from . import escuta
            escuta.definir_modo_tela("completo")
        except Exception:
            pass
        self.fechar()

    def fechar(self):
        try:
            self.raiz.destroy()
        except Exception:
            pass

    # ---------- dados do Braniac (thread) ----------
    def _consultar(self):
        while True:
            try:
                d = json.loads(urllib.request.urlopen(URL + "/api/escuta-estado", timeout=2).read())
                self.dados = d
            except Exception:
                self.dados = {"estado": "parada", "atividade": "idle", "entrada": 0.0, "fala": 0.0}
            time.sleep(0.1)

    # ---------- desenho ----------
    def _quadro(self):
        agora = time.time()
        dt = min(0.1, agora - self.ultimo)
        self.ultimo = agora
        d = self.dados
        ativ = d.get("atividade", "idle")
        reativo = d.get("entrada", 0.0) if ativ == "ouvindo" else d.get("fala", 0.0) if ativ == "falando" else (0.25 + 0.2 * math.sin(agora * 7)) if ativ == "pensando" else 0.0
        parada = d.get("estado") == "parada"
        acordado = 1.0 if d.get("estado") == "acordado" else 0.0
        k = min(1.0, dt * (14 if reativo > self.vivo["e"] else 6))
        self.vivo["e"] += (reativo - self.vivo["e"]) * k
        self.vivo["acordado"] += (acordado - self.vivo["acordado"]) * min(1.0, dt * 3)
        e, ac = self.vivo["e"], self.vivo["acordado"]
        respira = 0.5 + 0.5 * math.sin(agora * (1.8 if ac > 0.5 else 0.9))
        brilho = 0.15 if parada else 0.30 + 0.30 * ac + 0.40 * e + 0.08 * respira
        self.fase += dt * (0.6 + 2.2 * ac + 4.0 * e)
        cor = _mix((125, 82, 14), (255, 232, 140), brilho)
        cor2 = _mix((90, 58, 10), (255, 178, 26), brilho)

        S = self.S
        c = S / 2.0
        cv = self.cv
        cv.delete("all")
        raio = S * (0.20 + 0.10 * respira * (0.3 + ac) + 0.12 * e)
        # aro externo + miolo cheio (o miolo e o que voce agarra para arrastar)
        r_aro = S * (0.44 + 0.04 * e)
        cv.create_oval(c - r_aro, c - r_aro, c + r_aro, c + r_aro, outline=_hex(cor2), width=max(1, round(self.escala)))
        cv.create_oval(c - raio, c - raio, c + raio, c + raio, fill=_hex(cor), outline="")
        # pontos orbitando (mais rapidos e abertos quando ha som)
        for i, a in enumerate(self.pontos):
            ang = a + self.fase * (1 + 0.15 * i) * (-1 if i % 2 else 1)
            rr = S * (0.30 + 0.07 * math.sin(self.fase * 2 + i) + 0.07 * e)
            px, py = c + math.cos(ang) * rr, c + math.sin(ang) * rr * (0.55 + 0.45 * (i % 3) / 2)
            t = max(1.0, self.escala * (1.0 + 0.6 * e))
            cv.create_oval(px - t / 2, py - t / 2, px + t / 2, py + t / 2, fill=_hex(cor), outline="")
        self.raiz.after(33, self._quadro)

    def rodar(self):
        self.raiz.mainloop()


def ja_rodando():
    """True se ja ha um orbe aberto. Testa fazendo BIND na porta-trava (se estiver ocupada, o orbe esta la): conectar nao serve, porque o orbe
    nunca atende conexoes e a fila da porta enche."""
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", PORTA_TRAVA))
        return False
    except OSError:
        return True
    finally:
        s.close()


def iniciar_processo():
    """Abre o orbe mini (se ainda nao estiver aberto). Chamado pelo servidor/vigia."""
    if ja_rodando():
        return False
    py = Path(sys.executable)
    pyw = py.with_name("pythonw.exe")
    raiz = Path(__file__).resolve().parent.parent
    sem_janela = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen([str(pyw if pyw.exists() else py), "-m", "braniac.orbe"], cwd=str(raiz), creationflags=sem_janela,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True


def main():
    trava = socket.socket()
    try:
        trava.bind(("127.0.0.1", PORTA_TRAVA))
        trava.listen(1)
    except OSError:
        return      # ja ha um orbe aberto
    Orbe().rodar()


if __name__ == "__main__":
    main()
