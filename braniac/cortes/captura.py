# -*- coding: utf-8 -*-
"""Captura: grava a live (streamlink) + chat (IRC anonimo, so leitura), baixa VOD/clipe (yt-dlp)."""
import json, random, socket, subprocess, sys, threading, time
from pathlib import Path
from . import config

SEM_JANELA = 0x08000000 if sys.platform == "win32" else 0


class GravacaoLive:
    """Grava a live num .ts e o chat num .jsonl ({"t": segundos desde o inicio, "msg": texto}). Termina sozinha quando a live acaba."""

    def __init__(self, login, pasta=None):
        self.login = login
        carimbo = time.strftime("%Y%m%d_%H%M")
        pasta = Path(pasta or config.sub("gravacoes"))
        self.video = pasta / f"{login}_{carimbo}.ts"
        self.chat = pasta / f"{login}_{carimbo}.chat.jsonl"
        self.inicio = time.time()
        self._parar = threading.Event()
        self.proc = subprocess.Popen(
            ["streamlink", "--twitch-disable-ads", "--retry-streams", "10", "--retry-max", "3", "--stream-segment-threads", "2",
             "-o", str(self.video), f"https://www.twitch.tv/{login}", "720p60,720p,best"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=SEM_JANELA)
        self.th_chat = threading.Thread(target=self._chat, daemon=True)
        self.th_chat.start()

    def ativa(self):
        return self.proc.poll() is None

    def parar(self):
        self._parar.set()
        if self.ativa():
            self.proc.terminate()
            try:
                self.proc.wait(30)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def _chat(self):
        """IRC da Twitch com usuario anonimo 'justinfan' (somente leitura, sem conta e sem senha)."""
        while not self._parar.is_set() and self.ativa():
            try:
                s = socket.create_connection(("irc.chat.twitch.tv", 6667), timeout=30)
                s.sendall(f"NICK justinfan{random.randint(10000, 99999)}\r\nJOIN #{self.login}\r\n".encode())
                buf = b""
                with open(self.chat, "a", encoding="utf-8") as f:
                    while not self._parar.is_set() and self.ativa():
                        try:
                            pedaco = s.recv(4096)
                        except socket.timeout:
                            continue
                        if not pedaco:
                            break
                        buf += pedaco
                        *linhas, buf = buf.split(b"\r\n")
                        for ln in linhas:
                            t = ln.decode("utf-8", "replace")
                            if t.startswith("PING"):
                                s.sendall(b"PONG :tmi.twitch.tv\r\n")
                            elif " PRIVMSG #" in t:
                                msg = t.split(" PRIVMSG #", 1)[1].split(" :", 1)
                                f.write(json.dumps({"t": round(time.time() - self.inicio, 1), "msg": (msg[1] if len(msg) > 1 else "")[:200]},
                                                   ensure_ascii=False) + "\n")
                        f.flush()
                s.close()
            except OSError:
                time.sleep(10)


def _ytdlp(args, timeout=None):
    p = subprocess.run(["yt-dlp", "--no-progress", "--no-warnings", *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout, creationflags=SEM_JANELA)
    if p.returncode != 0:
        raise RuntimeError("yt-dlp: " + p.stderr.strip()[-400:])
    return p.stdout


def baixar(url, destino_sem_ext, so_audio=False, trecho=None):
    """Baixa video (ou so o audio) com yt-dlp. trecho=(ini, fim) em segundos baixa so aquele pedaco do VOD. Devolve o caminho."""
    destino_sem_ext = Path(destino_sem_ext)
    destino_sem_ext.parent.mkdir(parents=True, exist_ok=True)
    fmt = "bestaudio/Audio_Only/worst" if so_audio else "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"
    args = ["-f", fmt, "-o", str(destino_sem_ext) + ".%(ext)s", "--print", "after_move:filepath"]
    if trecho:
        args += ["--download-sections", f"*{trecho[0]:.1f}-{trecho[1]:.1f}", "--force-keyframes-at-cuts"]
    saida = _ytdlp(args + [url], timeout=6 * 3600)
    linhas = [l for l in saida.splitlines() if l.strip()]
    if linhas and Path(linhas[-1]).exists():
        return Path(linhas[-1])
    achados = sorted(destino_sem_ext.parent.glob(destino_sem_ext.name + ".*"))
    if not achados:
        raise RuntimeError("download terminou sem arquivo")
    return achados[-1]


def limpar_gravacoes(dias):
    """Apaga gravacoes/downloads temporarios (feitos pelo proprio sistema) mais velhos que `dias`. Os cortes prontos ficam."""
    limite = time.time() - dias * 86400
    for pasta in ("gravacoes", "tmp"):
        for p in config.sub(pasta).rglob("*"):
            try:
                if p.is_file() and p.stat().st_mtime < limite:
                    p.unlink()
            except OSError:
                pass
