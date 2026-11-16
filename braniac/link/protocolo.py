# -*- coding: utf-8 -*-
"""Envelope do BRANIAC LINK (ver SPEC.md): JSON assinado pelo dispositivo. Tudo que chega e dado nao confiavel: validar() antes de qualquer uso."""
import json
import time
import uuid

from . import VERSAO_PROTOCOLO
from .identidade import Identidade, id_de, verificar

TIPOS = {"hello", "ping", "pong", "msg", "caps.pedir", "caps", "tarefa.pedido", "tarefa.aceita", "tarefa.pendente", "tarefa.recusada",
         "tarefa.resultado", "arquivo.oferta", "arquivo.aceita", "arquivo.recusa", "arquivo.fim", "arquivo.ok", "arquivo.falta", "bye"}
MAX_ENVELOPE = 64 * 1024
TOLERANCIA_S = 300


class ProtocoloErro(ValueError):
    pass


def _canonico(env):
    return json.dumps({k: v for k, v in env.items() if k != "sig"}, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def criar(ident, tipo, corpo=None, para="", ref=""):
    if tipo not in TIPOS:
        raise ProtocoloErro("tipo desconhecido: " + tipo)
    env = {"link": VERSAO_PROTOCOLO, "tipo": tipo, "id": uuid.uuid4().hex[:16], "de": ident.id, "pub": ident.pub, "para": para, "ref": ref,
           "ts": int(time.time()), "corpo": corpo or {}}
    env["sig"] = ident.assinar(_canonico(env))
    return json.dumps(env, ensure_ascii=False)


class Antirepeticao:
    """Lembra os ids vistos na janela de tolerancia: reenviar o mesmo envelope e rejeitado."""
    def __init__(self):
        self._vistos = {}

    def novo(self, env_id, agora=None):
        agora = agora or time.time()
        self._vistos = {k: t for k, t in self._vistos.items() if agora - t < 2 * TOLERANCIA_S}
        if env_id in self._vistos:
            return False
        self._vistos[env_id] = agora
        return True


def validar(texto, anti=None, agora=None):
    """texto JSON -> dict do envelope, com a assinatura, o id e a data conferidos. Levanta ProtocoloErro se algo nao fecha."""
    if not isinstance(texto, (str, bytes)) or len(texto) > MAX_ENVELOPE:
        raise ProtocoloErro("envelope grande demais ou invalido")
    try:
        env = json.loads(texto)
    except ValueError:
        raise ProtocoloErro("nao e JSON")
    if not isinstance(env, dict) or env.get("link") != VERSAO_PROTOCOLO:
        raise ProtocoloErro("versao do protocolo nao suportada")
    if env.get("tipo") not in TIPOS or not isinstance(env.get("corpo"), dict):
        raise ProtocoloErro("tipo ou corpo invalido")
    for campo in ("id", "de", "pub", "sig"):
        if not isinstance(env.get(campo), str) or not env[campo]:
            raise ProtocoloErro("falta " + campo)
    try:
        if id_de(env["pub"]) != env["de"] or not verificar(env["pub"], _canonico(env), env["sig"]):
            raise ProtocoloErro("assinatura ou identidade nao confere")
    except ValueError:
        raise ProtocoloErro("chave invalida")
    agora = agora or time.time()
    if not isinstance(env.get("ts"), int) or abs(agora - env["ts"]) > TOLERANCIA_S:
        raise ProtocoloErro("data fora da tolerancia")
    if anti is not None and not anti.novo(env["id"], agora):
        raise ProtocoloErro("envelope repetido")
    return env
