# -*- coding: utf-8 -*-
"""Servidor LOCAL da instalacao (127.0.0.1): serve a tela e a API que conduz o roteiro. A janela (Tauri) so abre esta pagina.
Recusa quem nao vem do proprio PC (Host/Origin). Chaves digitadas nunca voltam para a tela."""
import json, mimetypes, socket, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from . import (banco, dependencias, hardware, ias_web, navegador, nomes, onboarding, perfil, permissoes, provedores, reuniao, cofre)

UI = Path(__file__).parent / "ui"
PORTA_PADRAO = 8777
JOBS = {}           # nome -> {"estado": "rodando|ok|erro", "texto": str, "pct": int, "dados": {}}
_lock = threading.Lock()


def _job(nome, **kw):
    with _lock:
        j = JOBS.setdefault(nome, {"estado": "parado", "texto": "", "pct": 0, "dados": {}})
        j.update(kw)
        return dict(j)


def _rodar(nome, fn):
    def alvo():
        _job(nome, estado="rodando", texto="", pct=0, dados={})
        try:
            dados = fn(lambda pct=None, texto="": _job(nome, **({"pct": pct} if pct is not None else {}), texto=texto)) or {}
            _job(nome, estado="ok", pct=100, dados=dados)
        except Exception as e:
            _job(nome, estado="erro", texto=str(e)[:300])
    threading.Thread(target=alvo, daemon=True, name="job-" + nome).start()


# ---------- acoes ----------

def estado_geral():
    p = perfil.carregar()
    chaves = provedores.chaves_validas()
    return {
        "perfil": {k: p[k] for k in ("nome_assistente", "voz", "modo_icone", "integracoes", "consentimento_acesso_pc", "etapa", "concluido", "perfil_ia")
                   if k in p},
        "etapas": onboarding.ETAPAS, "integracoes": onboarding.INTEGRACOES,
        "permissoes": permissoes.resumo(), "provedores": provedores.catalogo(), "chaves": chaves,
        "sem_chave": provedores.SEM_CHAVE, "faltando": onboarding.faltando(chaves),
        "ias": {k: {"titulo": v["titulo"]} for k, v in ias_web.ADAPTERS.items()},
        "jobs": {k: dict(v) for k, v in JOBS.items()}, "perguntas_nome": nomes.PERGUNTAS, "perfis_ia": hardware.PERFIS,
    }


