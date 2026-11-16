# -*- coding: utf-8 -*-
"""Identidade criptografica do dispositivo: par Ed25519 gerado uma vez. id = 'bl1-' + 20 hex do SHA-256 da chave publica.
A chave privada fica em disco (protegida pelo cofre do sistema quando houver `protetor`, senao arquivo 0600)."""
import base64
import hashlib
import os
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

_RAW = dict(encoding=serialization.Encoding.Raw)


def b64(b):
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def unb64(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def id_de(pub_b64):
    return "bl1-" + hashlib.sha256(unb64(pub_b64)).hexdigest()[:20]


def verificar(pub_b64, dados, sig_b64):
    try:
        Ed25519PublicKey.from_public_bytes(unb64(pub_b64)).verify(unb64(sig_b64), dados)
        return True
    except (InvalidSignature, ValueError):
        return False


class Identidade:
    def __init__(self, pasta, nome="", protetor=None, revelador=None):
        """protetor/revelador: funcoes str->str opcionais (ex.: segredos.proteger/revelar) para guardar a chave cifrada."""
        self.pasta = Path(pasta)
        self.pasta.mkdir(parents=True, exist_ok=True)
        self.arq = self.pasta / "chave.ed25519"
        self.nome = nome
        self._rev = revelador or (lambda s: s)
        prot = protetor or (lambda s: s)
        if self.arq.exists():
            raw = unb64(self._rev(self.arq.read_text(encoding="ascii").strip()))
            self._chave = Ed25519PrivateKey.from_private_bytes(raw)
        else:
            self._chave = Ed25519PrivateKey.generate()
            raw = self._chave.private_bytes(encoding=serialization.Encoding.Raw, format=serialization.PrivateFormat.Raw,
                                            encryption_algorithm=serialization.NoEncryption())
            self.arq.write_text(prot(b64(raw)), encoding="ascii")
            try:
                os.chmod(self.arq, 0o600)
            except OSError:
                pass
        self.pub = b64(self._chave.public_key().public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw))
        self.id = id_de(self.pub)

    def assinar(self, dados):
        return b64(self._chave.sign(dados))
