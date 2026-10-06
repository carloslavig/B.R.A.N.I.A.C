# -*- coding: utf-8 -*-
"""Perfil local da pessoa (JSON em %LOCALAPPDATA%\\BRANIAC\\perfil.json). Nunca sai do PC."""
import json, time
from . import paths

PADRAO = {
    "versao": 1,
    "nome_assistente": None,         # escolhido na instalacao (obrigatorio)
    "voz": None,                     # 'feminina' | 'masculina' (obrigatorio)
    "nome_pessoa": None,
    "modo_icone": "bandeja",         # 'bandeja' (junto dos icones do relogio) | 'flutuante' (solto na tela)
    "integracoes": [],               # o que a pessoa quer que o assistente use: email, spotify, whatsapp...
    "consentimento_acesso_pc": None, # 'total' | 'granular' | 'nenhum'  (+ data em consentimento_em)
    "consentimento_em": None,
    "voz_nome": None,                # voz escolhida do Gemini (ex.: Kore, Achird)
    "voz_estilo": "calmo",           # calmo | profissional | animado
    "voz_privada": False,            # True = nunca manda texto para gerar voz na nuvem (usa so a voz do sistema)
    "etapa": "boas_vindas",
    "concluido": False,
}


def _arq():
    return paths.arquivo("perfil.json")


def carregar():
    try:
        d = json.loads(_arq().read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        d = {}
    return {**PADRAO, **d}


def salvar(d):
    _arq().write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    return d


def atualizar(**campos):
    d = carregar()
    d.update(campos)
    return salvar(d)


def registrar_consentimento(modo):
    if modo not in ("total", "granular", "nenhum"):
        raise ValueError("modo de consentimento invalido")
    return atualizar(consentimento_acesso_pc=modo, consentimento_em=time.strftime("%Y-%m-%d %H:%M:%S"))
