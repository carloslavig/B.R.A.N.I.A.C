# -*- coding: utf-8 -*-
"""Interruptor do Braniac: liga/desliga manual e modo jogo automatico.

Desligado = o roteador recusa mensagens, o Ollama e descarregado da memoria
e o monitor do WhatsApp/Airbnb e pausado (arquivo monitor/PAUSE).
"""
import json, os, subprocess, threading, time
from pathlib import Path
import requests
from .store import DATA

ARQ = DATA / "estado.json"
PAUSE_MONITOR = Path(__file__).parent.parent / "monitor" / "PAUSE"


_LOCK = threading.RLock()  # o servidor, o modo jogo e os comandos mexem no mesmo arquivo


def _ler():
    with _LOCK:
        try:
            return json.loads(ARQ.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"pausado": False, "motivo": "", "modo_jogo_auto": True, "jogo": "", "arma_ate": 0, "atendimento_auto": False}


def _gravar(e):
    with _LOCK:
        DATA.mkdir(exist_ok=True)
        tmp = ARQ.with_suffix(".tmp")
        tmp.write_text(json.dumps(e, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, ARQ)  # troca atomica: ninguem le o arquivo pela metade


def estado():
    return _ler()


def pausado():
    return _ler()["pausado"]


def descarregar_ollama(modelo):
    """keep_alive=0 faz o Ollama liberar RAM/VRAM na hora."""
    try:
        requests.post("http://127.0.0.1:11434/api/generate",
                      json={"model": modelo, "keep_alive": 0}, timeout=5)
    except requests.RequestException:
        pass


def desligar(motivo="manual", jogo="", modelo_local="qwen2.5:3b"):
    e = _ler()
    e.update(pausado=True, motivo=motivo, jogo=jogo, arma_ate=0)  # desligar tambem desarma
    _gravar(e)
    descarregar_ollama(modelo_local)
    try:
        PAUSE_MONITOR.touch()
    except OSError:
        pass


def ligar():
    e = _ler()
    e.update(pausado=False, motivo="", jogo="")
    _gravar(e)
    try:
        PAUSE_MONITOR.unlink()
    except OSError:
        pass


MAX_ARMAR_MIN = 72 * 60          # 26/10: ate 72 h (antes 36 h)
INDEFINIDA = -1                   # 26/10 (pedido do Dono): armar SEM prazo ate ele desarmar (armar(0) ou 'Parar tudo agora')
_DEZ_ANOS_S = 10 * 365 * 24 * 3600


def armar(minutos):
    """Autonomia remota: libera acoes sensiveis vindas do Telegram por N minutos (ou INDEFINIDA). So a interface LOCAL chama isto."""
    e = _ler()
    minutos = int(minutos)
    e["indefinida"] = minutos == INDEFINIDA
    if e["indefinida"]:
        e["arma_ate"] = time.time() + _DEZ_ANOS_S
    else:
        minutos = max(0, min(minutos, MAX_ARMAR_MIN))
        e["arma_ate"] = time.time() + minutos * 60 if minutos else 0
    _gravar(e)
    return e["arma_ate"]


def armada():
    return _ler().get("arma_ate", 0) > time.time()


def armada_indefinida():
    e = _ler()
    return bool(e.get("indefinida")) and e.get("arma_ate", 0) > time.time()


def armada_restante_min():
    return max(0, int((_ler().get("arma_ate", 0) - time.time()) / 60))


def atendimento_auto():
    """Atendimento AUTOMATICO do WhatsApp (vigia.py). Padrao: desligado. So a interface local liga."""
    return bool(_ler().get("atendimento_auto", False))


def set_atendimento_auto(valor):
    e = _ler()
    e["atendimento_auto"] = bool(valor)
    _gravar(e)


def set_modo_jogo_auto(valor):
    e = _ler()
    e["modo_jogo_auto"] = bool(valor)
    _gravar(e)


def processos_rodando():
    try:
        out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True,
                             encoding="cp850", errors="replace", timeout=15, creationflags=0x08000000).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    return {l.split('","')[0].strip('"').lower() for l in out.splitlines() if l}


def jogo_aberto(lista):
    """Devolve o nome do primeiro processo da lista que esta rodando (ou '')."""
    rodando = processos_rodando()
    for nome in lista:
        n = nome.lower()
        if n in rodando or n + ".exe" in rodando:
            return nome
    return ""


def vigiar(cfg_getter, intervalo=10):
    """Thread: pausa sozinho quando um jogo/editor pesado abre; retoma quando fecha.
    So retoma o que ele mesmo pausou (motivo 'jogo'), nunca um desligamento manual."""
    def loop():
        while True:
            try:
                e = _ler()
                if e.get("modo_jogo_auto", True):
                    achou = jogo_aberto(cfg_getter().get("modo_jogo_processos", []))
                    if achou and not e["pausado"]:
                        desligar("jogo", achou, cfg_getter().get("modelo_local", "qwen2.5:3b"))
                    elif not achou and e["pausado"] and e["motivo"] == "jogo":
                        ligar()
            except Exception:
                pass
            time.sleep(intervalo)
    t = threading.Thread(target=loop, daemon=True, name="braniac-modo-jogo")
    t.start()
    return t
