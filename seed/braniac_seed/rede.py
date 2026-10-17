# -*- coding: utf-8 -*-
"""REDE DE BRANIACS: assistentes de pessoas diferentes conversam entre si pela VPN (Radmin), SO com a permissao de cada dono.

Modelo (decisao do Carlos, 17/10/2026: 'o usuario diz: eu permito que o Braniac X converse com o meu'; o conselho de IAs recomendou multi-agente com controle
de acesso granular, nao treinar uma rede neural):
- PAREAR: um dono gera um CONVITE (codigo de uso unico, 30 min) e o outro cola no seu Braniac. Os dois passam a dividir um segredo (so entre os dois).
- PERMITIR: depois de pareado, ninguem fala com ninguem ate o DONO de cada lado dizer 'permitir <nome>'. Revogar e imediato. A permissao e por Braniac.
- CONVERSAR: mensagens de TEXTO assinadas (HMAC-SHA256 + data/hora + nonce: sem falsificar nem repetir). O Braniac que recebe responde com a IA dele
  SEM ferramentas e SEM dados da pessoa; mensagem recebida e so texto de outra IA, nunca ordem (nao executa nada, nao abre arquivo).
- REDE: o servico escuta SO no IP da Radmin (26.x.x.x) ou em BRANIAC_REDE_IP; sem Radmin, nao abre porta nenhuma. Limite de 20 mensagens por minuto por Braniac.
Este modulo so usa a biblioteca padrao; recebe do Braniac hospedeiro o nome do assistente, a funcao que responde e a versao."""
import base64, hashlib, hmac, json, os, re, secrets, socket, subprocess, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORTA_PADRAO = 8791
VALIDADE_CONVITE_S = 30 * 60
JANELA_S = 120
LIMITE_POR_MIN = 20
MAX_TEXTO = 2000


class RedeErro(RuntimeError):
    pass


