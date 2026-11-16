# -*- coding: utf-8 -*-
"""AUTO-ATUALIZACAO SEGURA do Braniac (pedido do Dono, 08/10/2026): toda madrugada (03h) o Braniac se confere sozinho.
 - roda a suite de testes inteira (python -m pytest braniac/tests) e compara com a noite anterior (falha NOVA = alerta);
 - verifica dependencias desatualizadas (pip list --outdated) dos pacotes que o Jarvis usa;
 - verifica se os modelos locais configurados (Ollama) estao instalados.
NAO INSTALA NEM ATUALIZA NADA SOZINHA: atualizar pacote com o servidor rodando pode quebrar a voz/escuta (DLLs em uso no Windows).
O resultado vai para o relatorio do bom dia das 6h (rotina.registrar) e fica em data/manutencao.json (painel da interface).
Se algo falhar, nao aplica e avisa. Nunca registra chaves ou tokens (so nomes de pacotes, versoes e contagem de testes)."""
import json, re, subprocess, sys, threading
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent      # pasta Agente (onde 'python -m pytest braniac/tests' roda)
HORA = 3
PACOTES = ("faster-whisper", "edge-tts", "piper-tts", "sounddevice", "requests", "av", "pedalboard", "numpy", "ctranslate2", "onnxruntime")
_rodando = threading.Lock()


def _data():
    from . import store
    return store.DATA


def _arq():
    return _data() / "manutencao.json"


