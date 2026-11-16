# -*- coding: utf-8 -*-
"""PAR WEBRTC (29/10/2026): dois Braniacs conversam a distancia, DIRETO (WebRTC), sem VPN, sem IP fixo e sem humano no meio -- o mesmo jeito do celular (remoto.py).
Arquivo unico, independente do resto do Braniac: precisa so de aiortc + cryptography. O Braniac Loja usa esta MESMA copia.
Pareamento: um lado chama novo_codigo() e passa o codigo ao outro (que chama parear(codigo, nome_do_outro)). So quem tem o codigo fala com este Braniac:
o 'ola' (SDP) vai cifrado (AES-GCM, chave derivada do codigo) por um canal publico (ntfy.sh); depois o canal de dados WebRTC (DTLS) leva o texto.
Cada lado ouve um topico proprio (codigo + nome de quem recebe), entao os dois podem puxar assunto. O DONO decide: ninguem recebe nada ate permitir(True).
Mensagem recebida e SO TEXTO de outra IA: o `responder(de, texto)` do hospedeiro deve responder sem ferramentas e sem dados pessoais; aqui nada e executado.
v2 (30/10/2026): alem de texto, o canal leva 'ping' (o predio do outro Braniac aparece no Sauraki enquanto ele responde) e 'painel' (GET somente leitura do painel local do outro lado, so se o dono liberou com permitir_painel).
Limites: sem servidor TURN, redes de operadora muito fechadas podem nao conectar; 20 mensagens/min; 2000 caracteres por mensagem."""
import asyncio
import base64
import hashlib
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SINAL = "https://ntfy.sh"
STUN = "stun:stun.l.google.com:19302"
ALFA = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
MAX_TEXTO, LIMITE_MIN, JANELA_S = 2000, 20, 120
PARTE, MAX_PAINEL, LIMITE_PAINEL = 30000, 3_000_000, 240   # pedaco (base64) por mensagem, corpo maximo do painel, GETs por minuto


class ParErro(RuntimeError):
    pass


def _norm(c):
    return str(c).replace("-", "").replace(" ", "").upper()


def _chave(cod):
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=b"braniac-par-v1", info=b"aes").derive(_norm(cod).encode())


def _topico(cod, quem_recebe):
    return "braniac-par-" + hashlib.sha256(f"{_norm(cod)}|para|{quem_recebe.strip().lower()}".encode()).hexdigest()[:32]


def _cifrar(chave, obj):
    iv = os.urandom(12)
    return base64.b64encode(iv + AESGCM(chave).encrypt(iv, json.dumps(obj).encode(), None)).decode()


def _decifrar(chave, txt):
    b = base64.b64decode(txt)
    return json.loads(AESGCM(chave).decrypt(b[:12], b[12:], None))


def _publicar(topico, texto):
    urllib.request.urlopen(urllib.request.Request(f"{SINAL}/{topico}", data=texto.encode(), method="POST"), timeout=20).read()


