# -*- coding: utf-8 -*-
"""ESCALADA DO AIRBNB (28/10/2026, pedido do Dono). Funciona mesmo com o atendimento automatico desligado: so LE a caixa de entrada.
Pendencia = (a) pedido/consulta de reserva ainda nao aceito -> escala na hora (Mae -> Dono -> Parceira -> repete, ate 1 h);
(b) 16/11 (pedido do Dono): mensagem de hospede sem resposta ha 30 min -> Mae E Dono juntos (hospede, anuncio, resumo);
continua sem resposta -> UM lembrete 30 min depois e para. Nao passa pelo funil (whatsapp.enviar direto): sai de dia e de noite.
Fora do escopo por enquanto: reserva JA aceita perto do check-in (20 min / 2 min) -- precisa ler datas da reserva."""
import json
import re
import threading
import time

from . import airbnb, power
from .store import DATA

ARQ = DATA / "airbnb_escalada.json"
LOG = DATA / "airbnb.log"
INTERVALO_S = 15 * 60   # 05/11: no maximo 1 aviso a cada 15 min por hospede (pedido do Dono)
ESPERA_MENSAGEM_S, LEMBRETE_MENSAGEM_S = 1800, 1800   # 16/11: mensagem de hospede -> aviso aos 30 min, 1 lembrete aos 60
ENTRE_MAE_E_DONO_S, ENTRE_DONO_E_PARCEIRA_S, REPETE_S = INTERVALO_S, INTERVALO_S, INTERVALO_S
JANELA_S = 3600   # 03/11: passada 1 h da primeira pendencia a escalada para (pre-reserva nao aceita gerou 700+ avisos na madrugada; risco de bloqueio da Meta)
RESERVA_PENDENTE = re.compile(r"Pedido de reserva|Consulta de reserva|Reserva pendente", re.I)
# 05/11: avisos do proprio Airbnb e reservas ja decididas NAO esperam resposta
PREVIA_RESOLVIDA = re.compile(
    r"pr[eé]-?aprova[cç][aã]o (?:expirou|enviada|foi enviada)|(?:pedido|convite|reserva|solicita[cç][aã]o)[^.]{0,30}(?:expirou|foi (?:cancelad|aceit|recusad|confirmad|retirad|removid))|"
    r"reserva (?:confirmada|aceita)|mensagem foi cancelada|uma mensagem foi", re.I)
STATUS_RESOLVIDO = re.compile(r"^\s*(?:cancelad|expirad|recusad|negad|confirmad|conclu[ií]d|declinad)", re.I)


def ja_resolvido(l):
    """05/11: aviso automatico do Airbnb ou reserva ja decidida (expirou, cancelou, aceitamos, pre-aprovacao enviada) NAO espera resposta.
    Texto livre do hospede ('aceita pet?', 'quero cancelar') nao cai aqui: so frases de sistema e o status da conversa."""
    return bool(PREVIA_RESOLVIDA.search(l.get("previa") or "") or STATUS_RESOLVIDO.search(l.get("meta") or ""))



def _log(t):
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%d/%m %H:%M:%S')} | escalada | {t}\n")
    except OSError:
        pass


