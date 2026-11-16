"""Monitor termico do notebook. Fontes: GPU NVIDIA (nvidia-smi), CPU/RAM (psutil) e, SE estiver aberto, o LibreHardwareMonitor/OpenHardwareMonitor (WMI) para a
temperatura da CPU: o Windows nao expoe o sensor da CPU Ryzen sem driver. Sem esse programa, a CPU e avaliada pela carga. Historico em data/termico.csv."""
import csv
import subprocess
import time
from datetime import datetime

import psutil

from .store import DATA

CSV = DATA / "termico.csv"
GPU_ALERTA = 80          # C
CPU_ALERTA = 90          # C (so com sensor)
CARGA_ALERTA = 90        # % de CPU em 3 leituras seguidas (~30 min no tick de 10 min) quando nao ha sensor
COOLDOWN_S = 3600
_ult = {"alerta": 0.0}


def _gpu():
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=8, creationflags=0x08000000)
        return float(r.stdout.split()[0])
    except Exception:
        return None


def _cpu_sensor():
    """Temperatura da CPU via LibreHardwareMonitor/OpenHardwareMonitor se estiverem rodando (WMI); senao None."""
    for ns in ("root/LibreHardwareMonitor", "root/OpenHardwareMonitor"):
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-Command",
                                f"(Get-CimInstance -Namespace {ns} -ClassName Sensor -ErrorAction Stop | Where-Object {{$_.SensorType -eq 'Temperature' -and $_.Name -match 'CPU (Package|Core \\(Tctl|Total)|Tctl'}} | Measure-Object Value -Maximum).Maximum"],
                               capture_output=True, text=True, timeout=15, creationflags=0x08000000)
            if r.stdout.strip():
                return float(r.stdout.strip().replace(",", "."))
        except Exception:
            continue
    return None


def ler():
    top = sorted(((p.info["cpu_percent"] or 0, p.info["name"]) for p in psutil.process_iter(["name", "cpu_percent"])), reverse=True)[:3]
    return {"gpu_c": _gpu(), "cpu_c": _cpu_sensor(), "cpu_pct": psutil.cpu_percent(interval=1), "ram_pct": psutil.virtual_memory().percent,
            "carregando": psutil.sensors_battery().power_plugged if psutil.sensors_battery() else None, "top": [n for _, n in top]}


def _registrar(d):
    novo = not CSV.exists()
    with CSV.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if novo:
            w.writerow(["hora", "gpu_c", "cpu_c", "cpu_pct", "ram_pct"])
        w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M"), d["gpu_c"], d["cpu_c"], d["cpu_pct"], d["ram_pct"]])


def _recentes(n=3):
    try:
        return list(csv.DictReader(CSV.open(encoding="utf-8")))[-n:]
    except OSError:
        return []


def motivo(d, recentes):
    """Texto do problema ou ''. Pura (testavel)."""
    if d["gpu_c"] and d["gpu_c"] >= GPU_ALERTA:
        return f"a placa de vídeo está em {d['gpu_c']:.0f} graus"
    if d["cpu_c"] and d["cpu_c"] >= CPU_ALERTA:
        return f"o processador está em {d['cpu_c']:.0f} graus"
    if d["cpu_c"] is None and len(recentes) >= 3 and all(float(r["cpu_pct"] or 0) >= CARGA_ALERTA for r in recentes) and d["cpu_pct"] >= CARGA_ALERTA:
        return f"o processador está a {d['cpu_pct']:.0f}% de uso há muito tempo (sem sensor de temperatura, é o que dá para medir)"
    return ""


def resumo():
    d = ler()
    t = [f"placa de vídeo {d['gpu_c']:.0f} graus" if d["gpu_c"] else "placa de vídeo sem leitura",
         f"processador {d['cpu_c']:.0f} graus" if d["cpu_c"] else f"processador a {d['cpu_pct']:.0f}% de uso (sem sensor de temperatura)", f"memória {d['ram_pct']:.0f}%"]
    return ", ".join(t) + f". Quem mais usa: {', '.join(d['top'])}."


def verificar(avisar):
    """Chamado a cada ~10 min. Registra e, se esquentou (e passou 1 h do ultimo aviso), avisa o Dono."""
    d = ler()
    _registrar(d)
    m = motivo(d, _recentes())
    if m and time.time() - _ult["alerta"] > COOLDOWN_S:
        _ult["alerta"] = time.time()
        avisar(f"🌡 Dono, o notebook está esquentando: {m}. Quem mais usa: {', '.join(d['top'])}. Se der, coloque o notebook em lugar mais ventilado ou numa base elevada.")
        return m
    return ""


_cache = {"d": None, "ts": 0.0, "lendo": False}


def atual():
    """Leitura para a tela de voz: devolve o cache na hora e renova em segundo plano a cada 20 s (ler() demora ~2 s)."""
    import threading

    def _ler():
        try:
            _cache["d"], _cache["ts"] = ler(), time.time()
        finally:
            _cache["lendo"] = False
    if time.time() - _cache["ts"] > 20 and not _cache["lendo"]:
        _cache["lendo"] = True
        threading.Thread(target=_ler, daemon=True).start()
    d = _cache["d"]
    if not d:
        return {"pronto": False}
    return {"pronto": True, "gpu_c": d["gpu_c"], "cpu_c": d["cpu_c"], "cpu_pct": d["cpu_pct"], "ram_pct": d["ram_pct"],
            "quente": bool(motivo(d, []))}
