# -*- coding: utf-8 -*-
"""ACESSO REMOTO P2P (24/10/2026): o app B.R.A.N.I.A.C do celular conversa com o Braniac deste notebook DIRETO (WebRTC), sem servidor no meio.
Como: o celular e o notebook trocam so a 'apresentacao' (SDP) por um canal de sinalizacao publico (ntfy.sh), CIFRADA com uma chave derivada do CODIGO
de pareamento (AES-GCM) -- quem nao tem o codigo nao le nem forja. Depois disso o canal de dados WebRTC (DTLS) leva as requisicoes HTTP do app
para o servidor local (127.0.0.1) e volta com a resposta. Desligado de fabrica: so existe com o botao 'Acesso remoto' ligado no PC.
Limite: sem servidor TURN, redes de operadora muito fechadas (CGNAT simetrico) podem nao conectar. /api/remoto* nunca passa pelo tunel."""
import asyncio
import base64
import hashlib
import json
import os
import secrets
import threading
import time
import urllib.request
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

DADOS = Path(__file__).resolve().parent / "data"
ARQ = DADOS / "remoto.json"
SINAL = "https://ntfy.sh"
STUN = "stun:stun.l.google.com:19302"
PORTA = 8765
FRAME = 30000          # caracteres base64 por mensagem do canal (limite SCTP seguro)
ALFA = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
ESTADO = {"ligado": False, "conectado": False, "ultimo": "", "erro": "", "tentativas": []}


def _tentou(msg):
    ESTADO["tentativas"] = (ESTADO["tentativas"] + [time.strftime("%H:%M:%S") + " " + msg])[-6:]
    try:    # o diagnostico sobrevive a reinicios (data/remoto.log): so horario e estado de rede, nunca codigo nem conteudo
        with (DADOS / "remoto.log").open("a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S") + " " + msg + "\n")
    except OSError:
        pass
_stop = threading.Event()


def _ler():
    try:
        return json.loads(ARQ.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _salvar(d):
    DADOS.mkdir(exist_ok=True)
    ARQ.write_text(json.dumps(d), encoding="utf-8")


def novo_codigo():
    cod = "".join(secrets.choice(ALFA) for _ in range(16))
    d = _ler()
    d["codigo"] = cod
    _salvar(d)
    return formatar(cod)


def formatar(c):
    return "-".join(c[i:i + 4] for i in range(0, 16, 4))


def codigo():
    d = _ler()
    if not d.get("codigo"):
        novo_codigo()
        d = _ler()
    return d["codigo"]


def chaves(cod):
    """(chave AES-256, topico do ntfy) derivados do codigo, igual no celular (WebCrypto)."""
    cod = cod.replace("-", "").replace(" ", "").upper()
    chave = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"braniac-remoto-v1", info=b"aes").derive(cod.encode())
    topico = "braniac-" + hashlib.sha256((cod + "|topico").encode()).hexdigest()[:32]
    return chave, topico


def cifrar(chave, obj):
    iv = os.urandom(12)
    return base64.b64encode(iv + AESGCM(chave).encrypt(iv, json.dumps(obj).encode(), None)).decode()


def decifrar(chave, txt):
    b = base64.b64decode(txt)
    return json.loads(AESGCM(chave).decrypt(b[:12], b[12:], None))


def _local(req):
    """Executa a requisicao do celular no servidor local. /api/remoto* e barrado (so o PC liga/desliga)."""
    path = req.get("p", "/")
    if path.startswith(("/par", "/api/par", "/api/remoto", "/api/autonomia", "/api/atendimento-auto", "/api/airbnb-auto")):   # so no PC: nada que arme/ligue pode vir pelo celular
        return 403, {"content-type": "application/json"}, b'{"erro":"so no PC"}'
    corpo = base64.b64decode(req["b"]) if req.get("b") else None
    r = urllib.request.Request(f"http://127.0.0.1:{PORTA}{path}", data=corpo, method=req.get("m", "GET"))
    r.add_header("Origin", f"http://127.0.0.1:{PORTA}")
    if req.get("c"):
        r.add_header("Content-Type", req["c"])
    try:
        with urllib.request.urlopen(r, timeout=300) as resp:
            return resp.status, {"content-type": resp.headers.get("content-type", "")}, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, {"content-type": e.headers.get("content-type", "")}, e.read()
    except Exception as e:
        return 502, {"content-type": "application/json"}, json.dumps({"erro": str(e)[:100]}).encode()


