# -*- coding: utf-8 -*-
"""AUTOMELHORIA DO BRANIAC (pedido do Dono, 14/10/2026): o Jarvis melhora o proprio codigo sem o Dono abrir o Claude Code.
  1. CONSELHO de IAs monta o plano (so o pedido e o mapa dos modulos vao para as IAs; nada de WhatsApp/dados pessoais);
  2. o Claude headless (claude -p, mesma assinatura do Dono) IMPLEMENTA no braniac/ seguindo o plano;
  3. o BRANIAC VERIFICA sozinho, sem confiar no implementador: suite inteira passa, nenhum teste a menos, arquivos e travas de
     seguranca protegidos intocados;
  4. aprovado -> commit no git ("automelhoria: ..."), grafo atualizado e servidor reiniciado; reprovado -> tudo desfeito (git reset).
'Jarvis, desfaz a ultima automelhoria' = git revert do ultimo commit de automelhoria (com testes e reinicio).
Limites: uma por vez, no maximo LIMITE_DIA por dia."""
import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from .store import DATA

BRANIAC = Path(__file__).resolve().parent
RAIZ = BRANIAC.parent
ESTADO = DATA / "automelhoria.json"
LIMITE_DIA = 4
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PROTEGIDOS = {"tests/conftest.py", "automelhoria.py", "tests/test_automelhoria.py", "tests/test_seguranca_atender.py", "tests/test_revisao_1410.py"}
# identificadores das travas de seguranca: nenhuma linha que os contenha pode ser criada, mudada ou apagada por automelhoria
TRAVAS = ("def _gate(", "def _gate_envio(", "FAMILIA_LIVRE", "def tem_dado_real", "SENSIVEL", "def trava_destino",
          "def destino_confere", "nao_responder", "def _bloquear", "PROTEGIDOS", "TRAVAS")
_LOCK = threading.Lock()


# ---------- git ----------

def _git(*args, timeout=120):
    r = subprocess.run(["git", *args], cwd=str(BRANIAC), capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=timeout, creationflags=SEM_JANELA)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def _head():
    return _git("rev-parse", "HEAD")[1].strip()


def _arquivos_mudados(base):
    """Rastreados que mudaram desde base + novos nao ignorados (data/ e modelos/ ficam de fora pelo .gitignore)."""
    _, a = _git("diff", "--name-only", base)
    _, b = _git("ls-files", "--others", "--exclude-standard")
    return sorted({l.strip().replace("\\", "/") for l in (a + "\n" + b).splitlines() if l.strip() and not l.startswith(("warning:", "fatal:"))})


def _linhas_alteradas(base):
    _git("add", "-N", ".")    # novos arquivos entram no diff
    _, d = _git("diff", "-U0", base)
    return [l[1:] for l in d.splitlines() if l[:1] in "+-" and not l.startswith(("+++", "---"))]


TRAVAS_DEFS = {"_gate", "_gate_envio", "tem_dado_real", "trava_destino", "destino_confere", "_bloquear", "_eh_familia",
               "FAMILIA_LIVRE", "SENSIVEL", "PROTEGIDOS", "TRAVAS", "TRAVAS_DEFS"}


def _defs(fonte):
    """{nome: codigo} das funcoes/atribuicoes de topo cujo nome esta em TRAVAS_DEFS (o CORPO inteiro, nao so a linha do def)."""
    import ast
    try:
        arv = ast.parse(fonte)
    except SyntaxError:
        return {"<sintaxe invalida>": ""}
    out = {}
    for n in arv.body:
        nomes = [n.name] if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else \
            [t.id for t in getattr(n, "targets", [getattr(n, "target", None)]) if isinstance(t, ast.Name)]
        for nome in nomes:
            if nome in TRAVAS_DEFS:
                out[nome] = ast.get_source_segment(fonte, n)
    return out


