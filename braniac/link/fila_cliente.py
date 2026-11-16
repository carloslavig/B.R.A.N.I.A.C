# -*- coding: utf-8 -*-
"""Cliente da FILA do BRANIAC LINK (SPEC.md secao 12): entrega arquivos e pega o resultado. Usa a MESMA identidade (Ed25519) ja confirmada no par:
`ident` e o objeto Identidade do seu assistente (o mesmo do No), nao crie outra. So biblioteca padrao.
Uso:  c = Cliente(ident, "https://xxxx.trycloudflare.com")
      jid = c.pedir({"titulo": "...", "cenas": [...]}); c.enviar(jid, "audio.mp3"); c.pronto(jid)
      while c.status(jid)["estado"] not in ("concluido", "erro"): time.sleep(20)
      c.baixar(jid, "saida.mp4")"""
import hashlib
import json
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .fila import assinar_pedido

VAZIO = hashlib.sha256(b"").hexdigest()


class ClienteErro(RuntimeError):
    pass


def _sha_arquivo(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for parte in iter(lambda: f.read(1 << 20), b""):
            h.update(parte)
    return h.hexdigest()


class Cliente:
    def __init__(self, ident, url, timeout=120):
        self.ident, self.url, self.timeout = ident, url.rstrip("/"), timeout

    def _pedido(self, metodo, caminho, corpo=None, arquivo=None):
        """corpo: bytes; arquivo: caminho de um arquivo enviado como corpo. Devolve a resposta HTTP aberta."""
        if arquivo:
            sha, dados, tam = _sha_arquivo(arquivo), open(arquivo, "rb"), Path(arquivo).stat().st_size
        else:
            corpo = corpo or b""
            sha, dados, tam = hashlib.sha256(corpo).hexdigest(), corpo, len(corpo)
        cab = assinar_pedido(self.ident, metodo, caminho, sha)
        cab["Content-Length"] = str(tam)
        cab["User-Agent"] = "braniac-link-cliente/1"
        req = urllib.request.Request(self.url + caminho, data=dados if tam else None, method=metodo, headers=cab)
        try:
            return urllib.request.urlopen(req, timeout=self.timeout)
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read().decode()).get("erro", "")
            except Exception:
                msg = ""
            raise ClienteErro(f"HTTP {e.code}: {msg}")
        except OSError as e:
            raise ClienteErro("sem conexao com a fila: " + repr(e)[:80])
        finally:
            if arquivo:
                dados.close()

    def _json(self, *a, **k):
        with self._pedido(*a, **k) as r:
            return json.loads(r.read().decode())

    def pedir(self, meta):
        return self._json("POST", "/pedido", corpo=json.dumps(meta, ensure_ascii=False).encode())["id"]

    def enviar(self, jid, caminho, nome=None):
        return self._json("PUT", f"/job/{jid}/arquivo/{nome or Path(caminho).name}", arquivo=caminho)["nome"]

    def pronto(self, jid):
        return self._json("POST", f"/job/{jid}/pronto")

    def status(self, jid):
        return self._json("GET", f"/job/{jid}")

    def municipios(self, cidade=""):
        """Sem cidade: resumo (pronto/producao/falta). Com cidade: a situacao dela."""
        return self._json("GET", "/municipios" + ("/" + urllib.parse.quote(cidade) if cidade else ""))

    def reservar(self, cidade, acao="reservar", nota=""):
        """acao: reservar | concluir | liberar. Devolve {ok, motivo?...}: ok False = ja pronta ou reservada pelo outro lado."""
        return self._json("POST", f"/municipios/{urllib.parse.quote(cidade)}/{acao}", json.dumps({"nota": nota}).encode())

    def avisos(self, desde=0):
        """Caixa de avisos do Braniac: {"avisos": [{seq, quando, texto}], "ultimo": N}. Guarde o maior seq e passe como desde na proxima vez."""
        return self._json("GET", f"/avisos?desde={int(desde)}")

    def mensagem(self, texto):
        """Fala com o Braniac pela fila (PEDIDO COMPLETO, FONTES APROVADO...), sem gastar o ntfy."""
        return self._json("POST", "/mensagem", json.dumps({"texto": texto}).encode())

    def painel(self):
        """Painel dos videos do Parceiro (so leitura): {"cidades", "pendencias", "historico", "esteira"}."""
        return self._json("GET", "/painel.json")

    def servir_painel(self, porta=8770):
        """Abre o painel no navegador deste computador: http://127.0.0.1:<porta>/ (so este computador alcanca). Bloqueia; Ctrl+C para."""
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        cli = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                try:
                    caminho = self.path.split("?")[0]
                    if caminho == "/api/parceiro":
                        dados, tipo = json.dumps(cli.painel(), ensure_ascii=False).encode(), "application/json; charset=utf-8"
                    elif caminho in ("/", "/parceiro"):
                        with cli._pedido("GET", "/painel") as r:
                            dados, tipo = r.read(), "text/html; charset=utf-8"
                    else:
                        return self.send_error(404)
                    self.send_response(200)
                except ClienteErro as e:
                    dados, tipo = json.dumps({"erro": str(e)}).encode(), "application/json"
                    self.send_response(502)
                self.send_header("Content-Type", tipo)
                self.send_header("Content-Length", str(len(dados)))
                self.end_headers()
                self.wfile.write(dados)

        ThreadingHTTPServer(("127.0.0.1", porta), H).serve_forever()

    # ---------- predio por predio (link/predio.py) ----------
    def servir_predio(self, porta=8773):
        """Abre o PREDIO do Braniac (o mesmo /sauraki do Dono, sem texto das conversas) em http://127.0.0.1:<porta>/. So GET; bloqueia."""
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        cli = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                try:
                    with cli._pedido("GET", "/predio" + self.path) as r:
                        dados, tipo = r.read(), r.headers.get("Content-Type", "application/octet-stream")
                    self.send_response(200)
                except ClienteErro as e:
                    dados, tipo = json.dumps({"erro": str(e)}).encode(), "application/json"
                    self.send_response(404 if "HTTP 404" in str(e) else 502)
                self.send_header("Content-Type", tipo)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(dados)))
                self.end_headers()
                self.wfile.write(dados)

        ThreadingHTTPServer(("127.0.0.1", porta), H).serve_forever()

    def enviar_predio(self, pasta, ja=None):
        """Sobe o predio DESTE lado (pasta com index.html + dados) para o Braniac. Manda so o que mudou desde a ultima vez
        (`ja` = {caminho: mtime}, guardado entre chamadas). Devolve a lista do que foi enviado."""
        pasta, ja, foi = Path(pasta), ja if ja is not None else {}, []
        for f in sorted(pasta.rglob("*")):
            if not f.is_file() or f.name.startswith("."):
                continue
            rel = f.relative_to(pasta).as_posix()
            if ja.get(rel) == f.stat().st_mtime:
                continue
            self._json("PUT", "/predio-par/" + "/".join(urllib.parse.quote(p) for p in rel.split("/")), arquivo=f)
            ja[rel] = f.stat().st_mtime
            foi.append(rel)
        return foi

    def olhando_predio(self):
        """True quando o Dono esta com o predio deste lado aberto (so entao vale mandar dados novos)."""
        return bool(self._json("GET", "/predio-par/olhando").get("olhando"))

    def espelhar_predio(self, pasta, intervalo=20):
        """Laco: sobe a pasta uma vez e depois so o que mudar, a cada `intervalo` s enquanto o Dono olha (senao, 1x por minuto). Bloqueia."""
        ja = {}
        self.enviar_predio(pasta, ja)
        while True:
            try:
                if self.olhando_predio():
                    self.enviar_predio(pasta, ja)
                    time.sleep(intervalo)
                    continue
            except ClienteErro:
                pass
            time.sleep(60)

    def baixar(self, jid, destino):
        destino = Path(destino)
        with self._pedido("GET", f"/job/{jid}/resultado") as r, destino.open("wb") as f:
            shutil.copyfileobj(r, f)
        return destino

    def enviar_tudo(self, meta, arquivos, espera=1800, intervalo=20, destino=None):
        """Faz o ciclo inteiro: pedido, arquivos, 'pronto', espera e baixa o resultado. Devolve o caminho do mp4."""
        jid = self.pedir(meta)
        for a in arquivos:
            self.enviar(jid, a)
        self.pronto(jid)
        fim = time.time() + espera
        while time.time() < fim:
            st = self.status(jid)
            if st["estado"] == "erro":
                raise ClienteErro("a fila recusou ou falhou: " + str(st.get("detalhe")))
            if st["estado"] == "concluido":
                return self.baixar(jid, destino or f"{jid}.mp4")
            time.sleep(intervalo)
        raise ClienteErro("tempo esgotado esperando o render")
