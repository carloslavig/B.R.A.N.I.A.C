"""Organiza a barra lateral do app do Claude SEM IA (pedido do Dono, 16/11/2026: zero token).

A cada 5 min confere; só grava quando o app do Claude está FECHADO (aberto, ele guarda tudo na memória e grava por cima).
- Título sem status ganha "🟡 Parada · " (app fechado = nada rodando; "▶️" vira parada).
- Conversa sem seção vai para a seção do assunto, por palavra-chave no título/pasta (cria a seção se faltar).
Faz cópia do config antes de gravar, em data/organiza_claude/.
"""
import json, os, shutil, subprocess, threading, time, uuid
from pathlib import Path

LOCAL = Path(os.environ.get("LOCALAPPDATA", ""))
DATA = Path(__file__).parent / "data" / "organiza_claude"
STATUS = ("✅", "🔵", "🟡", "🔁")
PARADA = "🟡 Parada · "
# primeira seção cujo termo aparece no título/pasta; o resto vai para Braniac
SECOES = [
    ("🎬 Parceiro / Vídeos", ("parceiro", "vídeo", "video", "esteira", "prefeitura", "tcm", "aliado", "aliado", "município", "municipio", "capitais", "cidade")),
    ("🧊 Estúdio 3D", ("estúdio 3d", "estudio 3d", "estudio3d", "dono", "motor rust", "render 3d")),
    ("🌐 Sites e clientes", ("site", "landing", "agencia", "cliente", "vercel", "portfólio", "portfolio", "currículo", "curriculo")),
]
PADRAO = "🧠 Braniac e ferramentas"


def perfis():
    """Pastas de dados do app (uma por perfil) que têm config + conversas."""
    achados = []
    for base in (LOCAL / "Claude-Data", LOCAL):
        if not base.is_dir():
            continue
        for p in base.iterdir():
            if p.name.lower().startswith("claude") and (p / "claude_desktop_config.json").is_file() and (p / "claude-code-sessions").is_dir():
                achados.append(p)
    return achados


def app_aberto():
    """True se o app desktop do Claude roda (o CLI do Claude Code não conta)."""
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-c", "(Get-Process claude -ErrorAction SilentlyContinue).Path"],
                           capture_output=True, text=True, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return "WindowsApps" in r.stdout or "AnthropicClaude" in r.stdout
    except Exception:
        return True   # na dúvida não grava


def secao_de(texto):
    t = texto.lower()
    for nome, termos in SECOES:
        if any(x in t for x in termos):
            return nome
    return PADRAO


def titulo_novo(titulo):
    t = (titulo or "").strip()
    if t.startswith("▶️"):
        return PARADA + t[2:].strip()
    if not t or t.startswith(STATUS):
        return None
    return PARADA + t


def _gravar(p, obj):
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def organizar_perfil(perfil):
    """Aplica as regras num perfil. Devolve a lista do que mudou."""
    feito = []
    cfg_p = perfil / "claude_desktop_config.json"
    cfg = json.loads(cfg_p.read_text(encoding="utf-8"))
    escopos = cfg.setdefault("preferences", {}).setdefault("epitaxyPrefs", {}).setdefault("dframe-group-scopes", {})
    mudou_cfg = False
    for arq in (perfil / "claude-code-sessions").glob("*/*/local_*.json"):
        try:
            s = json.loads(arq.read_text(encoding="utf-8"))
        except Exception:
            continue
        if s.get("isArchived"):
            continue
        novo = titulo_novo(s.get("title"))
        if novo:
            s["title"] = novo
            _gravar(arq, s)
            feito.append(f"título: {novo}")
        esc = escopos.setdefault(f"{arq.parent.parent.name}/{arq.parent.name}", {"groups": [], "assignments": {}, "order": {}})
        chave = "code:" + s["sessionId"]
        if chave in esc.setdefault("assignments", {}):
            continue
        nome = secao_de(f"{s.get('title', '')} {s.get('cwd', '')}")
        g = next((g for g in esc.setdefault("groups", []) if g.get("name") == nome), None)
        if not g:
            g = {"id": "cg-" + str(uuid.uuid4()), "name": nome, "mode": "code"}
            esc["groups"].append(g)
        esc["assignments"][chave] = g["id"]
        esc.setdefault("order", {}).setdefault(g["id"], []).append(chave)
        mudou_cfg = True
        feito.append(f"seção {nome}: {s.get('title')}")
    if mudou_cfg:
        DATA.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cfg_p, DATA / f"{perfil.name}-{time.strftime('%Y%m%d-%H%M%S')}.json")
        _gravar(cfg_p, cfg)
    return feito


def ciclo():
    if app_aberto():
        return []
    feito = []
    for p in perfis():
        try:
            feito += organizar_perfil(p)
        except Exception as e:
            feito.append(f"erro em {p.name}: {e}")
    if feito:
        DATA.mkdir(parents=True, exist_ok=True)
        with open(DATA / "log.txt", "a", encoding="utf-8") as f:
            f.write(time.strftime("%d/%m %H:%M ") + " | ".join(feito) + "\n")
    return feito


def iniciar():
    def loop():
        while True:
            try:
                ciclo()
            except Exception as e:
                print("organiza_claude:", e, flush=True)
            time.sleep(300)
    threading.Thread(target=loop, daemon=True, name="organiza_claude").start()


if __name__ == "__main__":
    print("app aberto:", app_aberto(), "| perfis:", [p.name for p in perfis()])
    print(ciclo() or "nada a fazer (ou app aberto)")
