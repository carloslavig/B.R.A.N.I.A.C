# -*- coding: utf-8 -*-
"""TAXA DO SE PIQUE (30/10/2026): API que confirma a "ajuda de custo" de 3% do app de taximetro. O app informa {aparelho, nome, valor}; o COFRE (leitura da
InfinitePay, so leitura) procura no extrato um Pix recebido com esse nome e esse valor e marca a solicitacao como confirmada. Nunca paga, transfere nem mexe na conta.
Rede: servidor local (127.0.0.1:8766, so 3 rotas) + tunel rapido do cloudflared; o endereco do tunel e publicado em vaquinha-site/sepique-api.json para o app achar.
Dados em data/taxa_sepique.json (nomes de quem pagou ficam so no PC)."""
import json
import os
import re
import secrets
import shutil
import subprocess
import threading
import time
import unicodedata
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .store import DATA

ESTADO = DATA / "taxa_sepique.json"
PORTA = 8766
MIN_CENTAVOS, MAX_CENTAVOS = 1000, 500000        # R$ 10,00 a R$ 5.000,00
EXPIRA_S = 72 * 3600                              # sem Pix correspondente em 72 h -> nao_encontrada
GUARDA_S = 30 * 86400                             # solicitacoes antigas somem do arquivo
INTERVALO_LEITURA_S = 180                         # le o extrato no maximo a cada 3 min, e so se houver solicitacao pendente
MAX_PENDENTES_APARELHO = 3
MAX_NOVAS_10MIN = 20                              # teto global contra abuso
PARTICULAS = {"de", "da", "do", "das", "dos", "e"}
URL_TUNEL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
_lock = threading.RLock()


