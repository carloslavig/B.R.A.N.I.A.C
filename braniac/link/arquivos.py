# -*- coding: utf-8 -*-
"""Transferencia de arquivos em blocos, com retomada e verificacao (SPEC.md secao 5). Quadro binario: fid(8) | indice(4) | hash16 do bloco | dados.
O recebido vai para a pasta de quarentena e NUNCA e aberto nem executado por aqui."""
import hashlib
import json
import re
import secrets
import struct
from pathlib import Path

BLOCO = 16 * 1024
MAX_TAMANHO = 2 * 1024 ** 3
CAB = 8 + 4 + 16
PERIGOSOS = {".exe", ".bat", ".cmd", ".ps1", ".vbs", ".js", ".msi", ".scr", ".lnk", ".com", ".sh", ".jar", ".dll"}


class ArquivoErro(ValueError):
    pass


def _h(dados):
    return hashlib.blake2b(dados, digest_size=16).digest()


def nome_seguro(nome):
    base = re.sub(r"[^\w.\- ]", "_", Path(str(nome).replace("\\", "/")).name).strip(" .") or "arquivo"
    return base[:120]


class Envio:
    def __init__(self, caminho, bloco=BLOCO):
        self.caminho, self.bloco = Path(caminho), bloco
        self.tam = self.caminho.stat().st_size
        if self.tam > MAX_TAMANHO:
            raise ArquivoErro("arquivo maior que o limite")
        h = hashlib.blake2b(digest_size=32)
        with self.caminho.open("rb") as f:
            for parte in iter(lambda: f.read(1024 * 1024), b""):
                h.update(parte)
        self.hash, self.fid = h.hexdigest(), secrets.token_bytes(8)
        self.blocos = max(1, -(-self.tam // bloco))

    def oferta(self):
        return {"fid": self.fid.hex(), "nome": nome_seguro(self.caminho.name), "tam": self.tam, "bloco": self.bloco, "blocos": self.blocos, "hash": self.hash}

    def quadro(self, i):
        with self.caminho.open("rb") as f:
            f.seek(i * self.bloco)
            dados = f.read(self.bloco)
        return self.fid + struct.pack(">I", i) + _h(dados) + dados


class Recebimento:
    """Pasta/<fid>.parcial + <fid>.estado.json (indices ja recebidos): se a conexao cair, criar de novo com a mesma oferta e pedir faltando()."""

    def __init__(self, pasta, oferta):
        try:
            self.fid, self.tam, self.bloco, self.blocos, self.hash = str(oferta["fid"]), int(oferta["tam"]), int(oferta["bloco"]), int(oferta["blocos"]), str(oferta["hash"])
            self.nome = nome_seguro(oferta["nome"])
        except (KeyError, TypeError, ValueError):
            raise ArquivoErro("oferta invalida")
        if not re.fullmatch(r"[0-9a-f]{16}", self.fid) or not 0 <= self.tam <= MAX_TAMANHO or not 1024 <= self.bloco <= 1024 * 1024 \
                or self.blocos != max(1, -(-self.tam // self.bloco)) or not re.fullmatch(r"[0-9a-f]{64}", self.hash):
            raise ArquivoErro("oferta com numeros invalidos")
        self.pasta = Path(pasta)
        self.pasta.mkdir(parents=True, exist_ok=True)
        self.parcial, self.estado = self.pasta / f"{self.fid}.parcial", self.pasta / f"{self.fid}.estado.json"
        try:
            self.tenho = {int(i) for i in json.loads(self.estado.read_text(encoding="utf-8"))}
        except (OSError, ValueError):
            self.tenho = set()
        if not self.parcial.exists():
            self.parcial.write_bytes(b"")
            self.tenho = set()

    def receber(self, quadro):
        if len(quadro) < CAB or bytes(quadro[:8]).hex() != self.fid:
            raise ArquivoErro("quadro de outro arquivo")
        i = struct.unpack(">I", quadro[8:12])[0]
        dados = bytes(quadro[CAB:])
        esperado = self.bloco if i < self.blocos - 1 else self.tam - self.bloco * (self.blocos - 1)
        if i >= self.blocos or len(dados) != esperado or _h(dados) != bytes(quadro[12:CAB]):
            raise ArquivoErro(f"bloco {i} corrompido ou fora do esperado")
        with self.parcial.open("r+b") as f:
            f.seek(i * self.bloco)
            f.write(dados)
        self.tenho.add(i)
        if len(self.tenho) % 64 == 0 or len(self.tenho) == self.blocos:
            self.estado.write_text(json.dumps(sorted(self.tenho)), encoding="utf-8")
        return i

    def faltando(self):
        return [i for i in range(self.blocos) if i not in self.tenho]

    def finalizar(self):
        """Confere o hash do arquivo inteiro e solta o nome final (sem sobrescrever). Devolve o caminho."""
        if self.faltando():
            raise ArquivoErro("ainda faltam blocos")
        h = hashlib.blake2b(digest_size=32)
        with self.parcial.open("rb") as f:
            for parte in iter(lambda: f.read(1024 * 1024), b""):
                h.update(parte)
        if h.hexdigest() != self.hash:
            self.parcial.unlink(missing_ok=True)
            self.estado.unlink(missing_ok=True)
            raise ArquivoErro("hash final nao confere: arquivo descartado")
        destino = self.pasta / self.nome
        n = 1
        while destino.exists():
            destino = self.pasta / f"{Path(self.nome).stem}-{n}{Path(self.nome).suffix}"
            n += 1
        if destino.suffix.lower() in PERIGOSOS:
            destino = destino.with_name(destino.name + ".recebido")
        self.parcial.replace(destino)
        self.estado.unlink(missing_ok=True)
        return destino
