# -*- coding: utf-8 -*-
"""No do BRANIAC LINK: sinalizacao + conexao WebRTC (aiortc) + dispatcher do protocolo (SPEC.md secoes 2 a 6).
A sinalizacao so leva o 'ola' (SDP) cifrado com o segredo do par e assinado pela chave do dispositivo; a assinatura cobre o hash do SDP e o
fingerprint DTLS, entao quem controla o canal de sinalizacao nao consegue se passar pelo par. Depois de conectado nada passa por la.
Pedido do outro lado e DADO: tarefa so roda se a permissao do dono for 'aceitar' (ou depois de aprovar() em 'perguntar')."""
import asyncio
import base64
import hashlib
import json
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from . import arquivos, protocolo
from .confianca import ConviteErro, Pares, prova
from .identidade import b64, id_de, unb64

STUN = "stun:stun.l.google.com:19302"
MAX_TEXTO, LIMITE_MIN = 8000, 120
_FP = re.compile(r"a=fingerprint:sha-256 ([0-9A-Fa-f:]{95})")


class LinkErro(RuntimeError):
    pass


# ---------------- sinalizacao ----------------
class SinalMemoria:
    """Para testes: mensagens em memoria."""
    def __init__(self):
        self.msgs, self._l = {}, threading.Lock()

    def publicar(self, topico, texto):
        with self._l:
            self.msgs.setdefault(topico, []).append(texto)

    def ouvir(self, topico, visto):
        with self._l:
            return [m for m in self.msgs.get(topico, []) if m not in visto]


class SinalNtfy:
    """ntfy.sh (ou servidor proprio): so ve texto cifrado e o nome de um topico que nao da para adivinhar."""
    def __init__(self, base="https://ntfy.sh"):
        self.base, self.bloqueado_ate = base.rstrip("/"), 0.0

    def publicar(self, topico, texto):
        if len(texto.encode()) > 3900:
            raise LinkErro("sinalizacao grande demais para o canal")
        if time.time() < self.bloqueado_ate:
            raise LinkErro("cota diaria do ntfy esgotada")
        try:
            urllib.request.urlopen(urllib.request.Request(f"{self.base}/{topico}", data=texto.encode(), method="POST"), timeout=20).read()
        except urllib.error.HTTPError as e:
            if e.code == 429 and "daily message quota" in e.read().decode("utf-8", "replace"):
                # cota de 250/dia zera a 0h UTC; insistir antes so gasta o limite de pedidos e derruba a escuta (sinal_erro)
                self.bloqueado_ate = (time.time() // 86400 + 1) * 86400 + 60
                raise LinkErro("cota diaria do ntfy esgotada")
            raise

    def ouvir(self, topico, visto):
        url = f"{self.base}/{topico}/json?poll=1&since={int(time.time()) - 120}"
        with urllib.request.urlopen(url, timeout=20) as r:
            msgs = [json.loads(l).get("message", "") for l in r.read().decode().splitlines() if l.strip()]
        return [m for m in msgs if m and m not in visto]


def _topico(seg, para_id):
    return "blink-" + hashlib.sha256(f"{seg}|para|{para_id}".encode()).hexdigest()[:32]


def _chave(seg):
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=b"braniac-link-v1", info=b"sinal").derive(unb64(seg))


def _cifrar(seg, obj):
    iv = os.urandom(12)
    return b64(iv + AESGCM(_chave(seg)).encrypt(iv, zlib.compress(json.dumps(obj).encode()), None))


def _decifrar(seg, txt):
    b = unb64(txt)
    return json.loads(zlib.decompress(AESGCM(_chave(seg)).decrypt(b[:12], b[12:], None), 0, 200_000))


_VIRTUAL = re.compile(r"^(192\.168\.56\.|172\.(1[6-9]|2\d|3[01])\.|169\.254\.|26\.|25\.|10\.0\.2\.|fe80:|fd|2001:0?:)", re.I)


CRLF = chr(13) + chr(10)


def sem_virtuais(sdp):
    """Tira do SDP os candidatos de placas virtuais (VirtualBox, WSL/Docker, Radmin/Hamachi, Teredo): so atrapalham a conexao direta."""
    saida = []
    for linha in sdp.split(CRLF):
        if linha.startswith("a=candidate:"):
            partes = linha.split(" ")
            if len(partes) > 4 and _VIRTUAL.match(partes[4]):
                continue
        saida.append(linha)
    return CRLF.join(saida)