def _norm(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def _estado():
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _salvar(est):
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    tmp = ESTADO.with_suffix(".tmp")
    tmp.write_text(json.dumps(est, ensure_ascii=False), encoding="utf-8")
    tmp.replace(ESTADO)


# ---------- regras (puras, testaveis) ----------

def _tokens(nome):
    return [t for t in re.findall(r"[a-z]+", _norm(nome)) if len(t) >= 2 and t not in PARTICULAS]


def nome_confere(nome, desc):
    """Todas as partes do nome informado (sem 'de/da/do...') aparecem na descricao do Pix; exige 2+ partes."""
    partes = _tokens(nome)
    if len(partes) < 2:
        return False
    achadas = set(re.findall(r"[a-z]+", _norm(desc)))
    return all(p in achadas for p in partes)


def chave_mov(m):
    return f"{m['data']}|{m.get('hora', '')}|{m['desc']}|{m['valor']}"


def conferir(claims, movs, consumidos, agora):
    """Casa solicitacoes pendentes com Pix RECEBIDOS no extrato: mesmo valor (centavos), nome confere, data >= dia anterior ao pedido, cada Pix serve uma vez.
    Muda `claims`/`consumidos` e devolve os ids confirmados."""
    ok = []
    entradas = [m for m in movs if m["valor"] > 0 and _norm(m["desc"]).startswith("pix")]
    for c in sorted((c for c in claims.values() if c["estado"] == "pendente"), key=lambda c: c["criado"]):
        dia_min = time.strftime("%Y-%m-%d", time.localtime(c["criado"] - 86400))
        for m in entradas:
            k = chave_mov(m)
            if k in consumidos or m["data"] < dia_min or round(m["valor"] * 100) != c["centavos"] or not nome_confere(c["nome"], m["desc"]):
                continue
            c["estado"], c["confirmada_em"], c["movimento"] = "confirmada", agora, k
            consumidos.append(k)
            ok.append(c["id"])
            break
    return ok


def validar(corpo):
    """(aparelho, nome, centavos) ou levanta ValueError com mensagem curta."""
    if not isinstance(corpo, dict):
        raise ValueError("pedido inválido")
    aparelho, nome, cent = corpo.get("aparelho"), corpo.get("nome"), corpo.get("valor_centavos")
    if not isinstance(aparelho, str) or not re.fullmatch(r"[0-9a-fA-F-]{8,64}", aparelho):
        raise ValueError("aparelho inválido")
    if not isinstance(nome, str) or not 5 <= len(nome.strip()) <= 80 or not re.fullmatch(r"[A-Za-zÀ-ÿ'.\- ]+", nome.strip()) or len(_tokens(nome)) < 2:
        raise ValueError("nome inválido")
    if isinstance(cent, bool) or not isinstance(cent, int) or not MIN_CENTAVOS <= cent <= MAX_CENTAVOS:
        raise ValueError("valor inválido (mínimo R$ 10,00)")
    return aparelho.lower(), " ".join(nome.split()), cent


# ---------- operacoes ----------

def _limpar(est, agora):
    for c in est.get("claims", {}).values():
        if c["estado"] == "pendente" and agora - c["criado"] > EXPIRA_S:
            c["estado"] = "nao_encontrada"
    est["claims"] = {i: c for i, c in est.get("claims", {}).items() if agora - c["criado"] < GUARDA_S}


def reivindicar(corpo, agora=None):
    """Registra o aviso de pagamento. Devolve (resposta_json, http). Repetir o mesmo aviso devolve o mesmo id."""
    agora = agora or time.time()
    try:
        aparelho, nome, cent = validar(corpo)
    except ValueError as e:
        return {"erro": str(e)}, 400
    with _lock:
        est = _estado()
        _limpar(est, agora)
        claims = est.setdefault("claims", {})
        for c in claims.values():
            if c["estado"] == "pendente" and (c["aparelho"], c["nome"], c["centavos"]) == (aparelho, nome, cent):
                return {"id": c["id"], "estado": "pendente"}, 200
        if sum(c["estado"] == "pendente" and c["aparelho"] == aparelho for c in claims.values()) >= MAX_PENDENTES_APARELHO \
                or sum(agora - c["criado"] < 600 for c in claims.values()) >= MAX_NOVAS_10MIN:
            return {"erro": "muitas tentativas"}, 429
        id_ = secrets.token_urlsafe(9)
        claims[id_] = {"id": id_, "aparelho": aparelho, "nome": nome, "centavos": cent, "criado": agora, "estado": "pendente"}
        _salvar(est)
    return {"id": id_, "estado": "pendente"}, 200


def status(id_):
    c = _estado().get("claims", {}).get(id_ or "")
    if not c:
        return {"erro": "não encontrado"}, 404
    return {"estado": c["estado"], "valor_centavos": c["centavos"]}, 200


def _brl(cent):
    return "R$ " + f"{cent / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def ciclo(enviar_dono=None, ler=None, agora=None):
    """Se ha solicitacao pendente, le o extrato (no maximo a cada 3 min), confere e avisa o Dono. Devolve quantas foram confirmadas."""
    agora = agora or time.time()
    with _lock:
        est = _estado()
        _limpar(est, agora)
        if not any(c["estado"] == "pendente" for c in est.get("claims", {}).values()):
            _salvar(est)
            return 0
        if agora - est.get("ultima_leitura", 0) < INTERVALO_LEITURA_S:
            return 0
        est["ultima_leitura"] = agora
        _salvar(est)
    try:
        if ler is None:
            from . import financeiro
            ler = lambda: financeiro.ler_conta()[1]     # noqa: E731  (so os movimentos; o Cofre cuida do saldo e da meta)
        movs = ler()
    except Exception:
        return 0                                         # sessao do banco caiu: o Cofre ja avisa o Dono; tenta de novo no proximo ciclo
    with _lock:
        est = _estado()
        consumidos = est.setdefault("consumidos", [])
        feitos = conferir(est.setdefault("claims", {}), movs, consumidos, agora)
        est["consumidos"] = consumidos[-800:]
        _salvar(est)
        confirmadas = [est["claims"][i] for i in feitos]
    for c in confirmadas:
        try:
            if enviar_dono:
                enviar_dono(f"💸 Taxa do Se Pique confirmada: {_brl(c['centavos'])} de {c['nome']}.")
        except Exception:
            pass
    return len(confirmadas)


# ---------- servidor HTTP (so 3 rotas) ----------

class _H(BaseHTTPRequestHandler):
    server_version = "taxa"

    def log_message(self, *a):               # nada de log com nome de gente
        pass

    def _json(self, d, code=200):
        b = json.dumps(d, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/sepique/taxa/saude":
            return self._json({"ok": True})
        if u.path == "/sepique/taxa/status":
            return self._json(*status((parse_qs(u.query).get("id") or [""])[0][:40]))
        self._json({"erro": "não encontrado"}, 404)

    def do_POST(self):
        if urlparse(self.path).path != "/sepique/taxa/reivindicar":
            return self._json({"erro": "não encontrado"}, 404)
        try:
            n = int(self.headers.get("Content-Length") or 0)
            corpo = json.loads(self.rfile.read(n).decode("utf-8")) if 0 < n <= 2048 else None
        except (ValueError, OSError):
            corpo = None
        self._json(*reivindicar(corpo))


def servir():
    srv = ThreadingHTTPServer(("127.0.0.1", PORTA), _H)
    threading.Thread(target=srv.serve_forever, daemon=True, name="taxa-http").start()
    return srv


# ---------- tunel (cloudflared rapido) + endereco publicado para o app ----------

SITE = DATA.parent.parent.parent / "vaquinha-site"      # repo publico que ja serve o total da vaquinha; o app le sepique-api.json de la
_tunel = {"proc": None, "url": None, "inicio": 0.0}


def _exe():
    return shutil.which("cloudflared") or next((p for p in (r"C:\Program Files (x86)\cloudflared\cloudflared.exe", r"C:\Program Files\cloudflared\cloudflared.exe") if os.path.exists(p)), None)


def publicar_url(url):
    """Grava sepique-api.json e publica (commit + push so desse arquivo). Devolve (ok, saida)."""
    def git(*a):
        return subprocess.run(["git", *a], cwd=str(SITE), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90, creationflags=0x08000000)
    try:
        (SITE / "sepique-api.json").write_text(json.dumps({"url": url, "atualizado": time.strftime("%Y-%m-%dT%H:%M")}), encoding="utf-8")
        git("add", "sepique-api.json")
        c = git("commit", "-m", "endereco da API do Se Pique", "--", "sepique-api.json")
        p = git("push")
        return c.returncode == 0 and p.returncode == 0, (c.stdout + c.stderr + p.stderr)[-300:]
    except Exception as e:
        return False, str(e)[:200]


def _ler_url(proc, publicar=publicar_url):
    publicado = False
    for linha in proc.stderr:                           # continua lendo para o cloudflared nunca travar com o pipe cheio
        m = URL_TUNEL.search(linha)
        if m and not publicado:
            _tunel["url"] = m.group(0)
            publicado = publicar(_tunel["url"])[0]
            with _lock:
                est = _estado()
                est["tunel_url"] = _tunel["url"]
                _salvar(est)


def _matar_tunel_antigo():
    """Reinicio do Braniac deixa o cloudflared da execucao anterior orfao: encerra o pid guardado, se ainda for um cloudflared."""
    pid = _estado().get("tunel_pid")
    if not pid:
        return
    nao_mostra = 0x08000000
    quem = subprocess.run(["tasklist", "/FI", f"PID eq {int(pid)}", "/FO", "CSV", "/NH"], capture_output=True, text=True, errors="replace", creationflags=nao_mostra).stdout
    if "cloudflared" in quem.lower():
        subprocess.run(["taskkill", "/PID", str(int(pid)), "/F"], capture_output=True, creationflags=nao_mostra)


def garantir_tunel(publicar=publicar_url):
    """Sobe o tunel se nao estiver de pe (no maximo 1 tentativa a cada 2 min). Devolve True se subiu agora."""
    p = _tunel["proc"]
    if (p and p.poll() is None) or time.time() - _tunel["inicio"] < 120:
        return False
    exe = _exe()
    if not exe:
        return False
    _tunel["inicio"] = time.time()
    _tunel["url"] = None
    if p is None:
        _matar_tunel_antigo()
    proc = subprocess.Popen([exe, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{PORTA}"], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", errors="replace", creationflags=0x08000000)
    _tunel["proc"] = proc
    with _lock:
        est = _estado()
        est["tunel_pid"] = proc.pid
        _salvar(est)
    threading.Thread(target=_ler_url, args=(proc, publicar), daemon=True, name="taxa-tunel").start()
    return True


def iniciar(enviar_dono):
    """Chamado no start do servidor. So liga com o modulo financeiro (Cofre) ativo; o resto roda numa thread a cada minuto."""
    from . import modulos
    if not modulos.ativo("financeiro"):
        return
    try:
        servir()
    except OSError:
        return                                           # porta ocupada: outra copia ja serve

    def loop():
        time.sleep(60)
        while True:
            try:
                from . import power
                if not power.pausado():
                    garantir_tunel()
                    ciclo(enviar_dono)
            except Exception:
                pass
            time.sleep(60)
    threading.Thread(target=loop, daemon=True, name="taxa-sepique").start()
    garantir_tunel()
