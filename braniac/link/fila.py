# -*- coding: utf-8 -*-
"""FILA de pedidos do BRANIAC LINK (SPEC.md secao 12): servidor HTTP pequeno por onde um par confirmado entrega arquivos (audio, roteiro) e pega o resultado (mp4).
So o par sai para a internet (HTTPS por tunel), entao funciona mesmo atras de NAT simetrico. Sem senha: cada pedido e ASSINADO com a chave Ed25519 do dispositivo
e so passa se o par for confiavel e tiver a permissao 'tarefa' para o agente da fila. O servidor escuta so em 127.0.0.1 (o tunel faz a ponte).
Nada vindo de fora e executado: o `processador` do hospedeiro recebe SO dados (meta.json + arquivos de tipos permitidos) e devolve o arquivo pronto."""
import hashlib
import json
import re
import secrets
import shutil
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import arquivos
from .identidade import verificar

TOLERANCIA_S = 300
EXT_OK = {".json", ".txt", ".md", ".mp3", ".wav", ".m4a", ".ogg", ".aac", ".flac", ".png", ".jpg", ".jpeg", ".webp",
          ".zip"}   # 13/11: video-NNN.zip do pacote do Parceiro; o conteudo e filtrado em render_parceiro (so cena e dados sao extraidos)
EXT_PRODUCAO = EXT_OK | {".pdf", ".mp4"}   # so no tipo producao_completa (pacote de pesquisa + modelo de video)
ESTADOS = ("criado", "pronto", "processando", "concluido", "erro", "producao")


class FilaErro(ValueError):
    pass


def assinar_pedido(ident, metodo, caminho, corpo_sha, agora=None):
    """Cabecalhos de um pedido assinado (usado pelo cliente)."""
    ts, nonce = str(int(agora or time.time())), secrets.token_hex(8)
    texto = "\n".join([metodo, caminho, ts, corpo_sha, ident.id, nonce]).encode()
    return {"X-Link-Id": ident.id, "X-Link-Ts": ts, "X-Link-Sha": corpo_sha, "X-Link-Nonce": nonce, "X-Link-Sig": ident.assinar(texto)}


