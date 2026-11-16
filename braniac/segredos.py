# -*- coding: utf-8 -*-
"""CHAVES CRIPTOGRAFADAS NO braniac/.env (pedido do Dono, 14/10/2026).
Usa o DPAPI do Windows (CryptProtectData): so a conta do Windows do Dono, neste PC, consegue abrir. Sem senha mestra nem arquivo de chave.
No .env a linha fica  NOME=dpapi:<base64>.  Chave nova colada em texto puro e criptografada sozinha na proxima leitura do .env.
Uso manual:  python -m braniac.segredos   (criptografa o que estiver em texto puro; nunca imprime valores)."""
import base64
import ctypes
import ctypes.wintypes as wt
import os
import re
from pathlib import Path

PREFIXO = "dpapi:"
ENTROPIA = b"braniac-dono"      # amarra o segredo a este programa (outro programa da mesma conta precisa saber disto)
SEGREDO = re.compile(r"(KEY|TOKEN|SECRET|SENHA|PASSWORD|CHAVE|USER_ID)", re.I)


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(dados):
    buf = ctypes.create_string_buffer(dados, len(dados))
    return _Blob(len(dados), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


def _chamar(func, dados):
    entrada, _b1 = _blob(dados)
    entropia, _b2 = _blob(ENTROPIA)
    saida = _Blob()
    if not func(ctypes.byref(entrada), None, ctypes.byref(entropia), None, None, 0x1, ctypes.byref(saida)):   # 0x1 = sem janela (UI_FORBIDDEN)
        raise OSError(f"DPAPI falhou ({ctypes.GetLastError()})")
    try:
        return ctypes.string_at(saida.pbData, saida.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(saida.pbData)


def proteger(texto):
    if texto.startswith(PREFIXO):
        return texto
    cifrado = _chamar(ctypes.windll.crypt32.CryptProtectData, texto.encode("utf-8"))
    return PREFIXO + base64.b64encode(cifrado).decode("ascii")


def revelar(valor):
    if not valor.startswith(PREFIXO):
        return valor
    return _chamar(ctypes.windll.crypt32.CryptUnprotectData, base64.b64decode(valor[len(PREFIXO):])).decode("utf-8")


def ler_env(path):
    """{nome: valor ABERTO}. Linhas de segredo em texto puro sao criptografadas no arquivo (com verificacao antes de gravar)."""
    p = Path(path)
    if not p.exists():
        return {}
    linhas = p.read_text(encoding="utf-8-sig").splitlines()
    valores, novas, mudou = {}, [], False
    for linha in linhas:
        s = linha.strip()
        if not s or s.startswith("#") or "=" not in s:
            novas.append(linha)
            continue
        k, v = s.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        aberto = revelar(v)
        valores[k] = aberto
        if v and not v.startswith(PREFIXO) and SEGREDO.search(k) and os.name == "nt":
            cifrado = proteger(v)
            if revelar(cifrado) == v:              # so troca se abrir de volta igual
                novas.append(f"{k}={cifrado}")
                mudou = True
                continue
        novas.append(linha)
    if mudou:
        tmp = p.with_suffix(".env.tmp")
        tmp.write_text("\n".join(novas) + "\n", encoding="utf-8")
        tmp.replace(p)
    return valores


if __name__ == "__main__":
    arq = Path(__file__).resolve().parent / ".env"
    antes = arq.read_text(encoding="utf-8-sig") if arq.exists() else ""
    vals = ler_env(arq)
    depois = arq.read_text(encoding="utf-8-sig") if arq.exists() else ""
    protegidas = sum(1 for l in depois.splitlines() if "=" + PREFIXO in l)
    print(f"{len(vals)} variáveis lidas; {protegidas} criptografadas; {'arquivo atualizado' if antes != depois else 'nada a mudar'}.")
