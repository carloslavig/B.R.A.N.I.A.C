# -*- coding: utf-8 -*-
"""Agente NANDO (28/10/2026, nome escolhido com o conselho): recebe vagas do Correio e do Garimpeiro, faz a triagem (remota? tem link?) e guarda a fila de candidaturas
em data/candidaturas.json. FASE 1: so triagem e relato (reuniao da manha). Ele NAO envia candidatura, NAO cria conta e NAO digita senha: tudo que exige isso fica
'aguardando_voce'. Reuniao, entrevista, teste, login ou captcha viram aviso imediato ao Dono. Nunca inventa experiencia do curriculo."""
import json
import re
import time

from .store import DATA

ARQ = DATA / "candidaturas.json"
REMOTA = re.compile(r"(?i)remot[oa]|home\s*office|trabalho\s+em\s+casa|anywhere|work\s+from\s+home|\bremote\b")
HUMANO = re.compile(r"(?i)entrevista|reuni[ãa]o|teste|desafio|case\b|v[ií]deo|agendar|call\b|interview|assessment|captcha|login|cadastro")
MAX = 200


def _ler():
    try:
        return json.loads(ARQ.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _gravar(itens):
    DATA.mkdir(exist_ok=True)
    ARQ.write_text(json.dumps(itens[-MAX:], ensure_ascii=False), encoding="utf-8")


def receber(origem, titulo, empresa="", link="", texto=""):
    """Entra uma vaga na fila. Devolve o item, ou None se ja estava (mesmo link ou mesmo titulo+empresa)."""
    itens = _ler()
    chave = (link or f"{titulo}|{empresa}").lower()
    if any(i["chave"] == chave for i in itens):
        return None
    alvo = f"{titulo} {empresa} {texto}"
    humano = bool(HUMANO.search(alvo))
    item = {"chave": chave, "origem": origem, "titulo": titulo[:120], "empresa": empresa[:60], "link": link, "ts": time.time(),
            "remota": True if origem == "Garimpeiro" else (True if REMOTA.search(alvo) else None),
            "status": "aguardando_voce" if humano else "triagem",
            "motivo": "o aviso fala de reunião/entrevista/teste/login: só você resolve" if humano else
                      ("sem link da vaga: preciso abrir o e-mail original" if not link else "tem link; falta você autorizar a inscrição"),
            "avisado": False}
    itens.append(item)
    _gravar(itens)
    try:
        from . import barramento
        barramento.enviar("Nando", "Jarvis", "status", f"nova vaga na fila ({origem}): {item['titulo'][:60]}")
    except Exception:
        pass
    return item


def relato(agora=None):
    """Para a reuniao da manha: o que entrou desde a ultima reuniao e o que depende de um humano. Marca como avisado."""
    itens = _ler()
    novos = [i for i in itens if not i["avisado"]]
    if not novos:
        return ""
    for i in novos:
        i["avisado"] = True
    _gravar(itens)
    humanos = [i for i in novos if i["status"] == "aguardando_voce" and HUMANO.search(i["motivo"] + i["titulo"])]
    f = [f"Entraram {len(novos)} vaga(s) na fila: " + "; ".join(f"{i['titulo'][:50]}" + (f" na {i['empresa'][:25]}" if i["empresa"] else "") for i in novos[:3]) + "."]
    if humanos:
        f.append("Atenção, precisa de você: " + "; ".join(i["titulo"][:50] for i in humanos[:3]) + " fala de reunião, entrevista, teste ou login.")
    f.append("Eu ainda não me inscrevo sozinho: me diga quais você quer e eu preparo a mensagem.")
    return " ".join(f)


def resumo():
    itens = _ler()
    por = {}
    for i in itens:
        por[i["status"]] = por.get(i["status"], 0) + 1
    return por


def registrar(status, titulo, empresa="", link="", motivo=""):
    """Cria ou atualiza a vaga na fila com o status final (ex.: 'enviada', 'pulada', 'aguardando_voce'); 'enviada' guarda ts_envio."""
    item = receber("Rotina", titulo, empresa, link) or next(
        (i for i in _ler() if i["chave"] == (link or f"{titulo}|{empresa}").lower()), None)
    itens = _ler()
    for i in itens:
        if item and i["chave"] == item["chave"]:
            i["status"], i["motivo"], i["avisado"] = status, motivo[:160], True
            if status == "enviada":
                i["ts_envio"] = time.time()
    _gravar(itens)


def enviadas_entre(ini, fim):
    return sum(1 for i in _ler() if i["status"] == "enviada" and ini <= i.get("ts_envio", 0) < fim)


if __name__ == "__main__":      # python -m braniac.candidaturas registrar enviada "titulo" "empresa" "link" ["motivo"]
    import sys
    if len(sys.argv) >= 4 and sys.argv[1] == "registrar":
        registrar(*sys.argv[2:7])
        print("registrado")