class Fila:
    def __init__(self, pares, pasta, processador, agente="render", max_dia=5, max_bytes=300 * 1024 ** 2, avisar=None, ao_producao=None):
        """processador(pasta_do_job: Path, meta: dict) -> Path do arquivo pronto (ou levanta). avisar(par_id, job_id, estado, detalhe) e opcional."""
        self.pares, self.pasta, self.processador, self.agente = pares, Path(pasta), processador, agente
        self.max_dia, self.max_bytes, self.avisar = max_dia, max_bytes, avisar or (lambda *a: None)
        self.ao_producao = ao_producao          # ao_producao(par, job, meta, pasta): pedido producao_completa vai para a fila de producao (nao para o render)
        (self.pasta / "jobs").mkdir(parents=True, exist_ok=True)
        self._usados, self._lock, self._acordar, self._srv, self._parar = {}, threading.Lock(), threading.Event(), None, threading.Event()

    # ---------- autenticacao ----------
    def autenticar(self, metodo, caminho, h, agora=None):
        """h: cabecalhos. Devolve o id do par ou levanta FilaErro."""
        pid, ts, sha, sig, nonce = (h.get(k, "") for k in ("X-Link-Id", "X-Link-Ts", "X-Link-Sha", "X-Link-Sig", "X-Link-Nonce"))
        par = self.pares.get(pid)
        if not par or par["estado"] != "confiavel" or self.pares.decidir(pid, "tarefa", self.agente) != "aceitar":
            raise FilaErro("par sem permissao")
        agora = agora or time.time()
        if not ts.isdigit() or abs(agora - int(ts)) > TOLERANCIA_S:
            raise FilaErro("data fora da tolerancia")
        texto = "\n".join([metodo, caminho, ts, sha, pid, nonce]).encode()
        if not verificar(par["pub"], texto, sig):
            raise FilaErro("assinatura invalida")
        with self._lock:
            self._usados = {k: t for k, t in self._usados.items() if agora - t < 2 * TOLERANCIA_S}
            if sig in self._usados:
                raise FilaErro("pedido repetido")
            self._usados[sig] = agora
        return pid

    # ---------- jobs ----------
    def _dir(self, jid):
        if not re.fullmatch(r"[0-9a-f]{12}", jid):
            raise FilaErro("id de job invalido")
        return self.pasta / "jobs" / jid

    def _estado(self, jid):
        try:
            return json.loads((self._dir(jid) / "estado.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise FilaErro("job nao encontrado")

    def _gravar_estado(self, jid, **campos):
        with self._lock:
            try:
                e = json.loads((self._dir(jid) / "estado.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                e = {}
            e.update(campos, atualizado=int(time.time()))
            (self._dir(jid) / "estado.json").write_text(json.dumps(e, ensure_ascii=False), encoding="utf-8")
            return e

    def _do_dono(self, jid, pid):
        e = self._estado(jid)
        if e.get("par") != pid:
            raise FilaErro("job de outro par")
        return e

    def criar(self, pid, meta):
        hoje = time.strftime("%Y-%m-%d")
        n = sum(1 for d in (self.pasta / "jobs").iterdir() if (d / "estado.json").exists()
                and json.loads((d / "estado.json").read_text(encoding="utf-8")).get("par") == pid
                and json.loads((d / "estado.json").read_text(encoding="utf-8")).get("dia") == hoje)
        if n >= self.max_dia:
            raise FilaErro(f"limite de {self.max_dia} pedidos por dia")
        if not isinstance(meta, dict):
            raise FilaErro("meta invalida")
        if meta.get("tipo") == "producao_completa" and not (str(meta.get("numero") or "").strip() and str(meta.get("cidade") or "").strip()):
            raise FilaErro("producao_completa precisa de numero e cidade")
        jid = secrets.token_hex(6)
        self._dir(jid).mkdir(parents=True)
        (self._dir(jid) / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        self._gravar_estado(jid, par=pid, estado="criado", dia=hoje, criado=int(time.time()), bytes=0)
        return jid

    def receber_arquivo(self, jid, pid, nome, caminho_tmp):
        e = self._do_dono(jid, pid)
        if e["estado"] != "criado":
            raise FilaErro("job nao aceita mais arquivos")
        seguro = arquivos.nome_seguro(nome)
        producao = self._meta(jid).get("tipo") == "producao_completa"
        if Path(seguro).suffix.lower() not in (EXT_PRODUCAO if producao else EXT_OK):
            raise FilaErro("tipo de arquivo nao permitido")
        tam = Path(caminho_tmp).stat().st_size
        if e["bytes"] + tam > self.max_bytes:
            raise FilaErro("job grande demais")
        if producao and seguro.lower().endswith(".zip"):
            from .producao import conferir_zip
            try:
                conferir_zip(caminho_tmp)
            except ValueError as ex:
                raise FilaErro(str(ex))
        shutil.move(str(caminho_tmp), str(self._dir(jid) / seguro))
        self._gravar_estado(jid, bytes=e["bytes"] + tam)
        return seguro

    def _meta(self, jid):
        try:
            return json.loads((self._dir(jid) / "meta.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def pronto(self, jid, pid):
        self._do_dono(jid, pid)
        meta = self._meta(jid)
        if meta.get("tipo") == "producao_completa":
            if not self.ao_producao:
                raise FilaErro("fila de producao desligada")
            self._gravar_estado(jid, estado="producao")
            return self.ao_producao(pid, jid, meta, self._dir(jid))
        self._gravar_estado(jid, estado="pronto")
        self._acordar.set()

    def concluir_externo(self, jid, arquivo):
        """Pedido de producao entregue: o mp4 vira o resultado do job (GET /job/<id>/resultado)."""
        shutil.copy2(arquivo, self._dir(jid) / "resultado.mp4")
        self._gravar_estado(jid, estado="concluido", detalhe="", resultado_bytes=(self._dir(jid) / "resultado.mp4").stat().st_size)

    def status(self, jid, pid):
        e = self._do_dono(jid, pid)
        return {k: e.get(k) for k in ("estado", "detalhe", "criado", "atualizado", "bytes", "resultado_bytes")}

    def resultado(self, jid, pid):
        e = self._do_dono(jid, pid)
        arq = self._dir(jid) / "resultado.mp4"
        if e["estado"] != "concluido" or not arq.exists():
            raise FilaErro("resultado ainda nao existe")
        return arq

    # ---------- trabalhador ----------
    def _proximo(self):
        achados = []
        for d in (self.pasta / "jobs").iterdir():
            try:
                e = json.loads((d / "estado.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if e.get("estado") == "pronto":
                achados.append((e.get("criado", 0), d.name, e))
        return min(achados)[1:] if achados else None

    def processar_um(self):
        """Processa o job pronto mais antigo (se houver). Devolve o id ou None."""
        p = self._proximo()
        if not p:
            return None
        jid, e = p
        self._gravar_estado(jid, estado="processando", detalhe="")
        self.avisar(e["par"], jid, "processando", "")
        try:
            meta = json.loads((self._dir(jid) / "meta.json").read_text(encoding="utf-8"))
            saida = Path(self.processador(self._dir(jid), meta))
            shutil.copy2(saida, self._dir(jid) / "resultado.mp4")
            self._gravar_estado(jid, estado="concluido", detalhe="", resultado_bytes=(self._dir(jid) / "resultado.mp4").stat().st_size)
            self.avisar(e["par"], jid, "concluido", "")
        except Exception as ex:
            self._gravar_estado(jid, estado="erro", detalhe=str(ex)[:300])
            self.avisar(e["par"], jid, "erro", str(ex)[:300])
        return jid

    def _trabalhar(self):
        while not self._parar.is_set():
            if self.processar_um() is None:
                self._acordar.wait(30)
                self._acordar.clear()

    # ---------- HTTP ----------
    def servir(self, porta=8767):
        fila = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, codigo, obj):
                dados = json.dumps(obj, ensure_ascii=False).encode()
                self.send_response(codigo)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(dados)))
                self.end_headers()
                self.wfile.write(dados)

            def _tratar(self, metodo):
                try:
                    tam = int(self.headers.get("Content-Length") or 0)
                    if tam > fila.max_bytes:
                        return self._json(413, {"erro": "corpo grande demais"})
                    h = {k: self.headers.get(k, "") for k in ("X-Link-Id", "X-Link-Ts", "X-Link-Sha", "X-Link-Sig", "X-Link-Nonce")}
                    pid = fila.autenticar(metodo, self.path, h)            # assinatura confere ANTES de ler o corpo
                    corpo_tmp = fila.pasta / f"_rec-{secrets.token_hex(4)}"
                    try:
                        sha, restante = hashlib.sha256(), tam
                        with corpo_tmp.open("wb") as f:
                            while restante > 0:
                                parte = self.rfile.read(min(1 << 20, restante))
                                if not parte:
                                    break
                                sha.update(parte)
                                f.write(parte)
                                restante -= len(parte)
                        if restante or sha.hexdigest() != h["X-Link-Sha"]:
                            return self._json(400, {"erro": "corpo nao confere com o hash assinado"})
                        return self._rotear(metodo, pid, corpo_tmp)
                    finally:
                        corpo_tmp.unlink(missing_ok=True)
                except FilaErro as e:
                    return self._json(403 if "permissao" in str(e) or "assinatura" in str(e) or "repetido" in str(e) or "data" in str(e) else 400, {"erro": str(e)})
                except Exception as e:
                    return self._json(500, {"erro": repr(e)[:120]})

            def _rotear(self, metodo, pid, corpo_tmp):
                partes = [p for p in self.path.split("?")[0].split("/") if p]
                if metodo == "GET" and partes and partes[0] == "municipios" and len(partes) <= 2:   # o Aliado pergunta o que ja foi feito
                    from urllib.parse import unquote
                    from . import municipios
                    return self._json(200, municipios.cidade(unquote(partes[1])) if len(partes) == 2 else municipios.resumo())
                if metodo == "POST" and len(partes) == 3 and partes[0] == "municipios" and partes[2] in ("reservar", "concluir", "aprovar", "reprovar", "postar", "liberar"):
                    from urllib.parse import unquote
                    from . import municipios      # shortcut: o unico par com permissao 'tarefa' e o Aliado; com mais pares, usar o nome do par
                    nota = str((json.loads(corpo_tmp.read_text(encoding="utf-8") or "{}") if corpo_tmp and corpo_tmp.exists() else {}).get("nota", ""))
                    return self._json(200, getattr(municipios, partes[2])(unquote(partes[1]), "aliado", nota))
                if partes and partes[0] in ("predio", "predio-par"):   # predio por predio com o par (link/predio.py): ida e volta
                    from . import predio
                    return predio.rota(self, metodo, pid, partes, corpo_tmp, fila.pares)
                if metodo == "GET" and partes and partes[0] in ("painel", "painel.json") and fila.pares.decidir(pid, "tarefa", "painel") != "aceitar":
                    return self._json(403, {"erro": "o dono deste Braniac nao liberou o painel"})   # como o 'painel sim' da loja: so ve quem o Dono liberou
                if metodo == "GET" and partes == ["painel.json"]:   # painel dos videos do Parceiro, SO leitura e so o resumo (lote_parceiro.publico)
                    from . import lote_parceiro
                    return self._json(200, lote_parceiro.publico())
                if metodo == "GET" and partes == ["painel"]:        # a mesma tela do /parceiro; o mini-servidor do Mac responde o /api/parceiro com o /painel.json
                    pagina = (Path(__file__).parent.parent / "ui" / "parceiro.html").read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(pagina)))
                    self.end_headers()
                    return self.wfile.write(pagina)
                if metodo == "GET" and partes == ["avisos"]:      # caixa de avisos do Braniac para o par (nao depende do ntfy)
                    from urllib.parse import parse_qs, urlparse
                    from . import avisos
                    desde = (parse_qs(urlparse(self.path).query).get("desde") or ["0"])[0]
                    return self._json(200, avisos.ler(pid, int(desde) if desde.isdigit() else 0))
                if metodo == "POST" and partes == ["mensagem"]:   # o par fala com o Braniac pela fila (mesmo efeito de uma mensagem do Link)
                    from . import integracao
                    texto = str((json.loads(corpo_tmp.read_text(encoding="utf-8") or "{}") if corpo_tmp and corpo_tmp.exists() else {}).get("texto") or "")
                    if not texto.strip():
                        return self._json(400, {"erro": "texto vazio"})
                    integracao._ao_msg(pid, texto[:200_000])
                    return self._json(200, {"ok": True})
                if metodo == "POST" and partes == ["pedido"]:
                    return self._json(200, {"id": fila.criar(pid, json.loads(corpo_tmp.read_text(encoding="utf-8")))})
                if len(partes) >= 2 and partes[0] == "job":
                    jid = partes[1]
                    if metodo == "PUT" and len(partes) == 4 and partes[2] == "arquivo":
                        return self._json(200, {"nome": fila.receber_arquivo(jid, pid, partes[3], corpo_tmp)})
                    if metodo == "POST" and len(partes) == 3 and partes[2] == "pronto":
                        pos = fila.pronto(jid, pid)
                        return self._json(200, {"ok": True, **({"posicao": pos} if pos else {})})
                    if metodo == "GET" and len(partes) == 2:
                        return self._json(200, fila.status(jid, pid))
                    if metodo == "GET" and len(partes) == 3 and partes[2] == "resultado":
                        arq = fila.resultado(jid, pid)
                        self.send_response(200)
                        self.send_header("Content-Type", "video/mp4")
                        self.send_header("Content-Length", str(arq.stat().st_size))
                        self.end_headers()
                        with arq.open("rb") as f:
                            shutil.copyfileobj(f, self.wfile)
                        return
                return self._json(404, {"erro": "rota desconhecida"})

            def do_GET(self):
                self._tratar("GET")

            def do_POST(self):
                self._tratar("POST")

            def do_PUT(self):
                self._tratar("PUT")

        for d in (self.pasta / "jobs").iterdir():           # reinicio do Braniac no meio de um render: o job volta para a fila
            try:
                if self._estado(d.name).get("estado") == "processando":
                    self._gravar_estado(d.name, estado="pronto")
            except FilaErro:
                pass
        self._srv = ThreadingHTTPServer(("127.0.0.1", porta), H)
        threading.Thread(target=self._srv.serve_forever, daemon=True, name="braniac-link-fila").start()
        threading.Thread(target=self._trabalhar, daemon=True, name="braniac-link-fila-worker").start()
        return self._srv.server_address[1]

    def parar(self):
        self._parar.set()
        self._acordar.set()
        if self._srv:
            self._srv.shutdown()