def _carregar():
    try:
        return json.loads(ARQ.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def pendencias(linhas):
    """{id: {tipo, hospede}} a partir das linhas da caixa de entrada (ja interpretadas por airbnb.parse_linha)."""
    from . import airbnb_vigia, contexto
    p = {}
    for l in linhas:
        if l.get("suporte_airbnb"):
            continue
        idade = airbnb_vigia.idade_horas(l.get("quando"))
        if idade is None or idade > 24 or contexto.encerramento(l.get("previa") or "") or ja_resolvido(l):
            continue                      # antiga, so 'ok/obrigado' ou ja resolvida (expirou/cancelou/aceita): nao acorda a familia
        if RESERVA_PENDENTE.search(l.get("previa") or "") and "aceit" not in (l.get("previa") or "").lower():
            p[l["id"]] = {"tipo": "reserva", "hospede": l["hospede"], "sig": f"{l.get('previa')}|{l.get('quando')}"}
        elif airbnb.pendente_de_resposta(l):
            p[l["id"]] = {"tipo": "mensagem", "hospede": l["hospede"], "anuncio": l.get("anuncio") or "", "previa": l.get("previa") or "",
                          "sig": f"{l.get('previa')}|{l.get('quando')}"}
    return p


def _resumo(t, n=140):
    t = re.sub(r"\d[\d .\-/]{9,}\d", "[número]", " ".join((t or "").split()))   # nunca repassa cartao/CPF/conta que o hospede digitou
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "…"


def _texto_mensagem(quem, p, minutos, lembrete):
    h, an, q = p["hospede"], p.get("anuncio") or "", _resumo(p.get("previa"))
    onde = f" ({an})" if an else ""
    perg = f' Ele perguntou: "{q}"' if q else ""
    if quem == "mae":
        return (f"oh minha tia, {'ainda ' if lembrete else ''}ninguém respondeu o hóspede {h} no Airbnb{onde}, já faz {minutos} min.{perg} "
                f"Vê se consegue olhar pra mim?")
    return (f"Senhor, {'lembrete: ' if lembrete else ''}o hóspede {h} está há {minutos} min sem resposta no Airbnb{onde}.{perg} "
            f"Avisei a Mãe também.")


def _texto(quem, p, minutos):
    h, reserva = p["hospede"], p["tipo"] == "reserva"
    if quem == "mae":
        return (f"oh minha tia, tem um pedido de reserva do {h} no Airbnb esperando resposta, vê se consegue olhar pra mim?" if reserva
                else f"oh minha tia, o hóspede {h} mandou mensagem no Airbnb e ainda não foi respondido, vê se consegue olhar pra mim?")
    if quem == "parceira":
        return (f"Parceira, aqui é o Jarvis, assistente de IA do Dono. Tem {'um pedido de reserva' if reserva else 'uma mensagem'} do {h} no Airbnb "
                f"parada há {minutos} min e ninguém respondeu, nem a Mãe nem o Dono. Consegue olhar?")
    return (f"Dono, {'pedido de reserva' if reserva else 'mensagem'} do {h} no Airbnb sem resposta há {minutos} min "
            f"(já avisei a Mãe). Preciso do seu OK/resposta.")


def passo(pend, vistos, agora, enviar, destinos):
    """Avanca a escalada. pend={id:{tipo,hospede}}, vistos=ids lidos agora (so estes podem ser dados como resolvidos),
    enviar(nome_whatsapp, texto), destinos={'mae','dono','parceira'}->nome. Devolve o estado."""
    st = _carregar()
    ok = st.setdefault("_ok", {})                 # {id: assinatura da mensagem que o Dono disse ja ter respondido}
    for tid, p in list(pend.items()):
        if ok.get(tid) == "*":
            ok[tid] = p.get("sig")                    # 'ja respondi' vale para a mensagem que esta na caixa agora
        if ok.get(tid) is not None and ok.get(tid) == p.get("sig"):
            pend = {k: v for k, v in pend.items() if k != tid}
            st.pop(tid, None)
    for tid in [t for t in st if t != "_ok" and t in vistos and t not in pend]:
        _log(f"{st[tid]['hospede']} resolvida")
        del st[tid]
    for tid, p in pend.items():
        e = st.setdefault(tid, {"t0": agora, "etapa": 0, "ult": 0, **p})
        mins = int((agora - e["t0"]) / 60)

        def mandar(quem):
            nome = destinos.get(quem)
            if nome:
                try:
                    enviar(nome, _texto(quem, p, mins))
                    _log(f"{p['hospede']} -> {quem}")
                except Exception as ex:
                    _log(f"falha ao avisar {quem}: {ex!r}")
        if e["etapa"] == 4:
            continue
        if p["tipo"] == "mensagem":       # 16/11: 30 min -> Mae + Dono; 1 lembrete 30 min depois; e para
            if e["etapa"] == 0 and agora - e["t0"] >= ESPERA_MENSAGEM_S:
                lembrete = False
            elif e["etapa"] == 1 and agora - e["ult"] >= LEMBRETE_MENSAGEM_S:
                lembrete = True
            else:
                continue
            for quem in ("mae", "dono"):
                nome = destinos.get(quem)
                if nome:
                    try:
                        enviar(nome, _texto_mensagem(quem, p, mins, lembrete))
                        _log(f"{p['hospede']} -> {quem}{' (lembrete)' if lembrete else ''}")
                    except Exception as ex:
                        _log(f"falha ao avisar {quem}: {ex!r}")
            e["etapa"], e["ult"] = (4 if lembrete else 1), agora
            continue
        if agora - e["t0"] > JANELA_S:
            e["etapa"] = 4                # encerrada: o registro fica ate a pendencia sumir, para nao recomecar do zero
            _log(f"{p['hospede']} sem resposta ha mais de 1 h: parei de avisar")
            continue
        if e["etapa"] == 0 and agora - e["t0"] >= (0 if p["tipo"] == "reserva" else ESPERA_MENSAGEM_S):
            mandar("mae"); e["etapa"], e["ult"] = 1, agora
        elif e["etapa"] == 1 and agora - e["ult"] >= ENTRE_MAE_E_DONO_S:
            mandar("dono"); e["etapa"], e["ult"] = 2, agora
        elif e["etapa"] == 2 and agora - e["ult"] >= ENTRE_DONO_E_PARCEIRA_S:
            mandar("parceira"); e["etapa"], e["ult"] = 3, agora
        elif e["etapa"] == 3 and agora - e["ult"] >= REPETE_S:
            mandar("mae"); mandar("dono"); e["ult"] = agora
    DATA.mkdir(exist_ok=True)
    ARQ.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    return st


def _destinos():
    from . import contexto
    return {"mae": contexto.contato("mae"), "dono": contexto.contato("dono"), "parceira": contexto.contato("parceira")}


def _enviar(nome, texto):
    from . import whatsapp
    with whatsapp.LOCK:
        whatsapp.enviar(nome, texto)


def iniciar():
    """Thread: le a caixa a cada 60 s (30 s com escalada ativa) e avanca a escalada. So le; nunca responde hospede."""
    def loop():
        espera = 60
        while True:
            time.sleep(espera)
            try:
                if power.pausado():
                    continue
                with airbnb.AB() as ab:
                    linhas = ab.conversas(25)
                st = passo(pendencias(linhas), {l["id"] for l in linhas}, time.time(), _enviar, _destinos())
                espera = 30 if any(k != "_ok" for k in st) else 60
            except airbnb.AirbnbIndisponivel:
                espera = 300
            except Exception as e:
                _log(f"erro: {e!r}")
                espera = 120
    threading.Thread(target=loop, daemon=True, name="airbnb-escalada").start()


def reconhecer(texto):
    """O Dono disse 'ja respondi' (28/10). Marca como resolvidas as pendencias citadas pelo nome (ou todas as ativas, se nao citou ninguem) ate chegar mensagem NOVA do hospede.
    Devolve a resposta ao Dono, ou None se nao ha nada ativo (a frase segue o caminho normal)."""
    st = _carregar()
    ativos = {t: e for t, e in st.items() if t != "_ok"}
    if not ativos:
        return None
    t = (texto or "").lower()
    alvo = {i: e for i, e in ativos.items() if e["hospede"].split()[0].lower() in t} or ativos
    ok = st.setdefault("_ok", {})
    for i in alvo:
        ok[i] = "*"
        st.pop(i, None)
    ARQ.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    nomes = ", ".join(e["hospede"] for e in alvo.values())
    _log(f"Dono disse que ja respondeu: {nomes}")
    return f"Anotado: marquei {nomes} como já respondido(s) no Airbnb. Não aviso mais até chegar mensagem nova."
