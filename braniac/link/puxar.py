# -*- coding: utf-8 -*-
"""O Braniac PEDE ao Aliado o proximo video quando esta livre (pull; conselho de IAs, 13/11/2026: mensagem estruturada + trava local).
So pede se: todos os pedidos de producao estao entregues/erro/esperando (parado nao segura a fila), nenhum render na fila, GPU abaixo de 80 C, fora da madrugada (7h-22h),
2 h desde o ultimo pedido e no maximo 3 por dia. Cada pedido leva um id unico (o Aliado responde com o pacote; repetir nao duplica)."""
import json
import subprocess
import time
import uuid
from pathlib import Path

INTERVALO_S, MAX_DIA, TEMP_MAX = 2 * 3600, 3, 80
_estado_fn = None      # testes trocam


def _arq():
    from ..store import DATA
    return DATA / "link" / "puxar.json"


def _estado():
    try:
        return json.loads(_arq().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"pedidos": []}


def temperatura_gpu():
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10,
                           creationflags=0x08000000)
        return int(r.stdout.strip().splitlines()[0])
    except Exception:
        return None


def tempo_medio():
    from .render_parceiro import PACOTE
    try:
        ts = [json.loads(l)["minutos"] for l in (PACOTE / "videos" / "tempos.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        return round(sum(ts[-5:]) / len(ts[-5:])) if ts else None
    except (OSError, ValueError, KeyError):
        return None


def livre(producao_pedidos, fila_ocupada, temp, agora):
    """Motivo para NAO pedir agora, ou None se pode pedir."""
    h = time.localtime(agora).tm_hour
    if not 7 <= h < 22:
        return "madrugada"
    if any(x["etapa"] not in ("entregue", "erro", "esperando") for x in producao_pedidos):   # parado (esperando) nao segura a fila
        return "ainda ha pedido em andamento"
    if fila_ocupada:
        return "render na fila"
    if temp is not None and temp >= TEMP_MAX:
        return f"GPU a {temp} C"
    e = _estado()
    hoje = [p for p in e["pedidos"] if time.strftime("%Y-%m-%d", time.localtime(p["ts"])) == time.strftime("%Y-%m-%d", time.localtime(agora))]
    if len(hoje) >= MAX_DIA:
        return "limite do dia"
    if e["pedidos"] and agora - e["pedidos"][-1]["ts"] < INTERVALO_S:
        return "pedido recente"
    return None


def talvez_pedir(enviar, producao_pedidos, fila_ocupada, agora=None):
    """enviar(texto) -> bool (entregue). Devolve o id do pedido enviado, ou None."""
    agora = agora or time.time()
    temp = temperatura_gpu()
    if livre(producao_pedidos, fila_ocupada, temp, agora):
        return None
    pid = uuid.uuid4().hex[:10]
    med = tempo_medio()
    txt = (f"PEDIDO PROXIMO v1 · id={pid} · O Braniac está livre (fila vazia" + (f", GPU {temp} °C" if temp is not None else "") + "). "
           "Pode mandar o próximo vídeo da sua fila: produção completa (zip com LEIA-PRIMEIRO, como o 143) ou só render (video-NNN.zip, ou meta.json + audio.mp3). "
           + (f"Tempo médio de render aqui: {med} min. " if med else "") + "Se não houver vídeo, responda SEM PEDIDO " + pid + ".")
    if not enviar(txt):
        return None
    e = _estado()
    e["pedidos"] = (e["pedidos"] + [{"id": pid, "ts": agora}])[-50:]
    _arq().parent.mkdir(parents=True, exist_ok=True)
    _arq().write_text(json.dumps(e, ensure_ascii=False), encoding="utf-8")
    return pid

