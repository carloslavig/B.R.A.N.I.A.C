# -*- coding: utf-8 -*-
"""Cofre de chaves de API no Gerenciador de Credenciais do Windows (criptografado pelo Windows para o usuario atual).
As chaves NUNCA ficam em texto puro em arquivo, nunca vao para o repositorio e nunca saem do PC. Sem dependencias externas (ctypes)."""
import sys

PREFIXO = "BRANIAC/"
_TIPO_GENERICA = 1
_PERSISTE_PC = 2


class CofreErro(RuntimeError):
    pass


def _api():
    if sys.platform != "win32":
        raise CofreErro("o cofre usa o Gerenciador de Credenciais do Windows")
    import ctypes
    from ctypes import wintypes as wt

    class CRED(ctypes.Structure):
        _fields_ = [("Flags", wt.DWORD), ("Type", wt.DWORD), ("TargetName", wt.LPWSTR), ("Comment", wt.LPWSTR),
                    ("LastWritten", wt.FILETIME), ("CredentialBlobSize", wt.DWORD), ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                    ("Persist", wt.DWORD), ("AttributeCount", wt.DWORD), ("Attributes", ctypes.c_void_p),
                    ("TargetAlias", wt.LPWSTR), ("UserName", wt.LPWSTR)]
    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    adv.CredWriteW.argtypes = [ctypes.POINTER(CRED), wt.DWORD]
    adv.CredReadW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.POINTER(ctypes.POINTER(CRED))]
    adv.CredDeleteW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD]
    adv.CredFree.argtypes = [ctypes.c_void_p]
    return ctypes, CRED, adv


def guardar(provedor, chave):
    chave = (chave or "").strip()
    if not chave:
        raise CofreErro("chave vazia")
    ctypes, CRED, adv = _api()
    blob = chave.encode("utf-16-le")
    buf = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
    c = CRED()
    c.Type, c.TargetName, c.Persist = _TIPO_GENERICA, PREFIXO + provedor, _PERSISTE_PC
    c.CredentialBlobSize, c.CredentialBlob, c.UserName = len(blob), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)), "braniac"
    if not adv.CredWriteW(ctypes.byref(c), 0):
        raise CofreErro(f"nao consegui guardar a chave ({ctypes.get_last_error()})")


def ler(provedor):
    """Devolve a chave ou None."""
    ctypes, CRED, adv = _api()
    p = ctypes.POINTER(CRED)()
    if not adv.CredReadW(PREFIXO + provedor, _TIPO_GENERICA, 0, ctypes.byref(p)):
        return None
    try:
        c = p.contents
        return bytes(ctypes.string_at(c.CredentialBlob, c.CredentialBlobSize)).decode("utf-16-le")
    finally:
        adv.CredFree(p)


def remover(provedor):
    ctypes, CRED, adv = _api()
    return bool(adv.CredDeleteW(PREFIXO + provedor, _TIPO_GENERICA, 0))


def tem(provedor):
    return ler(provedor) is not None