def travas_alteradas(base, mudados):
    """Nomes de travas cujo codigo mudou (compara a funcao/valor inteiro antes x depois em cada .py alterado)."""
    alteradas = set()
    for arq in mudados:
        if not arq.endswith(".py") or arq.startswith("tests/"):
            continue
        cod, antes = _git("show", f"{base}:{arq}")
        antes = antes if cod == 0 else ""
        try:
            depois = (BRANIAC / arq).read_text(encoding="utf-8")
        except OSError:
            depois = ""
        a, d = _defs(antes), _defs(depois)
        alteradas |= {k for k in set(a) | set(d) if a.get(k) != d.get(k) and k != "<sintaxe invalida>"}
    return sorted(alteradas)


def _desfazer_ate(base):
    _git("reset", "--hard", base)
    _git("clean", "-fd")          # so arquivos novos NAO ignorados (dados em data/ nunca sao tocados)


# ---------- estado ----------

def _ler():
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _gravar(d):
    DATA.mkdir(exist_ok=True)
    ESTADO.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def _registrar(item):
    d = _ler()
    d.setdefault("historico", []).append(item)
    d["historico"] = d["historico"][-50:]
    _gravar(d)


def feitas_hoje(agora=None):
    hoje = time.strftime("%Y-%m-%d", time.localtime(agora or time.time()))
    return sum(1 for h in _ler().get("historico", []) if h.get("dia") == hoje)


# ---------- etapas ----------

def mapa_modulos(maximo=90):
    """Nome + 1a linha da docstring de cada modulo (contexto tecnico para o conselho, sem dados pessoais)."""
    linhas = []
    for p in sorted(BRANIAC.glob("*.py")):
        try:
            txt = p.read_text(encoding="utf-8")
        except OSError:
            continue
        m = re.search(r'"""(.*?)(?:\n|""")', txt, re.S)
        linhas.append(f"{p.stem}: {(m.group(1).strip() if m else '')[:maximo]}")
    return "\n".join(linhas)


def verificar(base, antes, testes):
    """(ok, motivo). Nao confia no implementador: confere tudo de novo."""
    mudados = _arquivos_mudados(base)
    if not mudados:
        return False, "nenhum arquivo foi alterado"
    proibidos = sorted(set(mudados) & PROTEGIDOS)
    if proibidos:
        return False, f"mexeu em arquivo protegido: {', '.join(proibidos)}"
    travas = sorted(set(travas_alteradas(base, mudados)) | {t for l in _linhas_alteradas(base) for t in TRAVAS if t in l})
    if travas:
        return False, f"mexeu em trava de segurança ({', '.join(travas)})"
    r = testes()
    if not r.get("ok"):
        return False, f"testes falharam ({r.get('falharam')} falha(s): {', '.join(r.get('falhas', [])[:3])})"
    if r.get("passaram", 0) < antes:
        return False, f"sumiram testes ({r.get('passaram')} agora, {antes} antes)"
    return True, f"{len(mudados)} arquivo(s) alterado(s), {r.get('passaram')} testes passando"


def prompt_implementador(pedido, plano):
    return (
        "Você é o IMPLEMENTADOR da AUTOMELHORIA do Braniac, acionado pelo próprio Jarvis (sem o Dono na tela). "
        f"Pedido do Dono: {pedido.strip()} | Plano do conselho de IAs: {plano.strip()[:3000]} | "
        "Regras: 1) mude só o necessário dentro de braniac/ (estilo ponytail: a menor mudança que resolve); "
        "2) para achar o código, consulte braniac/graphify-out/GRAPH_REPORT.md e leia só os arquivos envolvidos; "
        "3) NÃO altere braniac/tests/conftest.py, braniac/automelhoria.py nem nenhuma trava de segurança "
        f"({', '.join(TRAVAS)}); 4) escreva ou ajuste testes em braniac/tests para o que mudou; "
        "5) não faça commit, não reinicie nada, não envie mensagens a ninguém e não toque em braniac/data; "
        "6) se o pedido exigir quebrar uma trava ou for perigoso, não mude nada e explique. "
        "Ao terminar, responda em até 6 linhas, em português, o que mudou e em quais arquivos."
    )


