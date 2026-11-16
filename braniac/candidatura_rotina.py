# -*- coding: utf-8 -*-
"""Rotina de candidaturas (04/11/2026): 3 janelas por dia (manha, tarde, noite), ate META vagas em cada. Cada janela aciona o Claude com navegador, seguindo a
skill skills/candidatura-vagas (the Global Role + formularios Workable). O Claude registra cada vaga em candidaturas.py; aqui so se conta o que foi 'enviada'.
Nunca resolve captcha, nao cria conta, nao grava audio: o que exigir isso fica 'aguardando_voce' e vai no resumo."""
import json
import os
import threading
import time
from datetime import datetime

from .store import DATA

ARQ = DATA / "candidatura_rotina.json"
PAUSA = DATA / "candidatura_rotina.pausa"
META = 5
JANELAS = {"manha": (7, 12), "tarde": (12, 18), "noite": (18, 23)}
TENTATIVAS = 2          # por janela
ESPERA = 3600           # s entre tentativas da mesma janela
_rodando = threading.Event()


def janela(agora):
    return next((n for n, (a, b) in JANELAS.items() if a <= agora.hour < b), None)


def _ler():
    try:
        return json.loads(ARQ.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _inicio_janela(agora, nome):
    return agora.replace(hour=JANELAS[nome][0], minute=0, second=0, microsecond=0).timestamp()


def _prompt(nome, falta):
    return (f"Rotina de candidaturas, janela da {nome}. Siga a skill braniac/skills/candidatura-vagas/SKILL.md e as regras do CLAUDE.md. "
            f"Candidate o Dono a ate {falta} vaga(s) de desenvolvedor estagio/junior REMOTAS no theglobalrole.com (varie q: python, javascript, typescript, node, developer, "
            "software, suporte, QA; nivel 0 e 1), so se o CV cobrir o essencial (sem mentir) e sem audio/teste/presenca/residencia fora do Brasil. Pule vagas ja em data/candidaturas.json. "
            "Para cada vaga: python -m braniac.candidaturas registrar <enviada|pulada|aguardando_voce> \"titulo\" \"empresa\" \"link\" \"motivo\" (rode na pasta Agente). "
            "So registre 'enviada' quando a URL tiver ?success ou aparecer a mensagem de sucesso. Nunca clique em captcha. Termine com 1 linha: enviadas, puladas e o que depende do Dono.")


def tick(agora=None, enviar=None, rodar=None):
    """Chamado a cada ~10 min. Dispara a janela atual, em segundo plano, se ainda faltarem vagas e a espera passou. Devolve o nome da janela disparada ou None."""
    from . import candidaturas
    agora = agora or datetime.now()
    nome = janela(agora)
    if PAUSA.exists():      # pausa pedida pelo Dono: apague o arquivo para retomar
        return None
    if not nome or _rodando.is_set() or (rodar is None and "PYTEST_CURRENT_TEST" in os.environ):   # teste de outro modulo nunca aciona o Claude de verdade
        return None
    est = _ler()
    hoje = agora.strftime("%Y-%m-%d")
    j = est.setdefault(hoje, {}).setdefault(nome, {"tentativas": 0, "ultima": 0})
    ini = _inicio_janela(agora, nome)
    feitas = candidaturas.enviadas_entre(ini, ini + (JANELAS[nome][1] - JANELAS[nome][0]) * 3600)
    if feitas >= META or j["tentativas"] >= TENTATIVAS or time.time() - j["ultima"] < ESPERA:
        return None
    j["tentativas"] += 1
    j["ultima"] = time.time()
    est = {hoje: est[hoje]}          # guarda so o dia de hoje
    ARQ.parent.mkdir(exist_ok=True)
    ARQ.write_text(json.dumps(est), encoding="utf-8")
    if rodar is None:
        from . import agente_dev
        rodar = lambda p: agente_dev.rodar(p, workdir=DATA.parent.parent, timeout=2400, editar=True, navegador=True)

    def _trabalho():
        _rodando.set()
        try:
            cod, texto = rodar(_prompt(nome, META - feitas))
            total = candidaturas.enviadas_entre(ini, time.time() + 1)
            resumo = (texto or "").strip().splitlines()[-1][:300] if cod == 0 and (texto or "").strip() else f"não consegui rodar (código {cod})"
            if enviar:
                enviar(f"💼 Candidaturas da {nome}: {total} enviada(s) até agora. {resumo}")
        except Exception:
            pass
        finally:
            _rodando.clear()
    threading.Thread(target=_trabalho, daemon=True).start()
    return nome
