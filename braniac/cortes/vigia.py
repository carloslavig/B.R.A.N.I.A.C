# -*- coding: utf-8 -*-
"""Vigia dos cortes (roda sozinho): checa as lives, grava, processa quando acaba, busca clipes/VODs e publica os aprovados.

Leve enquanto espera (uma consulta a cada poucos minutos). O trabalho pesado (Whisper + NVENC) roda numa fila de um item por
vez e espera o modo jogo do Braniac acabar. Para parar: crie data/cortes/PARAR ou mande o Jarvis desligar os cortes."""
import os, queue, threading, time, traceback
from .. import power
from . import captura, config, fila, pipeline, twitch

PID = config.PASTA / "vigia.pid"
PARAR = config.PASTA / "PARAR"
PAUSA = config.PASTA / "PAUSA_ANDAR"   # pausa duradoura: o andar Claquete assumiu os cortes (nada apagado)


def rodando():
    # (os.kill(pid, 0) no Windows MATA o processo: por isso so a "batida" do arquivo, que o vigia regrava a cada ciclo)
    try:
        return time.time() - PID.stat().st_mtime < config.carregar()["intervalo_min"] * 60 + 300
    except OSError:
        return False


class Vigia:
    def __init__(self):
        self.gravando = {}       # login -> GravacaoLive
        self.jogo = {}           # login -> jogo da live
        self.trabalhos = queue.Queue()
        self.na_fila = set()
        self.ultimo_clipes = {}
        self.ultima_limpeza = 0
        threading.Thread(target=self._operario, daemon=True).start()

    def _enfileirar(self, chave, func, *args):
        if chave in self.na_fila:
            return
        self.na_fila.add(chave)
        self.trabalhos.put((chave, func, args))

    def _operario(self):
        while True:
            chave, func, args = self.trabalhos.get()
            cfg = config.carregar()
            while cfg.get("pausar_no_modo_jogo", True) and power.pausado():  # Dono jogando: GPU/CPU sao dele
                time.sleep(60)
            try:
                func(*args)
            except Exception as e:
                pipeline._log(f"erro em {chave}: {e}\n{traceback.format_exc()[-600:]}")
            finally:
                self.na_fila.discard(chave)

    def ciclo(self):
        cfg = config.carregar()
        canais = [c for c in cfg["canais"] if c.get("login") and c.get("autorizado")]
        for c in canais:
            login = c["login"].lower()
            ccfg = config.para_canal(c, cfg)  # perfil (ex.: gringo em ingles) por cima da config geral
            g = self.gravando.get(login)
            if g and not g.ativa():  # a live acabou (ou caiu): processa a gravacao
                del self.gravando[login]
                g.parar()
                if g.video.exists() and g.video.stat().st_size > 5_000_000:
                    pipeline._log(f"live de {login} terminou; gravacao na fila de cortes")
                    self._enfileirar(f"live:{g.video.name}", pipeline.processar_arquivo, str(g.video), str(g.chat), login, "live",
                                     self.jogo.get(login, ""), ccfg)
                g = None
            if c.get("live", True) and not g:
                try:
                    info = twitch.ao_vivo(login)
                except Exception as e:
                    info = None
                    pipeline._log(f"checagem de {login} falhou: {e}")
                if info:
                    self.gravando[login] = captura.GravacaoLive(login)
                    self.jogo[login] = info.get("jogo", "")
                    pipeline._log(f"{login} AO VIVO ({info.get('jogo') or '?'}): gravando em {self.gravando[login].video.name}")
            # meta diaria (youtube_horarios): com pouco corte em estoque busca clipe de hora em hora, nao so a cada clipes_cada_h
            espera = ccfg["clipes_cada_h"] * 3600
            if len(ccfg.get("youtube_horarios") or []) and fila.estoque(ccfg.get("perfil", "")) < 2 * len(ccfg["youtube_horarios"]):
                espera = min(espera, 3600)
            if c.get("clipes") and time.time() - self.ultimo_clipes.get(login, 0) > espera:
                self.ultimo_clipes[login] = time.time()
                try:
                    # os mais vistos que AINDA NAO viraram corte (antes pegava o top N e, ja vistos, nao entrava nada novo)
                    novos = [cl for cl in twitch.clipes_populares(login, ccfg["clipes_janela_h"], max(ccfg["clipes_max"] * 5, 15),
                                                                  ccfg["clipes_min_views"]) if not fila.ja_visto(f"clipe:{cl['id']}")]
                    for cl in novos[:ccfg["clipes_max"]]:
                        self._enfileirar(f"clipe:{cl['id']}", pipeline.processar_clipe, cl, login, ccfg)
                except Exception as e:
                    pipeline._log(f"busca de clipes de {login} falhou: {e}")
            if c.get("vods") and login not in self.gravando:  # VOD so depois da live (antes disso esta incompleto)
                try:
                    v = twitch.ultimo_vod(login)
                    if v and not fila.ja_visto(f"vod:{v['id']}"):
                        self._enfileirar(f"vod:{v['id']}", pipeline.processar_vod, v["url"], login, v["id"], ccfg)
                except Exception as e:
                    pipeline._log(f"busca de VOD de {login} falhou: {e}")
        if fila.listar("aprovado", 1):
            rel = pipeline.publicar_aprovados()
            if rel:
                pipeline._log(" | ".join(rel))
                pipeline._telegram("sendMessage", data={"text": "📤 Cortes:\n" + "\n".join(rel)})
        if time.time() - self.ultima_limpeza > 3600:
            self.ultima_limpeza = time.time()
            captura.limpar_gravacoes(cfg.get("manter_gravacoes_dias", 3))

    def rodar(self):
        if PAUSA.exists():
            return
        PARAR.unlink(missing_ok=True)
        pipeline._log("vigia dos cortes ligado")
        if not any(c.get("autorizado") for c in config.carregar()["canais"]):
            pipeline._log(f"nenhum canal autorizado em {config.ARQ}: edite a lista 'canais'")
        while not PARAR.exists():
            PID.write_text(str(os.getpid()))
            try:
                self.ciclo()
            except Exception as e:
                pipeline._log(f"erro no ciclo: {e}")
            for _ in range(int(config.carregar()["intervalo_min"] * 60)):
                if PARAR.exists():
                    break
                time.sleep(1)
        for g in self.gravando.values():
            g.parar()
        PID.unlink(missing_ok=True)
        pipeline._log("vigia dos cortes desligado")


def ligar_em_segundo_plano():
    """Sobe o vigia como processo separado (sem janela). Usado pelo Jarvis e pelo LIGAR-CORTES.bat."""
    import subprocess, sys
    if PAUSA.exists():
        return "rotina antiga de cortes da Twitch pausada (03/11/2026); apague data/cortes/PAUSA_ANDAR para religar"
    if rodando():
        return "o vigia dos cortes ja esta ligado"
    PARAR.unlink(missing_ok=True)
    exe = sys.executable.replace("python.exe", "pythonw.exe")
    raiz = config.PASTA.parent.parent.parent
    subprocess.Popen([exe if os.path.exists(exe) else sys.executable, "-m", "braniac.cortes", "vigiar"], cwd=str(raiz),
                     creationflags=0x08000000 if sys.platform == "win32" else 0)
    return "vigia dos cortes ligado"


def desligar():
    PARAR.touch()
    return "pedido de parada enviado ao vigia dos cortes (para no fim do ciclo atual)"
