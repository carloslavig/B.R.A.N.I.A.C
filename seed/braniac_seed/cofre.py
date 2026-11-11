# -*- coding: utf-8 -*-
"""Cofre de chaves de API: Gerenciador de Credenciais do Windows ou Chaves (Keychain) do macOS, criptografados pelo sistema para o usuario atual.
As chaves NUNCA ficam em texto puro em arquivo, nunca vao para o repositorio e nunca saem do PC. Sem dependencias externas (ctypes)."""
import sys

PREFIXO = "BRANIAC/"
_TIPO_GENERICA = 1
_PERSISTE_PC = 2
_CONTA_MAC = "braniac"
_NAO_ACHOU_MAC = -25300     # errSecItemNotFound


class CofreErro(RuntimeError):
    pass


def _mac():
    """Security.framework via ctypes (a chave vai por memoria, nunca como argumento de linha de comando, onde `ps` a mostraria)."""
    import ctypes
    sec = ctypes.CDLL("/System/Library/Frameworks/Security.framework/Security")
    cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
    u32, vp, cp = ctypes.c_uint32, ctypes.c_void_p, ctypes.c_char_p
    sec.SecKeychainFindGenericPassword.argtypes = [vp, u32, cp, u32, cp, ctypes.POINTER(u32), ctypes.POINTER(vp), ctypes.POINTER(vp)]
    sec.SecKeychainAddGenericPassword.argtypes = [vp, u32, cp, u32, cp, u32, cp, ctypes.POINTER(vp)]
    sec.SecKeychainItemModifyAttributesAndData.argtypes = [vp, vp, u32, cp]
    sec.SecKeychainItemFreeContent.argtypes = [vp, vp]
    sec.SecKeychainItemDelete.argtypes = [vp]
    cf.CFRelease.argtypes = [vp]
    for f in (sec.SecKeychainFindGenericPassword, sec.SecKeychainAddGenericPassword, sec.SecKeychainItemModifyAttributesAndData, sec.SecKeychainItemDelete):
        f.restype = ctypes.c_int32
    return ctypes, sec, cf


def _mac_achar(provedor):
    """(status, item, dados_bytes|None). Quem chama libera o item com CFRelease."""
    ctypes, sec, cf = _mac()
    srv, conta = (PREFIXO + provedor).encode(), _CONTA_MAC.encode()
    n, dados, item = ctypes.c_uint32(0), ctypes.c_void_p(), ctypes.c_void_p()
    st = sec.SecKeychainFindGenericPassword(None, len(srv), srv, len(conta), conta, ctypes.byref(n), ctypes.byref(dados), ctypes.byref(item))
    if st != 0:
        return st, None, None
    try:
        return 0, item, ctypes.string_at(dados, n.value)
    finally:
        sec.SecKeychainItemFreeContent(None, dados)


def _mac_guardar(provedor, chave):
    ctypes, sec, cf = _mac()
    st, item, _ = _mac_achar(provedor)
    blob = chave.encode("utf-8")
    if st == 0:
        try:
            st = sec.SecKeychainItemModifyAttributesAndData(item, None, len(blob), blob)
        finally:
            cf.CFRelease(item)
    elif st == _NAO_ACHOU_MAC:
        srv, conta = (PREFIXO + provedor).encode(), _CONTA_MAC.encode()
        st = sec.SecKeychainAddGenericPassword(None, len(srv), srv, len(conta), conta, len(blob), blob, None)
    if st != 0:
        raise CofreErro(f"nao consegui guardar a chave no Keychain ({st})")


def _mac_ler(provedor):
    ctypes, sec, cf = _mac()
    st, item, dados = _mac_achar(provedor)
    if st != 0:
        return None
    cf.CFRelease(item)
    return dados.decode("utf-8")


def _mac_remover(provedor):
    ctypes, sec, cf = _mac()
    st, item, _ = _mac_achar(provedor)
    if st != 0:
        return False
    try:
        return sec.SecKeychainItemDelete(item) == 0
    finally:
        cf.CFRelease(item)


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
    if sys.platform == "darwin":
        return _mac_guardar(provedor, chave)
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
    if sys.platform == "darwin":
        return _mac_ler(provedor)
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
    if sys.platform == "darwin":
        return _mac_remover(provedor)
    ctypes, CRED, adv = _api()
    return bool(adv.CredDeleteW(PREFIXO + provedor, _TIPO_GENERICA, 0))


def tem(provedor):
    return ler(provedor) is not None