class Par:
    """nome = como este Braniac se chama; responder(de, texto) -> str responde as mensagens recebidas."""

    def __init__(self, pasta, nome, responder, painel_base=""):
        """painel_base = URL do painel LOCAL que o par autorizado pode ver (ex.: http://127.0.0.1:8770); vazio = nao oferece painel."""
        self.arq = Path(pasta) / "par.json"
        self.nome, self.responder, self.painel_base = nome, responder, painel_base.rstrip("/")
        self._cli, self._pend, self._tp = None, {}, []
        self.estado = {"ouvindo": False, "conectado": False, "erro": "", "ultimo": ""}
        self._stop, self._lock, self._loop, self._pcs, self._tempos = threading.Event(), threading.Lock(), None, [], []

    # ---------- dados ----------
    def _ler(self):
        try:
            return json.loads(self.arq.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _gravar(self, d):
        self.arq.parent.mkdir(parents=True, exist_ok=True)
        self.arq.write_text(json.dumps(d), encoding="utf-8")

    def novo_codigo(self, nome_do_par):
        """Gera o codigo (16 letras/numeros) para entregar ao outro Braniac. O outro lado ainda comeca sem permissao."""
        cod = "".join(secrets.choice(ALFA) for _ in range(16))
        self._gravar({**self._ler(), "codigo": cod, "par": nome_do_par.strip(), "recebe": False})
        return "-".join(cod[i:i + 4] for i in range(0, 16, 4))

    def parear(self, codigo, nome_do_par):
        if len(_norm(codigo)) != 16:
            raise ParErro("Codigo invalido (sao 16 letras/numeros).")
        self._gravar({**self._ler(), "codigo": _norm(codigo), "par": nome_do_par.strip(), "recebe": False})

    def permitir(self, sim=True):
        d = self._ler()
        if not d.get("codigo"):
            raise ParErro("Ainda nao ha par: gere ou cole um codigo antes.")
        self._gravar({**d, "recebe": bool(sim)})

    def permitir_painel(self, sim=True):
        """O dono libera (ou nao) o par para VER o painel deste Braniac (so leitura)."""
        d = self._ler()
        if not d.get("codigo"):
            raise ParErro("Ainda nao ha par: gere ou cole um codigo antes.")
        self._gravar({**d, "painel": bool(sim)})

    def definir_painel_porta(self, porta):
        self._gravar({**self._ler(), "painel_porta": int(porta)})

    def info(self):
        d = self._ler()
        return {**self.estado, "par": d.get("par", ""), "pareado": bool(d.get("codigo")), "recebe": bool(d.get("recebe")), "painel": bool(d.get("painel"))}

    # ---------- receber ----------
    def _limite_ok(self):
        agora = time.time()
        self._tempos = [t for t in self._tempos if agora - t < 60]
        if len(self._tempos) >= LIMITE_MIN:
            return False
        self._tempos.append(agora)
        return True

    def _painel_local(self, path):
        """GET somente leitura no painel local. Devolve (status, content-type, bytes)."""
        porta = self._ler().get("painel_porta")      # o dono escolhe qual tela da loja o par ve (par_cli painel_porta N); sem isso, o painel padrao
        base = f"http://127.0.0.1:{int(porta)}" if str(porta).isdigit() else self.painel_base
        if not base or not path.startswith("/") or ".." in path or "//" in path or "\\" in path or len(path) > 300:
            return 404, "text/plain", b"nao encontrado"
        try:
            with urllib.request.urlopen(base + path, timeout=15) as r:
                return r.status, r.headers.get("Content-Type", "application/octet-stream"), r.read(MAX_PAINEL)
        except urllib.error.HTTPError as e:
            return e.code, "text/plain", b""
        except OSError:
            return 502, "text/plain", b"painel indisponivel"

    def _tratar_painel(self, canal, req, loop):
        i, d = req.get("i"), self._ler()
        enviar = lambda o: loop.call_soon_threadsafe(canal.send, json.dumps({"i": i, **o}))   # aiortc nao e thread-safe
        agora = time.time()
        self._tp = [t for t in self._tp if agora - t < 60]
        if not d.get("painel") or not self.painel_base:
            return enviar({"k": 0, "n": 1, "st": 403, "ct": "text/plain", "b64": base64.b64encode(b"O dono deste Braniac nao liberou o painel.").decode()})
        if len(self._tp) >= LIMITE_PAINEL:
            return enviar({"k": 0, "n": 1, "st": 429, "ct": "text/plain", "b64": ""})
        self._tp.append(agora)
        st, ct, corpo = self._painel_local(str(req.get("path", "/")))
        b64 = base64.b64encode(corpo).decode()
        partes = [b64[x:x + PARTE] for x in range(0, len(b64), PARTE)] or [""]
        for k, p in enumerate(partes):
            enviar({"k": k, "n": len(partes), "st": st, "ct": ct, "b64": p})

    def _tratar(self, canal, req, loop):
        d = self._ler()
        i = req.get("i")
        texto = str(req.get("texto", ""))[:MAX_TEXTO]
        if req.get("t") == "ping":
            return loop.call_soon_threadsafe(canal.send, json.dumps({"i": i, "texto": "pong", "v": 2, "nome": self.nome}))
        if req.get("t") == "painel":
            return self._tratar_painel(canal, req, loop)
        if not d.get("recebe"):
            resp = "O dono deste Braniac ainda nao permitiu conversas."
        elif not self._limite_ok():
            resp = "Muitas mensagens; espere um minuto."
        else:
            try:
                resp = str(self.responder(d.get("par", "outro Braniac"), texto))[:MAX_TEXTO]
            except Exception:
                resp = "Nao consegui responder agora."
        loop.call_soon_threadsafe(canal.send, json.dumps({"i": i, "texto": resp}))   # aiortc nao e thread-safe

    async def _atender(self, oferta, chave, topico, loop):
        from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription
        pc = RTCPeerConnection(RTCConfiguration([RTCIceServer(STUN)]))

        @pc.on("datachannel")
        def _canal(canal):
            self.estado.update(conectado=True, ultimo=time.strftime("%H:%M:%S"), erro="")

            @canal.on("message")
            def _msg(m):
                try:
                    req = json.loads(m)
                except ValueError:
                    return
                loop.run_in_executor(None, self._tratar, canal, req, loop)

        @pc.on("connectionstatechange")
        async def _estado():
            if pc.connectionState in ("failed", "closed", "disconnected"):
                self.estado["conectado"] = False
                await pc.close()
        await pc.setRemoteDescription(RTCSessionDescription(oferta["sdp"], "offer"))
        await pc.setLocalDescription(await pc.createAnswer())
        resp = _cifrar(chave, {"t": "answer", "sid": oferta["sid"], "sdp": pc.localDescription.sdp, "ts": time.time()})
        await loop.run_in_executor(None, _publicar, topico, resp)
        return pc

    def _ouvir(self, loop):
        visto = set()
        while not self._stop.is_set():
            d = self._ler()
            if not d.get("codigo"):
                self._stop.wait(5)
                continue
            try:
                chave, topico = _chave(d["codigo"]), _topico(d["codigo"], self.nome)
                req = urllib.request.Request(f"{SINAL}/{topico}/sse?since=1m", headers={"Accept": "text/event-stream"})
                with urllib.request.urlopen(req, timeout=90) as f:
                    self.estado["erro"] = ""
                    for linha in f:
                        if self._stop.is_set():
                            return
                        if not linha.startswith(b"data:"):
                            continue
                        try:
                            o = _decifrar(chave, json.loads(linha[5:]).get("message", ""))
                        except Exception:
                            continue
                        if o.get("t") != "offer" or o["sid"] in visto or abs(time.time() - o.get("ts", 0)) > JANELA_S:
                            continue
                        visto.add(o["sid"])
                        try:
                            self._pcs.append(asyncio.run_coroutine_threadsafe(self._atender(o, chave, topico, loop), loop).result(timeout=60))
                        except Exception as e:
                            self.estado["erro"] = "oferta: " + str(e)[:80]
            except Exception as e:
                if self._stop.is_set():
                    return
                self.estado["erro"] = "sinalizacao: " + str(e)[:80]
                self._stop.wait(5)

    def iniciar(self):
        """Comeca a ouvir (thread). Sem par cadastrado, so espera. Chame uma vez."""
        if self.estado["ouvindo"]:
            return self.info()
        self._stop.clear()
        self.estado["ouvindo"] = True
        threading.Thread(target=self._ouvir, args=(self._loop_ativo(),), daemon=True).start()
        return self.info()

    def _loop_ativo(self):
        with self._lock:
            if self._loop is None:
                self._loop = asyncio.new_event_loop()
                threading.Thread(target=self._loop.run_forever, daemon=True).start()
        return self._loop

    def parar(self):
        self._stop.set()
        self.estado.update(ouvindo=False, conectado=False)

    # ---------- enviar ----------
    async def _falar(self, d, texto, timeout):
        from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription
        chave, topico = _chave(d["codigo"]), _topico(d["codigo"], d["par"])
        sid, loop = secrets.token_hex(8), asyncio.get_running_loop()
        pc = RTCPeerConnection(RTCConfiguration([RTCIceServer(STUN)]))
        pronto, resposta = loop.create_future(), loop.create_future()
        canal = pc.createDataChannel("par")

        @canal.on("open")
        def _aberto():
            canal.send(json.dumps({"i": sid, "texto": texto[:MAX_TEXTO]}))

        @canal.on("message")
        def _msg(m):
            try:
                r = json.loads(m)
            except ValueError:
                return
            if r.get("i") == sid and not resposta.done():
                resposta.set_result(str(r.get("texto", ""))[:MAX_TEXTO])
        try:
            await pc.setLocalDescription(await pc.createOffer())
            await asyncio.wait_for(_aguardar_ice(pc), 10)
            await loop.run_in_executor(None, _publicar, topico, _cifrar(chave, {"t": "offer", "sid": sid, "sdp": pc.localDescription.sdp, "ts": time.time()}))
            resp_sdp = await asyncio.wait_for(loop.run_in_executor(None, _esperar_resposta, chave, topico, sid, timeout), timeout)
            await pc.setRemoteDescription(RTCSessionDescription(resp_sdp, "answer"))
            return await asyncio.wait_for(resposta, timeout)
        finally:
            try:
                await asyncio.wait_for(pc.close(), 3)     # fechar o SCTP pode demorar; a resposta ja esta em maos
            except Exception:
                pass

    def falar(self, texto, timeout=60):
        """Manda uma mensagem ao Braniac pareado e devolve a resposta dele (texto). Levanta ParErro se nao conectar."""
        d = self._ler()
        if not d.get("codigo"):
            raise ParErro("Sem par: gere ou cole um codigo.")
        try:
            return asyncio.run(self._falar(d, str(texto), timeout))
        except (asyncio.TimeoutError, OSError) as e:
            raise ParErro("O outro Braniac nao respondeu (desligado, sem permissao ou rede fechada): " + str(e)[:60])

    # ---------- conexao persistente (ping e painel) ----------
    async def _garantir(self, timeout):
        from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription
        c = self._cli
        if c and c["canal"].readyState == "open":
            return c
        d = self._ler()
        if not d.get("codigo"):
            raise ParErro("Sem par: gere ou cole um codigo.")
        chave, topico = _chave(d["codigo"]), _topico(d["codigo"], d["par"])
        sid, loop = secrets.token_hex(8), asyncio.get_running_loop()
        pc = RTCPeerConnection(RTCConfiguration([RTCIceServer(STUN)]))
        canal, aberto = pc.createDataChannel("par"), loop.create_future()
        novo = {"pc": pc, "canal": canal}

        @canal.on("open")
        def _aberto():
            if not aberto.done():
                aberto.set_result(True)

        @canal.on("message")
        def _msg(m):
            try:
                r = json.loads(m)
            except ValueError:
                return
            p = self._pend.get(r.get("i"))
            if not p or p["fut"].done():
                return
            if "k" in r:
                p["partes"][r["k"]] = r
                if len(p["partes"]) >= r["n"]:
                    p["fut"].set_result([p["partes"][k] for k in sorted(p["partes"])])
            else:
                p["fut"].set_result([r])

        @pc.on("connectionstatechange")
        async def _estado():
            if pc.connectionState in ("failed", "closed", "disconnected") and self._cli is novo:
                self._cli = None
                await pc.close()
        try:
            await pc.setLocalDescription(await pc.createOffer())
            await asyncio.wait_for(_aguardar_ice(pc), 10)
            await loop.run_in_executor(None, _publicar, topico, _cifrar(chave, {"t": "offer", "sid": sid, "sdp": pc.localDescription.sdp, "ts": time.time()}))
            resp_sdp = await asyncio.wait_for(loop.run_in_executor(None, _esperar_resposta, chave, topico, sid, timeout), timeout)
            await pc.setRemoteDescription(RTCSessionDescription(resp_sdp, "answer"))
            await asyncio.wait_for(aberto, timeout)
        except BaseException:
            try:
                await asyncio.wait_for(pc.close(), 3)
            except Exception:
                pass
            raise
        self._cli = novo
        return novo

    async def _pedir(self, req, timeout):
        c = await self._garantir(timeout)
        i = secrets.token_hex(6)
        self._pend[i] = {"fut": asyncio.get_running_loop().create_future(), "partes": {}}
        try:
            c["canal"].send(json.dumps({**req, "i": i}))
            return await asyncio.wait_for(self._pend[i]["fut"], timeout)
        finally:
            self._pend.pop(i, None)

    def pedir(self, req, timeout=30):
        """Pedido pela conexao persistente (abre se preciso). Devolve a lista de respostas; ParErro se o outro lado nao responder."""
        try:
            return asyncio.run_coroutine_threadsafe(self._pedir(req, timeout), self._loop_ativo()).result(timeout + 20)
        except ParErro:
            raise
        except Exception as e:
            raise ParErro("O outro Braniac nao respondeu: " + (str(e)[:60] or type(e).__name__))

    def ping(self):
        """True se o outro Braniac esta de pe. Nao gasta IA dele (resposta fixa)."""
        try:
            return self.pedir({"t": "ping"}, 25)[0].get("texto") == "pong"
        except ParErro:
            return False

    def painel_get(self, path):
        """(status, content-type, bytes) de um GET no painel do outro Braniac (precisa da liberacao dele)."""
        r = self.pedir({"t": "painel", "path": path}, 30)
        if "b64" not in r[0]:
            return 502, "text/plain", b"o outro Braniac e de uma versao sem painel (atualize o par_webrtc.py dele)"
        return r[0]["st"], r[0]["ct"], base64.b64decode("".join(x["b64"] for x in r))

    def conversar(self, abertura, gerar, turnos=4):
        """Conversa sozinha, sem humano: manda `abertura`, le a resposta e usa gerar(historico)->proxima fala. Para no limite (max 6 turnos)."""
        hist, fala = [], abertura
        for _ in range(min(int(turnos), 6)):
            resp = self.falar(fala)
            hist += [("eu", fala), ("par", resp)]
            fala = gerar(hist)
            if not fala:
                break
        return hist


async def _aguardar_ice(pc):
    while pc.iceGatheringState != "complete":
        await asyncio.sleep(0.1)


def _esperar_resposta(chave, topico, sid, timeout):
    fim = time.time() + timeout
    while time.time() < fim:          # reabre o fluxo a cada 8 s: assim a thread nunca fica presa depois do prazo
        try:
            req = urllib.request.Request(f"{SINAL}/{topico}/sse?since=60s", headers={"Accept": "text/event-stream"})
            with urllib.request.urlopen(req, timeout=8) as f:
                for linha in f:
                    if time.time() > fim:
                        break
                    if not linha.startswith(b"data:"):
                        continue
                    try:
                        o = _decifrar(chave, json.loads(linha[5:]).get("message", ""))
                    except Exception:
                        continue
                    if o.get("t") == "answer" and o.get("sid") == sid:
                        return o["sdp"]
        except OSError:
            time.sleep(1)
    raise OSError("sem resposta")