def ip_radmin():
    """IP desta maquina na Radmin VPN (26.x.x.x), ou o forcado por BRANIAC_REDE_IP, ou None."""
    forcado = os.environ.get("BRANIAC_REDE_IP", "").strip()
    if forcado:
        return forcado
    achados = set()
    try:
        achados |= {i[4][0] for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
    except OSError:
        pass
    try:
        saida = subprocess.run(["ipconfig"], capture_output=True, text=True, encoding="cp850", errors="replace", timeout=10, creationflags=0x08000000).stdout
        achados |= set(re.findall(r"\b(26\.\d{1,3}\.\d{1,3}\.\d{1,3})\b", saida))
    except (OSError, subprocess.SubprocessError):
        pass
    return next((ip for ip in sorted(achados) if ip.startswith("26.")), None)


def _mac(segredo, *partes):
    return hmac.new(bytes.fromhex(segredo), "|".join(str(p) for p in partes).encode("utf-8"), hashlib.sha256).hexdigest()


class Rede:
    def __init__(self, pasta, nome, responder, versao="", porta=PORTA_PADRAO):
        """nome: funcao() -> nome do meu assistente. responder: funcao(nome_do_par, texto) -> resposta (texto)."""
        self.arq = Path(pasta) / "rede.json"
        self.nome, self.responder, self.versao, self.porta = nome, responder, versao, porta
        self._lock = threading.RLock()
        self._vistos, self._recentes = {}, {}
        self.servidor = None
        self.ip = None

    # ---------- estado ----------
    def _ler(self):
        try:
            d = json.loads(self.arq.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            d = {}
        novo = "id" not in d
        d.setdefault("id", secrets.token_hex(4))
        d.setdefault("pares", {})
        d.setdefault("convites", {})
        d.setdefault("log", [])
        if novo:
            self._gravar(d)         # o id tem de ser sempre o mesmo, desde a primeira leitura
        return d

    def _gravar(self, d):
        d["log"] = d["log"][-30:]
        self.arq.parent.mkdir(parents=True, exist_ok=True)
        self.arq.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")

    def _par_por_nome(self, d, nome):
        alvo = re.sub(r"\W+", "", str(nome).lower())
        for pid, p in d["pares"].items():
            n = re.sub(r"\W+", "", p["nome"].lower())
            if alvo and (alvo == n or alvo in n):
                return pid, p
        raise RedeErro(f"Não conheço nenhum Braniac chamado '{nome}'. Veja a lista com 'rede listar'.")

    def _registrar(self, d, texto):
        d["log"].append(f"{time.strftime('%d/%m %H:%M')} {texto}")

    # ---------- convite e pareamento ----------
    def convidar(self):
        meu_ip = self.ip or ip_radmin()
        if not meu_ip:
            raise RedeErro("Não achei o seu IP da Radmin VPN (26.x.x.x). Abra a Radmin, entre na rede do BRANIAC e tente de novo.")
        with self._lock:
            d = self._ler()
            cid, segredo = secrets.token_hex(4), secrets.token_hex(16)
            agora = time.time()
            d["convites"] = {k: v for k, v in d["convites"].items() if v["ate"] > agora}
            d["convites"][cid] = {"segredo": segredo, "ate": agora + VALIDADE_CONVITE_S}
            self._gravar(d)
            carga = {"id": d["id"], "nome": self.nome(), "ip": meu_ip, "porta": self.porta, "cid": cid, "segredo": segredo, "ate": int(agora + VALIDADE_CONVITE_S)}
        return "BRN1." + base64.urlsafe_b64encode(json.dumps(carga).encode()).decode()

    def aceitar(self, codigo):
        try:
            c = json.loads(base64.urlsafe_b64decode(str(codigo).strip().split(".", 1)[1].encode()))
            c["segredo"], c["ip"], c["porta"], c["cid"], c["id"], c["nome"]
        except Exception:
            raise RedeErro("Esse convite não é válido.")
        if c["ate"] < time.time():
            raise RedeErro("Esse convite expirou (vale 30 minutos). Peça outro.")
        with self._lock:
            d = self._ler()
            meu_ip = self.ip or ip_radmin() or ""
            ts = int(time.time())
            corpo = {"cid": c["cid"], "id": d["id"], "nome": self.nome(), "ip": meu_ip, "porta": self.porta, "ts": ts}
            corpo["mac"] = _mac(c["segredo"], c["cid"], corpo["id"], corpo["nome"], meu_ip, self.porta, ts)
        r = self._post(c["ip"], c["porta"], "/rede/parear", corpo, timeout=15)
        with self._lock:
            d = self._ler()
            d["pares"][c["id"]] = {"nome": r.get("nome") or c["nome"], "ip": c["ip"], "porta": c["porta"], "segredo": c["segredo"], "recebe": False, "desde": time.strftime("%Y-%m-%d")}
            self._registrar(d, f"pareado com {c['nome']}")
            self._gravar(d)
        return c["nome"]

    # ---------- permissoes ----------
    def permitir(self, nome, sim=True):
        with self._lock:
            d = self._ler()
            pid, p = self._par_por_nome(d, nome)
            p["recebe"] = bool(sim)
            self._registrar(d, f"{'permitiu' if sim else 'bloqueou'} {p['nome']}")
            self._gravar(d)
        return p["nome"]

    def remover(self, nome):
        with self._lock:
            d = self._ler()
            pid, p = self._par_por_nome(d, nome)
            del d["pares"][pid]
            self._registrar(d, f"removeu {p['nome']}")
            self._gravar(d)
        return p["nome"]

    def listar(self):
        d = self._ler()
        return [{"nome": p["nome"], "ip": p["ip"], "pode_falar_comigo": p["recebe"]} for p in d["pares"].values()], d["log"][-8:]

    # ---------- enviar ----------
    def _post(self, ip, porta, caminho, corpo, timeout=90):
        req = urllib.request.Request(f"http://{ip}:{porta}{caminho}", data=json.dumps(corpo).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read().decode("utf-8")).get("erro")
            except Exception:
                msg = None
            raise RedeErro(msg or f"O outro Braniac recusou ({e.code}).")
        except (OSError, ValueError):
            raise RedeErro(f"Não consegui falar com {ip}:{porta}. A Radmin está ligada nos dois lados e o Braniac de lá está aberto?")

    def falar(self, nome, texto):
        texto = str(texto or "").strip()[:MAX_TEXTO]
        if not texto:
            raise RedeErro("Faltou o texto da mensagem.")
        d = self._ler()
        pid, p = self._par_por_nome(d, nome)
        ts, nonce = int(time.time()), secrets.token_hex(8)
        r = self._post(p["ip"], p["porta"], "/rede/mensagem", {"de": d["id"], "ts": ts, "nonce": nonce, "texto": texto, "mac": _mac(p["segredo"], d["id"], ts, nonce, texto)})
        if r.get("de") != pid or abs(time.time() - int(r.get("ts", 0))) > JANELA_S or not hmac.compare_digest(
                str(r.get("mac", "")), _mac(p["segredo"], r.get("de"), r.get("ts"), r.get("nonce"), r.get("texto"))):
            raise RedeErro("A resposta não passou na verificação de segurança; ignorei.")
        with self._lock:
            d = self._ler()
            self._registrar(d, f"conversou com {p['nome']}")
            self._gravar(d)
        return str(r["texto"])[:MAX_TEXTO]

    # ---------- receber ----------
    def _tratar_parear(self, c):
        with self._lock:
            d = self._ler()
            conv = d["convites"].get(str(c.get("cid")))
            if not conv or conv["ate"] < time.time():
                raise RedeErro("convite inválido ou expirado")
            ts = int(c.get("ts", 0))
            esperado = _mac(conv["segredo"], c["cid"], c["id"], c["nome"], c["ip"], c["porta"], ts)
            if abs(time.time() - ts) > JANELA_S or not hmac.compare_digest(str(c.get("mac", "")), esperado):
                raise RedeErro("assinatura inválida")
            del d["convites"][c["cid"]]            # uso unico
            d["pares"][str(c["id"])[:16]] = {"nome": str(c["nome"])[:40], "ip": c["ip"], "porta": int(c["porta"]), "segredo": conv["segredo"], "recebe": False, "desde": time.strftime("%Y-%m-%d")}
            self._registrar(d, f"{c['nome']} aceitou o seu convite (ainda NÃO pode falar com você: diga 'permitir {c['nome']}')")
            self._gravar(d)
            return {"ok": True, "id": d["id"], "nome": self.nome()}

    def _tratar_mensagem(self, c):
        with self._lock:
            d = self._ler()
            p = d["pares"].get(str(c.get("de")))
            if not p:
                raise RedeErro("Braniac desconhecido")
            ts, nonce, texto = int(c.get("ts", 0)), str(c.get("nonce", "")), str(c.get("texto", ""))
            if abs(time.time() - ts) > JANELA_S or not hmac.compare_digest(str(c.get("mac", "")), _mac(p["segredo"], c["de"], ts, nonce, texto)):
                raise RedeErro("assinatura inválida")
            if nonce in self._vistos:
                raise RedeErro("mensagem repetida")
            agora = time.time()
            self._vistos = {k: t for k, t in self._vistos.items() if agora - t < 2 * JANELA_S}
            self._vistos[nonce] = agora
            if not p["recebe"]:
                raise RedeErro("O dono deste Braniac ainda não permitiu a conversa com você.")
            rec = [t for t in self._recentes.get(c["de"], []) if agora - t < 60]
            if len(rec) >= LIMITE_POR_MIN:
                raise RedeErro("muitas mensagens por minuto")
            self._recentes[c["de"]] = rec + [agora]
            nome_par = p["nome"]
            segredo = p["segredo"]
            self._registrar(d, f"{nome_par} falou com você")
            self._gravar(d)
        resposta = str(self.responder(nome_par, texto[:MAX_TEXTO]) or "")[:MAX_TEXTO]
        ts2, nonce2 = int(time.time()), secrets.token_hex(8)
        return {"de": d["id"], "ts": ts2, "nonce": nonce2, "texto": resposta, "mac": _mac(segredo, d["id"], ts2, nonce2, resposta)}

    # ---------- servico ----------
    def iniciar(self, ip=None):
        """Abre a porta SO no IP da Radmin (ou o informado). Devolve o IP, ou None se nao ha Radmin (nada e aberto)."""
        ip = ip or ip_radmin()
        if not ip:
            return None
        rede = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _resp(self, codigo, obj):
                b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
                self.send_response(codigo)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def do_GET(self):
                if self.path == "/rede/quem":
                    return self._resp(200, {"id": rede._ler()["id"], "nome": rede.nome(), "versao": rede.versao})
                self._resp(404, {"erro": "não encontrado"})

            def do_POST(self):
                try:
                    n = int(self.headers.get("Content-Length", 0))
                    if not 0 < n <= 16384:
                        return self._resp(413, {"erro": "tamanho inválido"})
                    corpo = json.loads(self.rfile.read(n))
                    if self.path == "/rede/parear":
                        return self._resp(200, rede._tratar_parear(corpo))
                    if self.path == "/rede/mensagem":
                        return self._resp(200, rede._tratar_mensagem(corpo))
                    self._resp(404, {"erro": "não encontrado"})
                except RedeErro as e:
                    self._resp(403, {"erro": str(e)})
                except (ValueError, KeyError, TypeError):
                    self._resp(400, {"erro": "pedido inválido"})
                except Exception:
                    self._resp(500, {"erro": "erro interno"})

        self.servidor = ThreadingHTTPServer((ip, self.porta), H)
        self.servidor.daemon_threads = True
        self.ip = ip
        threading.Thread(target=self.servidor.serve_forever, daemon=True, name="rede-braniac").start()
        return ip

    def parar(self):
        if self.servidor:
            self.servidor.shutdown()
            self.servidor.server_close()
            self.servidor = None