def acao(caminho, d):
    if caminho == "/api/etapa":
        e = d.get("etapa")
        if e not in onboarding.ETAPAS:
            raise ValueError("etapa inválida")
        perfil.atualizar(etapa=e)
        return {}
    if caminho == "/api/consentimento":
        permissoes.aplicar_modo(d["modo"])
        return {}
    if caminho == "/api/permissao":
        (permissoes.conceder(d["chave"], bool(d.get("com_filhos"))) if d.get("ativo") else permissoes.revogar(d["chave"]))
        return {}
    if caminho == "/api/emergencia":
        permissoes.revogar_tudo()
        return {}
    if caminho == "/api/hardware":
        info = hardware.detectar()
        perf, motivo = hardware.recomendar(info)
        perfil.atualizar(perfil_ia=perf)
        return {"info": info, "perfil": perf, "motivo": motivo, "detalhe": hardware.PERFIS[perf]}
    if caminho == "/api/perfil-ia":
        if d["perfil"] not in hardware.PERFIS:
            raise ValueError("perfil inválido")
        perfil.atualizar(perfil_ia=d["perfil"])
        return {}
    if caminho == "/api/chave":
        ok, motivo = provedores.cadastrar(d["provedor"], d["chave"])
        return {"ok": ok, "motivo": motivo}
    if caminho == "/api/chave/remover":
        cofre.remover(d["provedor"])
        return {}
    if caminho == "/api/dependencias":
        perf = hardware.PERFIS[perfil.carregar().get("perfil_ia") or "equilibrado"]
        return dependencias.estado(perf["ollama"])
    if caminho == "/api/dependencias/instalar":
        perf = hardware.PERFIS[perfil.carregar().get("perfil_ia") or "equilibrado"]

        def tarefa(prog):
            if not dependencias.ollama_exe():
                raise RuntimeError("O Ollama ainda não está instalado. Instale em ollama.com/download e volte aqui.")
            if not dependencias.ollama_no_ar():
                prog(0, "Iniciando o Ollama…")
                dependencias.subir_ollama()
                for _ in range(30):
                    time.sleep(1)
                    if dependencias.ollama_no_ar():
                        break
            dependencias.baixar_modelo(perf["ollama"], lambda p, t: prog(p, t))
        _rodar("dependencias", tarefa)
        return {}
    if caminho == "/api/ia/abrir":
        ia = d["ia"]
        navegador.abrir_aba(ias_web.ADAPTERS[ia]["url"])
        navegador.mostrar()
        return {}
    if caminho == "/api/ia/estado":
        return {ia: ias_web.logado(ia) for ia in ias_web.ADAPTERS}
    if caminho == "/api/ia/esconder":
        navegador.esconder()
        return {}
    if caminho == "/api/reuniao":
        logadas = [ia for ia in ias_web.ADAPTERS if ias_web.logado(ia)]
        if not logadas:
            raise RuntimeError("Entre em pelo menos uma conta (ChatGPT ou Gemini) antes da reunião.")

        def tarefa(prog):
            r = reuniao.reunir(logadas, progresso=lambda t: prog(None, t))
            navegador.esconder()          # terminou: o navegador do assistente some; so o assistente mexe nele
            return r
        _rodar("reuniao", tarefa)
        return {}
    if caminho == "/api/nome/sugerir":
        return {"nomes": nomes.sugerir(d.get("gostos", ""), d["voz"])}
    if caminho == "/api/nome":
        try:
            onboarding.definir_nome_voz(d["nome"], d["voz"])
        except onboarding.Pendencia as e:
            return {"ok": False, "motivo": str(e)}
        return {"ok": True, "frase": nomes.frase_de_acordar(d["nome"])}
    if caminho == "/api/integracoes":
        onboarding.definir_integracoes(d.get("lista", []))
        return {}
    if caminho == "/api/icone":
        onboarding.definir_icone(d["modo"])
        return {}
    if caminho == "/api/concluir":
        try:
            onboarding.concluir()
        except onboarding.Pendencia as e:
            return {"ok": False, "motivo": str(e)}
        return {"ok": True}
    raise KeyError(caminho)


class Handler(BaseHTTPRequestHandler):
    server_version = "braniac-seed"

    def log_message(self, *a):
        pass

    def _local(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost", "[::1]")

    def _json(self, obj, cod=200):
        corpo = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(cod)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        if not self._local():
            return self._json({"erro": "host negado"}, 403)
        if self.path == "/api/estado":
            return self._json(estado_geral())
        nome = "index.html" if self.path in ("/", "") else self.path.lstrip("/").split("?")[0]
        arq = (UI / nome).resolve()
        if UI.resolve() not in arq.parents and arq != UI.resolve() or not arq.is_file():
            return self._json({"erro": "não encontrado"}, 404)
        corpo = arq.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", (mimetypes.guess_type(str(arq))[0] or "application/octet-stream") + "; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def do_POST(self):
        if not self._local():
            return self._json({"erro": "host negado"}, 403)
        origem = self.headers.get("Origin")
        if origem and origem.split("//")[-1].split(":")[0] not in ("127.0.0.1", "localhost"):
            return self._json({"erro": "origem negada"}, 403)    # outro site nao aciona esta API
        try:
            n = int(self.headers.get("Content-Length") or 0)
            d = json.loads(self.rfile.read(n) or b"{}")
            return self._json(acao(self.path, d))
        except KeyError:
            return self._json({"erro": "rota desconhecida"}, 404)
        except Exception as e:
            return self._json({"erro": str(e)[:300]}, 400)


def porta_livre(preferida=PORTA_PADRAO):
    for p in range(preferida, preferida + 30):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    raise RuntimeError("sem porta livre")


def servir(porta=None, bloquear=True):
    porta = porta or porta_livre()
    srv = ThreadingHTTPServer(("127.0.0.1", porta), Handler)
    if bloquear:
        srv.serve_forever()
    else:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, porta


if __name__ == "__main__":
    porta = int(sys.argv[1]) if len(sys.argv) > 1 else None
    srv, porta = servir(porta, bloquear=False)
    print(f"BRANIAC instalação em http://127.0.0.1:{porta}", flush=True)
    while True:
        time.sleep(3600)