def _responder(canal, msg, loop):
    st, h, corpo = _local(msg)
    b64 = base64.b64encode(corpo).decode()
    partes = [b64[i:i + FRAME] for i in range(0, len(b64), FRAME)] or [""]
    for n, p in enumerate(partes):
        # aiortc nao e thread-safe: o envio tem que acontecer no loop do WebRTC
        loop.call_soon_threadsafe(canal.send, json.dumps({"i": msg["i"], "s": st, "c": h.get("content-type", ""), "n": len(partes), "x": n, "b": p}))


async def _atender_oferta(oferta, chave, topico):
    from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription
    pc = RTCPeerConnection(RTCConfiguration([RTCIceServer(STUN)]))
    loop = asyncio.get_running_loop()

    @pc.on("datachannel")
    def _canal(canal):
        ESTADO.update(conectado=True, ultimo=time.strftime("%H:%M:%S"), erro="")

        @canal.on("message")
        def _msg(m):
            try:
                req = json.loads(m)
            except ValueError:
                return
            loop.run_in_executor(None, _responder, canal, req, loop)

    @pc.on("connectionstatechange")
    async def _estado():
        if pc.connectionState in ("failed", "closed", "disconnected"):
            ESTADO["conectado"] = False
            await pc.close()
    import re as _re
    tipos = _re.findall(r"typ (host|srflx|relay)", oferta["sdp"])
    _tentou("celular ofereceu caminhos: " + ", ".join(f"{t}={tipos.count(t)}" for t in ("host", "srflx", "relay")))

    @pc.on("iceconnectionstatechange")
    async def _ice():
        _tentou("rede: " + pc.iceConnectionState)
    await pc.setRemoteDescription(RTCSessionDescription(oferta["sdp"], "offer"))
    await pc.setLocalDescription(await pc.createAnswer())
    resp = cifrar(chave, {"t": "answer", "sid": oferta["sid"], "sdp": pc.localDescription.sdp, "ts": time.time()})
    await loop.run_in_executor(None, lambda: urllib.request.urlopen(urllib.request.Request(f"{SINAL}/{topico}", data=resp.encode(), method="POST"), timeout=20).read())
    return pc


def _ouvir(loop, pcs):
    """Fica ouvindo o topico no ntfy (SSE) ate desligar; cada oferta valida vira uma conexao."""
    visto = set()
    while not _stop.is_set():
        try:
            chave, topico = chaves(codigo())
            req = urllib.request.Request(f"{SINAL}/{topico}/sse?since=1m", headers={"Accept": "text/event-stream"})
            with urllib.request.urlopen(req, timeout=90) as f:
                ESTADO["erro"] = ""
                for linha in f:
                    if _stop.is_set():
                        return
                    if not linha.startswith(b"data:"):
                        continue
                    try:
                        ev = json.loads(linha[5:])
                        o = decifrar(chave, ev.get("message", ""))
                    except Exception:
                        continue          # lixo ou cifrado com outro codigo: ignora
                    if o.get("t") != "offer" or o["sid"] in visto or abs(time.time() - o.get("ts", 0)) > 120:
                        continue
                    visto.add(o["sid"])
                    _tentou("celular pediu conexão")
                    fut = asyncio.run_coroutine_threadsafe(_atender_oferta(o, chave, topico), loop)
                    try:
                        pcs.append(fut.result(timeout=60))
                        _tentou("resposta enviada ao celular")
                    except Exception as e:
                        ESTADO["erro"] = "oferta: " + str(e)[:80]
                        _tentou("falhou: " + str(e)[:60])
        except Exception as e:
            if _stop.is_set():
                return
            ESTADO["erro"] = "sinalizacao: " + str(e)[:80]
            _stop.wait(5)


def _principal():
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    pcs = []
    try:
        _ouvir(loop, pcs)
    finally:
        for pc in pcs:
            asyncio.run_coroutine_threadsafe(pc.close(), loop)
        loop.call_soon_threadsafe(loop.stop)
        ESTADO.update(ligado=False, conectado=False)


def retomar():
    if _ler().get("ligado"):
        ligar()


def ligar(salvar=False):
    if salvar:
        _salvar({**_ler(), "ligado": True})
    if ESTADO["ligado"]:
        return estado()
    _stop.clear()
    ESTADO["ligado"] = True
    threading.Thread(target=_principal, daemon=True).start()
    return estado()


def desligar(salvar=False):
    if salvar:
        _salvar({**_ler(), "ligado": False})
    _stop.set()
    ESTADO.update(ligado=False, conectado=False)
    return estado()


def estado():
    return {**ESTADO, "codigo": formatar(codigo())}