def ultimo():
    try:
        return json.loads(_arq().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _log(txt):
    try:
        _data().mkdir(exist_ok=True)
        with (_data() / "manutencao.log").open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {txt}\n")
    except OSError:
        pass

# o servidor roda no pythonw (sem console): filhos dele herdam handles invalidos e subprocess falha com WinError 6; python.exe + CREATE_NO_WINDOW resolve
PY = sys.executable.replace("pythonw.exe", "python.exe")


def _rodar(cmd, timeout):
    r = subprocess.run(cmd, cwd=str(RAIZ), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def testes(rodar=_rodar):
    """{'ok', 'passaram', 'falharam', 'falhas': [nomes]}. ok = nenhuma falha (erro ao rodar tambem conta como falha)."""
    try:
        cod, saida = rodar([PY, "-m", "pytest", "braniac/tests", "-q", "-p", "no:cacheprovider"], 1200)
    except Exception as e:
        return {"ok": False, "passaram": 0, "falharam": 0, "falhas": [], "erro": str(e)[:120]}
    num = lambda rot: int((re.search(rf"(\d+) {rot}", saida) or [0, 0])[1])
    falhas = sorted(set(re.findall(r"^FAILED (\S+?)(?:\[| - |$)", saida, re.M)) | set(re.findall(r"^ERROR (\S+?)(?:\[| - |$)", saida, re.M)))
    res = {"ok": cod == 0, "passaram": num("passed"), "falharam": num("failed") + num("error"), "falhas": falhas}
    if cod not in (0, 1):
        res["erro"] = f"pytest saiu com código {cod}"
    return res


def dependencias(rodar=_rodar):
    """[(pacote, versao_atual, versao_nova)] so dos pacotes que o Jarvis usa. Erro de rede -> None (nao e falha do Braniac)."""
    try:
        cod, saida = rodar([PY, "-m", "pip", "list", "--outdated", "--format=json", "--disable-pip-version-check"], 300)
        lista = json.loads(saida[saida.find("["): saida.rfind("]") + 1] or "[]")
    except Exception:
        return None
    alvo = {p.lower().replace("_", "-") for p in PACOTES}
    return [(d["name"], d.get("version"), d.get("latest_version")) for d in lista if d.get("name", "").lower().replace("_", "-") in alvo]


def modelos(tags=None):
    """Modelos locais configurados (providers.json) que NAO estao instalados no Ollama. None se o Ollama nao respondeu."""
    try:
        cfg = json.loads((Path(__file__).parent / "providers.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    queridos = {cfg.get("modelo_local")} | {p.get("modelo") for p in cfg.get("cadeia", []) if p.get("tipo") == "ollama"}
    queridos.discard(None)
    if tags is None:
        try:
            import urllib.request
            with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=5) as r:   # nao liga o Ollama: so pergunta se ele ja esta rodando
                tags = [m["name"] for m in json.load(r).get("models", [])]
        except Exception:
            return None
    inst = set(tags) | {t.split(":")[0] + ":latest" for t in tags if ":" not in t}
    return sorted(q for q in queridos if q not in inst and f"{q}:latest" not in inst)


def organizador_rodar(registrar):
    from . import organizador
    organizador.rodar(registrar)


def seguranca_rodar(registrar):
    from . import seguranca
    seguranca.rodar(registrar)


def predio_feitos(registrar, horas=24):
    """Uma linha com o que cada agente do predio fez nas ultimas horas (alertas/respostas/pedidos que enviou no barramento)."""
    import time
    from . import barramento
    conta = {}
    for m in barramento.historico(500):
        if m["ts"] >= time.time() - horas * 3600 and m["tipo"] != "pedido":
            conta[m["de"]] = conta.get(m["de"], 0) + 1
    if conta:
        registrar("🏢 Prédio nas últimas 24 h (mensagens de cada agente): " + ", ".join(f"{k} {v}" for k, v in sorted(conta.items(), key=lambda x: -x[1])) + ".")


def rodar_manutencao(rodar=_rodar, tags=None, registrar=None):
    """Uma rodada completa. Devolve o resumo gravado. Nada e instalado/alterado: so confere e relata."""
    if not _rodando.acquire(blocking=False):
        return {"resumo": "já está rodando"}
    try:
        anterior = ultimo()
        if rodar is _rodar:     # grafo do codigo (Graphify) atualizado toda madrugada, sem custo de IA (14/10)
            from . import automelhoria
            automelhoria._atualizar_grafo()
        t = testes(rodar)
        novas = sorted(set(t["falhas"]) - set(anterior.get("falhas", []))) if anterior else t["falhas"]
        dep = dependencias(rodar)
        mod = modelos(tags)
        partes = [f"🔧 Manutenção da madrugada: testes {t['passaram']} ok / {t['falharam']} com falha"
                  + (f" — ⚠️ {len(novas)} falha(s) NOVA(S) desde ontem: {', '.join(n.split('::')[-1] for n in novas[:5])}" if novas and anterior else "")
                  + (f" ({t['erro']})" if t.get("erro") else "") + "."]
        if dep:
            partes.append("📦 Atualizações disponíveis (NÃO apliquei; peça ao Claude para testar e aplicar): " +
                          ", ".join(f"{n} {a}→{b}" for n, a, b in dep[:8]) + ".")
        elif dep is None:
            partes.append("📦 Não consegui verificar atualizações (sem internet?).")
        else:
            partes.append("📦 Dependências em dia.")
        if mod:
            partes.append("🧠 Modelos locais configurados mas não instalados no Ollama: " + ", ".join(mod) + " (o Braniac usa outro da cadeia).")
        elif mod is None:
            partes.append("🧠 Ollama não estava rodando: não conferi os modelos.")
        resumo = " ".join(partes)
        res = {"quando": f"{datetime.now():%d/%m %H:%M}", "dia": f"{datetime.now():%Y-%m-%d}", "testes_ok": t["ok"],
               "passaram": t["passaram"], "falharam": t["falharam"], "falhas": t["falhas"], "novas_falhas": novas,
               "dependencias": dep, "modelos_faltando": mod, "resumo": resumo}
        _data().mkdir(exist_ok=True)
        _arq().write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
        _log(resumo)
        if registrar is None:
            from . import rotina
            registrar = rotina.registrar
        registrar(resumo)
        if rodar is _rodar:     # 30/10: Downloads organizado, seguranca do PC/rede e feitos de cada agente entram no relatorio da madrugada
            for passo in (organizador_rodar, seguranca_rodar, predio_feitos):
                try:
                    passo(registrar)
                except Exception as e:
                    _log(f"{passo.__name__} falhou: {e}")
        return res
    finally:
        _rodando.release()


def tick(agora=None, iniciar=None):
    """Chamado pela rotina (~10 min). Uma vez por dia, a partir das 03h e antes do bom dia das 6h, roda em segundo plano."""
    agora = agora or datetime.now()
    if iniciar is None and "PYTEST_CURRENT_TEST" in __import__("os").environ:   # dentro dos testes nunca dispara a suite de verdade (recursao)
        return False
    if not (HORA <= agora.hour < 6) or ultimo().get("dia") == agora.strftime("%Y-%m-%d") or _rodando.locked():
        return False
    (iniciar or (lambda: threading.Thread(target=rodar_manutencao, daemon=True, name="braniac-manutencao").start()))()
    return True
