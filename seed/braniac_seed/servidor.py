# -*- coding: utf-8 -*-
"""Servidor LOCAL da instalacao (127.0.0.1): serve a tela e a API que conduz o roteiro. A janela (Tauri) so abre esta pagina.
Recusa quem nao vem do proprio PC (Host/Origin). Chaves digitadas nunca voltam para a tela."""
import html, urllib.parse, json, mimetypes, socket, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from . import (paths, guarda, email_diario, assistente, transcricao, voz_nuvem, autostart, banco, dependencias, hardware, ias_web, navegador, nomes, onboarding, perfil, permissoes, provedores, remoto, reuniao, cofre, whatsapp)

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

def _registrar(texto):
    """Diario da instalacao (so no PC): ajuda a achar o que travou, sem enviar nada para fora."""
    try:
        arq = paths.arquivo("instalacao.log")
        if arq.exists() and arq.stat().st_size > 300_000:
            arq.write_text("", encoding="utf-8")
        with arq.open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {texto}\n")
    except OSError:
        pass


def estado_geral():
    p = perfil.carregar()
    chaves = provedores.chaves_validas()
    return {
        "perfil": {k: p[k] for k in ("nome_assistente", "voz", "modo_icone", "integracoes", "consentimento_acesso_pc", "etapa", "concluido", "perfil_ia")
                   if k in p},
        "etapas": onboarding.ETAPAS, "opcionais": onboarding.OPCIONAIS, "integracoes": onboarding.INTEGRACOES,
        "permissoes": permissoes.resumo(), "provedores": provedores.catalogo(), "chaves": chaves,
        "sem_chave": provedores.SEM_CHAVE, "faltando": onboarding.faltando(chaves),
        "ias": {k: {"titulo": v["titulo"]} for k, v in ias_web.ADAPTERS.items()},
        "jobs": {k: dict(v) for k, v in JOBS.items()}, "suspenso": bool(p.get("suspenso")), "stt": transcricao.disponivel(), "concluido": bool(p.get("concluido")), "remoto": remoto.resumo(), "email_diario": email_diario.estado(), "guarda": {"ativa": guarda.ativa(), "ligada": bool(p.get("guarda_ativa")), "permitida": permissoes.permitido("sistema.seguranca"), "resumo": guarda.resumo()}, "autostart": autostart.ativo(), "navegador": navegador.info(),
        "voz": {"nuvem": voz_nuvem.disponivel() and not p.get("voz_privada"), "privada": bool(p.get("voz_privada")), "nome": p.get("voz_nome"), "reserva": bool(p.get("voz_reserva")),
                "estilo": p.get("voz_estilo") or "calmo", "vozes": voz_nuvem.VOZES, "estilos": {k: v[0] for k, v in voz_nuvem.ESTILOS.items()}},
        "nivel": provedores.nivel(chaves), "por_que_mais": provedores.POR_QUE_MAIS, "aviso_passos": provedores.AVISO_PASSOS, "perguntas_nome": nomes.PERGUNTAS, "perfis_ia": hardware.PERFIS,
    }