def _rodar_claude_padrao(prompt, timeout=1500):
    """O agente escolhido (agente_dev: Claude, Codex...) implementa; sem agente (nao instalado, sem creditos/limite, BRANIAC_AGENTE=nenhum) o Jarvis programa sozinho com as IAs gratis (dev_livre)."""
    from . import dev_livre
    from . import agente_dev
    if not agente_dev.disponivel():      # sem agente instalado/configurado: o Jarvis programa sozinho
        return dev_livre.rodar(prompt, timeout)
    try:
        cod, saida = agente_dev.rodar(prompt, RAIZ, timeout, editar=True)
    except Exception as e:
        cod, saida = 1, str(e)
    if cod != 0 and re.search(r"limit|credit|quota|usage|billing|rate", saida or "", re.I):
        _desfazer_ate(_head())
        return dev_livre.rodar(prompt, timeout)
    return cod, saida


def _testes_padrao():
    from . import manutencao
    return manutencao.testes()


def _plano_padrao(pedido):
    from . import conselho, jarvis
    from .router import Router
    router = Router()
    tema = (f"Melhoria no código do Braniac (assistente pessoal em Python, servidor local, ~60 módulos). Pedido: {pedido.strip()}. "
            f"Módulos:\n{mapa_modulos()}")
    formato = ("PLANO em até 10 linhas: 1) quais módulos mudar; 2) a menor mudança que resolve; 3) testes a escrever; "
               "4) riscos. Sem código longo.")
    return conselho.reunir(tema, jarvis.consultar_reuniao, lambda p: router.responder("conselho-ias", p)[0], formato)


def reiniciar_servidor():
    """Reinicia o servidor do Braniac num processo SEPARADO (o servidor nao pode se matar e se subir sozinho)."""
    py = Path(sys.executable)
    pyw = py.with_name("pythonw.exe")
    subprocess.Popen([str(pyw if pyw.exists() else py), "-m", "braniac.automelhoria", "reiniciar"], cwd=str(RAIZ),
                     creationflags=SEM_JANELA | getattr(subprocess, "DETACHED_PROCESS", 0),
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _reiniciar_agora():
    time.sleep(5)    # deixa o servidor terminar de mandar o aviso ao Dono
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' OR Name='python.exe'\" | "
          "? { $_.CommandLine -match 'braniac\\.server' } | % { Stop-Process -Id $_.ProcessId -Force }")
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], creationflags=SEM_JANELA, timeout=60)
    time.sleep(3)
    from . import sentinela
    sentinela.subir_braniac(120)


def _atualizar_grafo():
    try:
        exe = Path.home() / ".local" / "bin" / "graphify.exe"
        subprocess.run([str(exe) if exe.exists() else "graphify", "update", "braniac"], cwd=str(RAIZ), capture_output=True,
                       timeout=300, creationflags=SEM_JANELA)
    except Exception:
        pass


# ---------- fluxo ----------

