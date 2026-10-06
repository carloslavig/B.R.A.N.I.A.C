# -*- coding: utf-8 -*-
"""Roteiro da instalacao (primeiro uso). Cada etapa grava o progresso no perfil local: se fechar no meio, continua de onde parou.

  1 boas_vindas  2 consentimento (acesso ao PC: total / granular / nenhum)  3 hardware  4 chaves de API (>= 1 obrigatoria)
  5 ias_nuvem (ChatGPT e Gemini: a pessoa entra na propria conta)  6 reuniao das IAs (perfil da pessoa -> banco local)
  7 nome e voz (obrigatorios)  8 integracoes (e-mail, Spotify...)  9 icone (bandeja ou flutuante)  10 concluido
"""
from . import hardware, nomes, perfil, permissoes, provedores

ETAPAS = ["boas_vindas", "consentimento", "hardware", "chaves", "ias_nuvem", "reuniao_inicial", "nome_voz", "integracoes", "icone", "concluido"]
INTEGRACOES = ["email", "spotify", "whatsapp", "agenda", "arquivos"]


class Pendencia(Exception):
    pass


def etapa_atual():
    return perfil.carregar()["etapa"]


def _ir_para(etapa):
    perfil.atualizar(etapa=etapa)
    return etapa


def proxima():
    i = ETAPAS.index(etapa_atual())
    return _ir_para(ETAPAS[min(i + 1, len(ETAPAS) - 1)])


def consentimento(modo):
    """modo: total | basico | granular | nenhum. Recusar e valido: o assistente so conversa e nada do PC e liberado."""
    permissoes.aplicar_modo(modo)
    return proxima()


def hardware_recomendado(info=None):
    perf, motivo = hardware.recomendar(info or hardware.detectar())
    perfil.atualizar(perfil_ia=perf)
    return perf, motivo, hardware.PERFIS[perf]


def chaves_ok(chaves=None):
    return len(chaves if chaves is not None else provedores.chaves_validas()) >= 1


def definir_nome_voz(nome, voz):
    ok, motivo = nomes.validar_nome(nome)
    if not ok:
        raise Pendencia(motivo)
    if voz not in nomes.VOZES:
        raise Pendencia("escolha se a voz do assistente será feminina ou masculina")
    perfil.atualizar(nome_assistente=nome.strip(), voz=voz, frase_acordar=nomes.frase_de_acordar(nome))


def definir_integracoes(lista):
    ruins = [x for x in lista if x not in INTEGRACOES]
    if ruins:
        raise Pendencia(f"integração desconhecida: {', '.join(ruins)}")
    perfil.atualizar(integracoes=list(lista))


def definir_icone(modo):
    if modo not in ("bandeja", "flutuante"):
        raise Pendencia("o ícone fica na bandeja ou flutuante")
    perfil.atualizar(modo_icone=modo)


def faltando(chaves=None):
    """Lista do que ainda impede de concluir (vazia = pode concluir)."""
    p = perfil.carregar()
    f = []
    if not p["consentimento_acesso_pc"]:
        f.append("escolher o nível de acesso ao PC (pode ser nenhum)")
    if not chaves_ok(chaves):
        f.append("informar pelo menos uma chave de API válida")
    if not p["nome_assistente"] or not p["voz"]:
        f.append("escolher o nome e a voz do assistente")
    return f


def concluir(chaves=None):
    f = faltando(chaves)
    if f:
        raise Pendencia("Ainda falta: " + "; ".join(f))
    perfil.atualizar(concluido=True, etapa="concluido")