def acao(caminho, d):
    if caminho == "/api/navegador":
        try:
            navegador.trocar(d["id"])
        except navegador.NavegadorErro as e:
            return {"ok": False, "motivo": str(e)}
        return {"ok": True, "navegador": navegador.info()}
    if caminho == "/api/email/config":
        try:
            return {"ok": True, "email": email_diario.configurar(d.get("client_id"), d.get("client_secret"), d.get("hora_resumo"), d.get("avisos_trabalho"),
                                                                   d.get("resumo_ativo"))}
        except (email_diario.EmailErro, ValueError) as e:
            return {"ok": False, "motivo": str(e)}
    if caminho == "/api/email/login":
        redirect = str(d.get("redirect", ""))
        if not redirect.startswith("http://127.0.0.1:") or not redirect.endswith("/email/callback"):
            return {"ok": False, "motivo": "redirecionamento inválido"}
        try:
            return {"ok": True, "url": email_diario.url_login(redirect)}
        except email_diario.EmailErro as e:
            return {"ok": False, "motivo": str(e)}
    if caminho == "/api/email/desconectar":
        email_diario.desconectar()
        return {"ok": True}
    if caminho == "/api/guarda":
        try:
            guarda.ligar(bool(d.get("ligado")))
        except permissoes.PermissaoNegada as e:
            return {"ok": False, "motivo": str(e)}
        return {"ok": True, "guarda": {"ativa": guarda.ativa(), "resumo": guarda.resumo()}}
    if caminho == "/api/chat":
        return assistente.conversar(d.get("texto", ""))
    if caminho == "/api/chat/confirmar":
        return assistente.confirmar(d.get("id", ""), bool(d.get("sim")))
    if caminho == "/api/modo-jogo":
        return {"suspenso": assistente.definir_suspenso(bool(d.get("ligado")))}
    if caminho == "/api/transcrever":
        try:
            return {"texto": transcricao.transcrever(d.get("audio", ""))}
        except transcricao.TranscricaoErro as e:
            return {"texto": "", "erro": str(e)}
    if caminho == "/api/ollama/instalar":
        def tarefa(prog):
            import os, tempfile
            destino = os.path.join(tempfile.gettempdir(), "OllamaSetup.exe")
            dependencias.baixar_instalador_ollama(destino, lambda p, t: prog(p, t))
            os.startfile(destino)          # o instalador oficial abre; quem confirma e a propria pessoa
            prog(100, "Instalador do Ollama aberto: conclua a instalação e volte aqui.")
        _rodar("ollama_instalador", tarefa)
        return {}
    if caminho == "/api/log":
        _registrar(f"[tela] etapa={d.get('etapa')} {str(d.get('msg', ''))[:400]}")
        return {}
    if caminho == "/api/etapa":
        e = d.get("etapa")
        if e not in onboarding.ETAPAS:
            raise ValueError("etapa inválida")
        if e == "concluido" and onboarding.faltando(provedores.chaves_validas()):
            return {}                      # nunca grava 'concluido' com pendencia: na proxima abertura a pessoa volta para onde parou, e nao para a tela final sem saida
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
    if caminho == "/api/voz/config":
        campos = {}
        if "nome" in d:
            campos["voz_nome"] = d["nome"] if d["nome"] in {n for v in voz_nuvem.VOZES.values() for n, _ in v} else None
        if d.get("estilo") in voz_nuvem.ESTILOS:
            campos["voz_estilo"] = d["estilo"]
        if "reserva" in d:
            campos["voz_reserva"] = bool(d["reserva"])
        if "privada" in d:
            campos["voz_privada"] = bool(d["privada"])
        perfil.atualizar(**campos)
        return {}
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
    if caminho == "/api/whatsapp/abrir":
        whatsapp.abrir_login()
        return {}
    if caminho == "/api/whatsapp/estado":
        return {"estado": whatsapp.estado()}
    if caminho == "/api/telegram/token":
        try:
            return {"ok": True, "bot": remoto.cadastrar_token(d["token"])}
        except remoto.RemotoErro as e:
            return {"ok": False, "motivo": str(e)}
    if caminho == "/api/telegram/codigo":
        cod = remoto.novo_codigo(bool(d.get("reparear")))
        remoto.iniciar()
        return {"codigo": cod}
    if caminho == "/api/telegram/estado":
        remoto.iniciar()
        return remoto.resumo()
    if caminho == "/api/telegram/remover":
        remoto.parar()
        remoto.desligar_tudo()
        return {}
    if caminho == "/api/remoto/armar":
        try:
            remoto.armar(d.get("minutos") or None)
        except remoto.RemotoErro as e:
            return {"ok": False, "motivo": str(e)}
        return {"ok": True}
    if caminho == "/api/remoto/desarmar":
        remoto.desarmar()
        return {}
    if caminho == "/api/autostart":
        try:
            autostart.definir(bool(d.get("ativo")))
        except Exception as e:
            return {"ok": False, "motivo": str(e)}
        return {"ok": True}
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

    def _voz(self, d):
        """Voz natural (Gemini TTS pela chave da pessoa). Se nao der, 503: a tela usa a voz do sistema. Voz privada: nunca sai texto do PC."""
        p = perfil.carregar()
        if p.get("voz_privada"):
            return self._json({"erro": "voz privada: usando só a voz do sistema", "motivo": "privada"}, 409)
        try:
            wav = voz_nuvem.sintetizar(str(d.get("texto", "")), d.get("genero") or p.get("voz") or "feminina", d.get("voz") or p.get("voz_nome"),
                                       estilo=d.get("estilo") or p.get("voz_estilo") or "calmo")
        except voz_nuvem.VozErro as e:
            _registrar(f"[voz] {e}")
            return self._json({"erro": str(e), "motivo": e.motivo}, 503)
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(wav)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(wav)

    def do_GET(self):
        if not self._local():
            return self._json({"erro": "host negado"}, 403)
        if self.path == "/api/estado":
            try:
                return self._json(estado_geral())
            except Exception as e:
                _registrar(f"[erro] GET /api/estado: {e!r}")
                return self._json({"erro": "não consegui ler o estado: " + str(e)[:200]}, 500)
        caminho = self.path.split("?")[0]
        if caminho == "/email/callback":      # volta do login do Google (so leitura): guarda o token e leva de volta as configuracoes
            q = urllib.parse.parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
            try:
                if q.get("error"):
                    raise email_diario.EmailErro("Você cancelou o login no Google.")
                email_diario.concluir_login((q.get("code") or [""])[0], (q.get("state") or [""])[0])
                msg = "E-mail conectado! Pode fechar esta aba e voltar ao BRANIAC."
            except (email_diario.EmailErro, cofre.CofreErro) as e:
                msg = f"Não deu certo: {e}"
            corpo = f"<!doctype html><meta charset=utf-8><body style='font-family:sans-serif;background:#05070d;color:#e9eef9;padding:40px'><h2>{html.escape(msg)}</h2>".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)
            return
        if caminho in ("/", ""):
            nome = "app.html" if perfil.carregar().get("concluido") else "index.html"      # instalacao concluida: abre o assistente
        elif caminho in ("/instalacao", "/configuracoes"):
            nome = "index.html"
        else:
            nome = caminho.lstrip("/")
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
            if self.path == "/api/voz":
                return self._voz(d)
            return self._json(acao(self.path, d))
        except KeyError:
            return self._json({"erro": "rota desconhecida"}, 404)
        except Exception as e:
            _registrar(f"[erro] POST {self.path}: {e!r}")
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
    remoto.iniciar()
    print(f"BRANIAC instalação em http://127.0.0.1:{porta}", flush=True)
    while True:
        time.sleep(3600)