def melhorar(pedido, avisar, plano=None, rodar_claude=None, testes=None, reiniciar=None, agora=None):
    """Executa a automelhoria inteira (bloqueante). avisar(texto) manda progresso ao Dono. Devolve o texto final."""
    pedido = (pedido or "").strip()
    if len(pedido) < 8:
        return "Qual melhoria você quer? Me diga o que mudar no Braniac/Jarvis."
    if feitas_hoje(agora) >= LIMITE_DIA:
        return f"Já fiz {LIMITE_DIA} automelhorias hoje (limite de segurança). Amanhã eu continuo, ou peça ao Claude direto."
    if not _LOCK.acquire(blocking=False):
        return "Já estou no meio de uma automelhoria. Te aviso quando terminar."
    rodar_claude, testes = rodar_claude or _rodar_claude_padrao, testes or _testes_padrao
    reiniciar = reiniciar or reiniciar_servidor
    try:
        if _arquivos_mudados("HEAD"):       # ponto de volta limpo: o que ja estava mudado vira um commit proprio
            _git("add", "-A")
            _git("commit", "-q", "-m", "estado antes da automelhoria")
        base = _head()
        antes = testes()
        if not antes.get("ok"):
            return f"Não comecei: os testes já estavam falhando antes ({', '.join(antes.get('falhas', [])[:3])}). Peça ao Claude para arrumar primeiro."
        avisar("🔧 Automelhoria: chamei o conselho de IAs para planejar.")
        plano = plano if plano is not None else _plano_padrao(pedido)
        avisar("🔧 Plano pronto. O Claude está implementando; eu confiro tudo antes de aplicar.")
        cod, saida = rodar_claude(prompt_implementador(pedido, plano))
        saida = (saida or "").split("[stderr]")[0]
        if cod != 0:
            _desfazer_ate(base)
            return _fim(pedido, False, f"o implementador falhou (código {cod}); nada foi mudado", agora)
        ok, motivo = verificar(base, antes.get("passaram", 0), testes)
        if not ok:
            _desfazer_ate(base)
            return _fim(pedido, False, motivo + "; desfiz tudo, o Braniac ficou como estava", agora)
        _git("add", "-A")
        _git("commit", "-q", "-m", f"automelhoria: {pedido[:70]}\n\nPlano do conselho:\n{plano[:1500]}\n\nImplementador:\n{saida.strip()[-1500:]}")
        _atualizar_grafo()
        reiniciar()
        return _fim(pedido, True, f"{motivo}. O que mudou: {saida.strip()[-600:]}\nVou reiniciar em instantes. "
                                  "Para voltar atrás: 'Jarvis, desfaz a última automelhoria'.", agora, _head())
    except Exception as e:
        try:
            _desfazer_ate(base)
        except Exception:
            pass
        return _fim(pedido, False, f"erro inesperado ({str(e)[:150]}); desfiz o que tinha mudado", agora)
    finally:
        _LOCK.release()


def _fim(pedido, ok, texto, agora=None, commit=""):
    _registrar({"dia": time.strftime("%Y-%m-%d", time.localtime(agora or time.time())), "pedido": pedido[:200], "ok": ok,
                "commit": commit, "resultado": texto[:500]})
    return ("✅ Automelhoria aplicada: " if ok else "❌ Automelhoria não aplicada: ") + texto


def desfazer_ultima(testes=None, reiniciar=None):
    """git revert do ultimo commit 'automelhoria:' (so se nada mais veio depois dele, para nao desfazer trabalho do Claude)."""
    testes, reiniciar = testes or _testes_padrao, reiniciar or reiniciar_servidor
    with _LOCK:
        _, log = _git("log", "--format=%H %s", "-n", "15")
        linhas = [l.split(" ", 1) for l in log.splitlines() if " " in l]
        alvo = next(((h, s) for h, s in linhas if s.startswith("automelhoria:")), None)
        if not alvo:
            return "Não achei nenhuma automelhoria para desfazer."
        if linhas[0][0] != alvo[0]:
            return "Depois da última automelhoria já houve outras mudanças; peça ao Claude para desfazer com cuidado."
        base = _head()
        cod, out = _git("revert", "--no-edit", alvo[0])
        if cod != 0:
            _git("revert", "--abort")
            return f"Não consegui desfazer: {out[-200:]}"
        r = testes()
        if not r.get("ok"):
            _desfazer_ate(base)
            return "Desfazer quebraria os testes; deixei como estava. Peça ao Claude."
        _atualizar_grafo()
        reiniciar()
        return f"↩️ Desfeita a automelhoria «{alvo[1][len('automelhoria: '):]}». Vou reiniciar em instantes."


def em_segundo_plano(pedido, avisar):
    threading.Thread(target=lambda: avisar(melhorar(pedido, avisar)), daemon=True, name="braniac-automelhoria").start()
    return "🔧 Começando a automelhoria: conselho → implementação → testes. Te aviso a cada etapa (leva uns 10 a 25 minutos)."


if __name__ == "__main__" and sys.argv[1:] == ["reiniciar"]:
    _reiniciar_agora()