def _fp(sdp):
    m = _FP.search(sdp)
    return m.group(1).upper() if m else ""


class _Sessao:
    def __init__(self, par_id, canal, pc):
        self.par_id, self.canal, self.pc = par_id, canal, pc
        self.pend, self.receb, self.envios, self.tempos = {}, {}, {}, []
        self.anti = protocolo.Antirepeticao()


class _CanalRelay:
    """Faz o papel do canal de dados, mas publica no canal de sinalizacao (cifrado com o segredo do par). So texto; cabe ~3 KB por mensagem."""
    readyState, bufferedAmount = "open", 0

    def __init__(self, no, par_id, seg):
        self.no, self.par_id, self.seg = no, par_id, seg

    def send(self, dados):
        if isinstance(dados, bytes):
            raise LinkErro("arquivos nao passam pelo plano B (precisa da conexao direta)")
        carga = _cifrar(self.seg, {"t": "msg", "env": dados})
        asyncio.get_running_loop().run_in_executor(None, self._publicar, _topico(self.seg, self.par_id), carga)

    def _publicar(self, topico, carga):
        try:
            self.no.sinal.publicar(topico, carga)
        except Exception as e:
            self.no._log(self.par_id, "relay_erro", repr(e)[:100])


class No:
    def __init__(self, ident, pares, pasta, executor=None, agentes=None, ao_msg=None, sinal=None, ice=(STUN,), intervalo=6.0, p2p=True, p2p_espera=12):
        """executor(agente, pedido, par_id) -> str; agentes() -> [{nome, descricao, capacidades}]; ao_msg(par_id, texto).
        p2p=False ou conexao direta que nao abre em p2p_espera segundos: o TEXTO segue pelo canal de sinalizacao (cifrado e assinado), mais lento e sem arquivos."""
        self.p2p, self.p2p_espera, self.relays, self._p2p_falhou = p2p, p2p_espera, {}, {}
        self.ident, self.pares, self.pasta = ident, pares, Path(pasta)
        self.executor, self.agentes, self.ao_msg = executor, agentes or (lambda: []), ao_msg
        self.sinal, self.ice, self.intervalo = sinal or SinalNtfy(), list(ice), intervalo
        self.sessoes, self._loop, self._thr, self._visto, self._parar, self._espera = {}, None, None, {}, threading.Event(), 0
        self.pasta.mkdir(parents=True, exist_ok=True)
        self.arq_pend, self.arq_log = self.pasta / "pendencias.json", self.pasta / "registro.jsonl"

    def _ice_servers(self, RTCIceServer):
        """ice: textos 'stun:host:porta' ou dicts {urls, username, credential} (TURN opcional, so entra quando o caminho direto falha)."""
        return [RTCIceServer(**u) if isinstance(u, dict) else RTCIceServer(u) for u in self.ice]

    # ---------- registro e pendencias ----------
    def _log(self, par, evento, detalhe=""):
        try:
            with self.arq_log.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": int(time.time()), "par": par, "evento": evento, "detalhe": str(detalhe)[:200]}, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def pendencias(self):
        try:
            return json.loads(self.arq_pend.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []

    def _add_pend(self, item):
        p = self.pendencias()[-49:] + [item]
        self.arq_pend.write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")

    def recusar(self, pid_item):
        self.arq_pend.write_text(json.dumps([p for p in self.pendencias() if p["id"] != pid_item], ensure_ascii=False), encoding="utf-8")
        self._log("", "pendencia_recusada", pid_item)

    def aprovar(self, pid_item):
        """O dono aprovou um pedido que estava em 'perguntar': roda o executor e tenta entregar o resultado ao par."""
        item = next((p for p in self.pendencias() if p["id"] == pid_item), None)
        if not item:
            raise LinkErro("pendencia nao encontrada")
        self.recusar(pid_item)
        texto = self._executar(item["par"], item["agente"], item["pedido"])
        try:
            self._rodar(self._enviar(item["par"], "tarefa.resultado", {"ok": True, "texto": texto}, ref=item["id"]), 30)
        except Exception:
            pass
        return texto

    # ---------- ciclo de vida ----------
    def iniciar(self):
        if self._thr:
            return
        self._loop = asyncio.new_event_loop()
        self._thr = threading.Thread(target=self._rodar_loop, daemon=True, name="braniac-link")
        self._thr.start()

    def _rodar_loop(self):
        asyncio.set_event_loop(self._loop)
        self._tarefa = self._loop.create_task(self._ouvir())
        self._loop.run_forever()

    def parar(self):
        self._parar.set()
        if self._loop:
            async def fechar():
                self._tarefa.cancel()
                for s in list(self.sessoes.values()):
                    await s.pc.close()
            try:
                asyncio.run_coroutine_threadsafe(fechar(), self._loop).result(5)
            except Exception:
                pass
            self._loop.call_soon_threadsafe(self._loop.stop)

    def _rodar(self, coro, timeout):
        if not self._loop:
            raise LinkErro("no nao iniciado")
        try:
            return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout)
        except (asyncio.TimeoutError, TimeoutError):
            raise LinkErro("sem resposta no tempo (par desligado, sem permissao ou rede fechada)")

    # ---------- sinalizacao: ouvir ----------
    def _segredos(self):
        """seg -> conhecido (par confiavel/pendente) ou convite aberto."""
        segs = {p["seg"] for p in self.pares._ler()["pares"].values() if p.get("seg") and p["estado"] != "revogado"}
        return segs | set(self.pares.convites_abertos())

    async def _ouvir(self):
        while not self._parar.is_set():
            for seg in self._segredos():
                top = _topico(seg, self.ident.id)
                visto = self._visto.setdefault(top, set())
                try:
                    novas = await self._loop.run_in_executor(None, self.sinal.ouvir, top, visto)
                    self._espera = 0
                except Exception as e:
                    self._espera = min(60, max(self.intervalo, self._espera * 2))      # 429 do ntfy: espera progressiva
                    self._log("", "sinal_erro", repr(e)[:100])
                    await asyncio.sleep(self._espera)
                    continue
                for txt in novas:
                    visto.add(txt)
                    try:
                        await self._atender_oferta(seg, txt)
                    except Exception as e:
                        self._log("", "oferta_rejeitada", repr(e)[:120])
            await asyncio.sleep(self.intervalo)

    def _hello(self, sdp, sid, extra=None):
        return protocolo.criar(self.ident, "hello", {"sid": sid, "sdp": hashlib.sha256(sdp.encode()).hexdigest(), "fp": _fp(sdp),
                                                      "nome": self.ident.nome, **(extra or {})})

    def _conferir_hello(self, hello_txt, sdp, sid):
        env = protocolo.validar(hello_txt)
        c = env["corpo"]
        if env["tipo"] != "hello" or c.get("sid") != sid or c.get("sdp") != hashlib.sha256(sdp.encode()).hexdigest() or not c.get("fp") or c["fp"] != _fp(sdp):
            raise protocolo.ProtocoloErro("hello nao cobre este SDP")
        return env

    async def _atender_oferta(self, seg, txt):
        from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription
        m = _decifrar(seg, txt)
        if m.get("t") == "msg":
            return await self._atender_relay(seg, m)
        if m.get("t") != "offer":
            return
        env = self._conferir_hello(m["hello"], m["sdp"], m["sid"])
        de, c = env["de"], env["corpo"]
        par = self.pares.get(de)
        if par and par["pub"] == env["pub"] and par["seg"] == seg and par["estado"] != "revogado":
            pass
        elif c.get("prova") and not par:
            self.pares.consumir_convite(seg, self.ident, de, env["pub"], str(c.get("nome", "")), c["prova"])    # primeiro contato com convite valido
            self._log(de, "par_novo_pendente", c.get("nome", ""))
        else:
            raise protocolo.ProtocoloErro("par desconhecido ou revogado")
        pc = RTCPeerConnection(RTCConfiguration(self._ice_servers(RTCIceServer)))
        sess = _Sessao(de, None, pc)

        @pc.on("datachannel")
        def _canal(canal):
            sess.canal = canal
            self._ligar(sess)

        @pc.on("connectionstatechange")
        async def _estado():
            if pc.connectionState in ("failed", "closed"):
                self.sessoes.pop(de, None)
                await pc.close()
        await pc.setRemoteDescription(RTCSessionDescription(m["sdp"], "offer"))
        await pc.setLocalDescription(await pc.createAnswer())
        sdp = sem_virtuais(pc.localDescription.sdp)
        resp = _cifrar(seg, {"t": "answer", "sid": m["sid"], "sdp": sdp, "hello": self._hello(sdp, m["sid"])})
        await self._loop.run_in_executor(None, self.sinal.publicar, _topico(seg, de), resp)
        self.sessoes[de] = sess
        self._log(de, "conexao_aceita")

    # ---------- sinalizacao: conectar ----------
    async def _conectar(self, par_id, convite=None, timeout=30):
        from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription
        s = self.sessoes.get(par_id)
        if s and s.canal and s.canal.readyState == "open":
            return s
        par = self.pares.get(par_id)
        if not par or par["estado"] == "revogado":
            raise LinkErro("par desconhecido ou revogado")
        seg = par["seg"]
        pc, sid = RTCPeerConnection(RTCConfiguration(self._ice_servers(RTCIceServer))), secrets.token_hex(8)
        sess = _Sessao(par_id, pc.createDataChannel("link"), pc)
        aberto = self._loop.create_future()
        sess.canal.on("open", lambda: aberto.done() or aberto.set_result(True))
        await pc.setLocalDescription(await pc.createOffer())
        sdp = sem_virtuais(pc.localDescription.sdp)
        extra = {"prova": prova(seg, par_id, self.ident.id)} if convite else None
        await self._loop.run_in_executor(None, self.sinal.publicar, _topico(seg, par_id),
                                         _cifrar(seg, {"t": "offer", "sid": sid, "sdp": sdp, "hello": self._hello(sdp, sid, extra)}))
        top, visto, fim = _topico(seg, self.ident.id), set(), time.time() + timeout
        while time.time() < fim:
            try:
                novas = await self._loop.run_in_executor(None, self.sinal.ouvir, top, visto)
            except Exception as e:
                self._log(par_id, "sinal_erro", repr(e)[:100])
                await asyncio.sleep(max(self.intervalo, 6))
                continue
            for txt in novas:
                visto.add(txt)
                try:
                    m = _decifrar(seg, txt)
                    if m.get("t") != "answer" or m.get("sid") != sid:
                        continue
                    env = self._conferir_hello(m["hello"], m["sdp"], sid)
                    if env["de"] != par_id or env["pub"] != par["pub"]:
                        continue
                    await pc.setRemoteDescription(RTCSessionDescription(m["sdp"], "answer"))
                    await asyncio.wait_for(aberto, max(1, fim - time.time()))
                    self.sessoes[par_id] = sess
                    self._ligar(sess)
                    self._log(par_id, "conectado")
                    return sess
                except (protocolo.ProtocoloErro, ValueError, KeyError):
                    continue
            await asyncio.sleep(self.intervalo)
        await pc.close()
        raise LinkErro("o par nao respondeu a tempo")

    def conectar(self, par_id, convite=False, timeout=30):
        """Abre (ou reaproveita) a conexao com um par. convite=True no primeiro contato do convidado."""
        self._rodar(self._conectar(par_id, convite, timeout), timeout + 5)

    # ---------- mensagens ----------
    def _ligar(self, sess):
        loop = self._loop

        @sess.canal.on("message")
        def _msg(m):
            loop.create_task(self._receber(sess, m))

    async def _enviar_env(self, sess, tipo, corpo, ref=""):
        env = protocolo.criar(self.ident, tipo, corpo, para=sess.par_id, ref=ref)
        sess.canal.send(env)
        return json.loads(env)["id"]

    # ---------- plano B: texto pelo canal de sinalizacao ----------
    def _relay(self, par_id):
        s = self.relays.get(par_id)
        if not s:
            par = self.pares.get(par_id)
            if not par or par["estado"] == "revogado" or not par.get("seg"):
                raise LinkErro("par desconhecido ou revogado")
            s = self.relays[par_id] = _Sessao(par_id, _CanalRelay(self, par_id, par["seg"]), None)
        return s

    async def _atender_relay(self, seg, m):
        par_id = next((i for i, p in self.pares._ler()["pares"].items() if p.get("seg") == seg and p["estado"] != "revogado"), None)
        if par_id and isinstance(m.get("env"), str):
            await self._receber(self._relay(par_id), m["env"])

    def _direta(self, par_id):
        s = self.sessoes.get(par_id)
        return bool(s and s.canal and s.canal.readyState == "open")

    async def _sessao(self, par_id):
        """Conexao direta quando abrir; senao o plano B (so texto)."""
        s = self.sessoes.get(par_id)
        if s and s.canal and s.canal.readyState == "open":
            return s
        if self.p2p and time.time() - self._p2p_falhou.get(par_id, 0) > 300:     # depois de uma falha, nao tenta a direta por 5 min
            try:
                return await self._conectar(par_id, timeout=self.p2p_espera)
            except LinkErro:
                self._p2p_falhou[par_id] = time.time()
                self._log(par_id, "p2p_falhou_usando_relay")
        return self._relay(par_id)

    async def _enviar(self, par_id, tipo, corpo, ref=""):
        return await self._enviar_env(await self._sessao(par_id), tipo, corpo, ref)

    async def _pedir(self, sess, tipo, corpo, timeout=60):
        fut = self._loop.create_future()
        env = protocolo.criar(self.ident, tipo, corpo, para=sess.par_id)
        sess.pend[json.loads(env)["id"]] = fut
        sess.canal.send(env)
        try:
            return await asyncio.wait_for(fut, timeout)
        finally:
            sess.pend.pop(json.loads(env)["id"], None)

    def _limite_ok(self, sess):
        agora = time.time()
        sess.tempos = [t for t in sess.tempos if agora - t < 60]
        sess.tempos.append(agora)
        return len(sess.tempos) <= LIMITE_MIN

    async def _receber(self, sess, m):
        try:
            if isinstance(m, bytes):
                return self._quadro(sess, m)
            if not self._limite_ok(sess):
                return
            env = protocolo.validar(m, sess.anti)
            if env["de"] != sess.par_id or env["para"] not in ("", self.ident.id):
                raise protocolo.ProtocoloErro("remetente ou destino inesperado")
            par = self.pares.get(sess.par_id)
            if not par or par["estado"] == "revogado":
                raise protocolo.ProtocoloErro("par revogado")
            fut = sess.pend.get(env["ref"]) if env["ref"] else None
            if fut and not fut.done():
                return fut.set_result(env)
            await self._tratar(sess, env)
        except (protocolo.ProtocoloErro, arquivos.ArquivoErro) as e:
            self._log(sess.par_id, "rejeitado", e)
        except Exception as e:
            self._log(sess.par_id, "erro", repr(e)[:150])

    async def _tratar(self, sess, env):
        t, c, pid = env["tipo"], env["corpo"], sess.par_id
        resp = lambda tipo, corpo: self._enviar_env(sess, tipo, corpo, ref=env["id"])
        confiavel = (self.pares.get(pid) or {}).get("estado") == "confiavel"
        if t == "ping":
            return await resp("pong", {"nome": self.ident.nome})
        if not confiavel:                                       # pendente so faz ping: ninguem conversa antes do dono conferir o SAS
            self._log(pid, "ignorado_pendente", t)
            return
        if t == "msg":
            if self.pares.decidir(pid, "msg") == "aceitar" and self.ao_msg:
                self._log(pid, "msg_recebida", str(c.get("texto", ""))[:300])
                await self._loop.run_in_executor(None, self.ao_msg, pid, str(c.get("texto", ""))[:MAX_TEXTO])
                return await resp("pong", {})
            return await resp("tarefa.recusada", {"motivo": "mensagens nao liberadas"})
        if t == "caps.pedir":
            return await resp("caps", {"agentes": self.agentes()[:50]})
        if t == "tarefa.pedido":
            agente, pedido = str(c.get("agente", ""))[:60], str(c.get("pedido", ""))[:MAX_TEXTO]
            nivel = self.pares.decidir(pid, "tarefa", agente)
            self._log(pid, "tarefa_pedido:" + nivel, f"{agente}: {pedido[:60]}")
            if nivel == "recusar" or not self.executor:
                return await resp("tarefa.recusada", {"motivo": "sem permissao para este agente"})
            if nivel == "perguntar":
                self._add_pend({"id": env["id"], "par": pid, "agente": agente, "pedido": pedido, "ts": int(time.time())})
                return await resp("tarefa.pendente", {"motivo": "aguardando o dono aprovar"})
            texto = await self._loop.run_in_executor(None, self._executar, pid, agente, pedido)
            return await resp("tarefa.resultado", {"ok": True, "texto": texto})
        if t == "arquivo.oferta":
            if self.pares.decidir(pid, "arquivo") != "aceitar":
                self._log(pid, "arquivo_oferta_recusada", c.get("nome", ""))
                return await resp("arquivo.recusa", {"motivo": "o dono nao liberou arquivos deste par"})
            rec = arquivos.Recebimento(self.pasta / "recebidos" / pid, c)
            sess.receb[rec.fid] = rec
            self._log(pid, "arquivo_aceito", f"{rec.nome} {rec.tam}")
            return await resp("arquivo.aceita", {"fid": rec.fid, "faltando": rec.faltando()})
        if t == "arquivo.fim":
            rec = sess.receb.get(str(c.get("fid")))
            if not rec:
                return await resp("arquivo.falta", {"fid": c.get("fid"), "faltando": []})
            if rec.faltando():
                return await resp("arquivo.falta", {"fid": rec.fid, "faltando": rec.faltando()[:5000]})
            try:
                destino = rec.finalizar()
                self._log(pid, "arquivo_recebido", destino)
                return await resp("arquivo.ok", {"fid": rec.fid, "ok": True})
            except arquivos.ArquivoErro as e:
                return await resp("arquivo.ok", {"fid": rec.fid, "ok": False, "motivo": str(e)})

    def _executar(self, par, agente, pedido):
        try:
            return str(self.executor(agente, pedido, par))[:MAX_TEXTO]
        except Exception as e:
            return "Nao consegui atender: " + repr(e)[:100]

    def _quadro(self, sess, q):
        rec = sess.receb.get(bytes(q[:8]).hex())
        if rec:
            rec.receber(q)

    # ---------- API de uso (sincrona) ----------
    def ping(self, par_id, timeout=20):
        async def f():
            return (await self._pedir(await self._sessao(par_id), "ping", {}, timeout))["tipo"] == "pong"
        return self._rodar(f(), timeout + 35)

    def enviar_msg(self, par_id, texto, timeout=30):
        if time.time() < getattr(self.sinal, "bloqueado_ate", 0) and not self._direta(par_id):
            raise LinkErro("cota diaria do ntfy esgotada")      # falha na hora em vez de esperar 80 s por um pong que nao vem
        async def f():
            return (await self._pedir(await self._sessao(par_id), "msg", {"texto": str(texto)[:MAX_TEXTO]}, timeout))
        r = self._rodar(f(), timeout + 35)
        if r["tipo"] != "pong":
            raise LinkErro(r["corpo"].get("motivo", "recusado"))

    def capacidades(self, par_id, timeout=20):
        async def f():
            return (await self._pedir(await self._sessao(par_id), "caps.pedir", {}, timeout))
        r = self._rodar(f(), timeout + 35)
        return r["corpo"].get("agentes", []) if r["tipo"] == "caps" else []

    def pedir_tarefa(self, par_id, agente, pedido, timeout=120):
        """Devolve (estado, texto): 'resultado' | 'pendente' | 'recusada'."""
        async def f():
            return await self._pedir(await self._sessao(par_id), "tarefa.pedido", {"agente": agente, "pedido": str(pedido)[:MAX_TEXTO]}, timeout)
        r = self._rodar(f(), timeout + 35)
        return r["tipo"].split(".")[1], str(r["corpo"].get("texto") or r["corpo"].get("motivo") or "")

    def enviar_arquivo(self, par_id, caminho, timeout=600):
        async def f():
            sess, env = await self._conectar(par_id), arquivos.Envio(caminho)
            r = await self._pedir(sess, "arquivo.oferta", env.oferta())
            if r["tipo"] != "arquivo.aceita":
                raise LinkErro(r["corpo"].get("motivo", "recusado"))
            falta = r["corpo"].get("faltando", [])
            for _ in range(4):
                for i in falta:
                    while sess.canal.bufferedAmount > 1_000_000:
                        await asyncio.sleep(0.01)
                    sess.canal.send(env.quadro(int(i)))
                r = await self._pedir(sess, "arquivo.fim", {"fid": env.fid.hex()}, 60)
                if r["tipo"] == "arquivo.ok":
                    if not r["corpo"].get("ok"):
                        raise LinkErro(r["corpo"].get("motivo", "o outro lado nao validou o arquivo"))
                    self._log(par_id, "arquivo_enviado", f"{caminho} {env.tam}")
                    return True
                falta = r["corpo"].get("faltando", [])
            raise LinkErro("arquivo nao completou apos 4 tentativas")
        return self._rodar(f(), timeout)
