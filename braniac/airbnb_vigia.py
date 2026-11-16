# -*- coding: utf-8 -*-
"""ATENDIMENTO AUTOMATICO DO AIRBNB: olha a caixa de entrada do anfitriao e responde hospedes que ficaram sem resposta, com as MESMAS
decisoes e travas do WhatsApp (protocolo JV1: o Claude decide E/I/A/P; auditoria e revisao antes de agir).

TRAVAS:
- padrao DESLIGADO; so a interface local liga (de fora so se consegue desligar);
- so responde quando a ULTIMA mensagem da conversa e do hospede; ignora o suporte do Airbnb e conversas antigas;
- janela de horario, limites por conversa/hora, total/hora e total/dia, no maximo 3 conversas por ciclo;
- nunca fala de valores em reais, links, Pix, senha ou cartao (validar_resposta + regra propria do Airbnb);
- aceitar/recusar reserva, dinheiro e qualquer coisa fora do padrao: o hospede recebe uma resposta honesta e o Dono e AVISADO no WhatsApp;
- nunca altera anuncio (este modulo so le e escreve mensagens); o anuncio do Amiga so recebe respostas;
- o navegador so fica ocupado para LER e para ENVIAR; a decisao (lenta) acontece com ele liberado, para nao travar o WhatsApp.
"""
import json
import re
import threading
import time
from datetime import datetime

from . import airbnb, airbnb_base as base, atender, contexto, memoria, power, revisao
from .store import DATA

ARQ = DATA / "airbnb_estado.json"
LOG = DATA / "airbnb.log"
_CICLO = threading.Lock()
CFG_PADRAO = {"intervalo_s": 300, "janela": ["07:00", "22:30"], "max_por_conversa_hora": 2, "max_por_hora": 8, "max_por_dia": 30,
              "max_idade_h": 36, "max_por_ciclo": 3, "max_hospedes": 4, "max_noites": 7, "res_revisita_min": 90, "consulta_reenvio_h": 5}
VALOR_EM_REAIS = re.compile(r"R\$\s*\d|\d+\s*reais|\d+[.,]\d{2}\s*(?:por|a)\s+noite", re.I)
CARTAO_PENDENTE = re.compile(r"Consulta de reserva|Pedido de reserva", re.I)
CARTAO_RESOLVIDO = re.compile(r"recusad|aceit|expirad|cancelad|pr[eé]-aprov|confirmad", re.I)


def _log(txt):
    DATA.mkdir(exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {txt}\n")


def _estado():
    try:
        return json.loads(ARQ.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _salvar(e):
    DATA.mkdir(exist_ok=True)
    ARQ.write_text(json.dumps(e, ensure_ascii=False), encoding="utf-8")


def cfg_de(cfg_router=None):
    c = dict(CFG_PADRAO)
    c.update((cfg_router or {}).get("airbnb_auto", {}))
    return c


def ligado():
    from . import modulos
    return modulos.ativo("airbnb") and bool(_estado().get("ligado"))


def ligar():
    """SO a interface local chama isto. Religar nao apaga o que ja foi tratado (nada e reenviado)."""
    from . import modulos
    modulos.exigir("airbnb")
    e = _estado()
    e["ligado"] = True
    _salvar(e)
    _log("LIGADO")


def desligar():
    e = _estado()
    e["ligado"] = False
    _salvar(e)
    _log("DESLIGADO")


def resumo():
    e = _estado()
    agora = time.time()
    return {"ligado": bool(e.get("ligado")), "respostas_ultima_hora": len([x for x in e.get("envios", []) if agora - x[1] < 3600]),
            "tratadas": len(e.get("tratados", {})), "ultimo_ciclo": e.get("ultimo_ciclo", "")}


# ---------- regras puras (testaveis) ----------

def dentro_da_janela(janela, agora=None):
    agora = agora or datetime.now()
    ini, fim = (tuple(int(x) for x in h.split(":")) for h in janela)
    return ini <= (agora.hour, agora.minute) < fim


def idade_horas(quando, agora=None):
    """'22:50' (hoje) -> horas desde entao; 'ontem' -> 24+; outra coisa (dia da semana, data) -> None (antiga demais para responder de repente)."""
    agora = agora or datetime.now()
    q = (quando or "").strip().lower()
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", q)
    if m:
        t = agora.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
        h = (agora - t).total_seconds() / 3600
        return h if h >= 0 else h + 24
    if q == "ontem":
        return 30.0
    return None


def limite_ok(est, conversa, agora, cfg):
    envios = est.setdefault("envios", [])
    envios[:] = [x for x in envios if agora - x[1] < 86400]
    hora = [x for x in envios if agora - x[1] < 3600]
    hoje = [x for x in envios if datetime.fromtimestamp(x[1]).date() == datetime.fromtimestamp(agora).date()]
    return (len([x for x in hora if x[0] == conversa]) < cfg["max_por_conversa_hora"] and len(hora) < cfg["max_por_hora"] and len(hoje) < cfg["max_por_dia"])


def finais_do_hospede(msgs):
    """Mensagens do HOSPEDE (e cartoes do sistema) depois da ultima resposta nossa. -> (textos_do_hospede, cartoes)."""
    textos, cartoes = [], []
    for m in reversed(msgs):
        if m["de"] in ("voce", "anfitriao"):
            break
        (cartoes if m["de"] == "sistema" else textos).append(m["texto"])
    return list(reversed(textos)), list(reversed(cartoes))


def reserva_pendente(cartoes):
    return any(CARTAO_PENDENTE.search(c) and not CARTAO_RESOLVIDO.search(c.split("Você tem até")[0][:120]) for c in cartoes)


def validar_airbnb(texto):
    ok, motivo = atender.validar_resposta(texto)
    if not ok:
        return ok, motivo
    if re.search(r"https?://|www\.|github", texto, re.I):
        return False, "link (hospede do Airbnb nao recebe link por aqui)"
    if re.search(r"reembols|estorn|multa|devolu[cç][aã]o do (valor|dinheiro)|cancel(ar|amos|ei)", texto, re.I):
        return False, "fala de reembolso/multa/cancelamento (dinheiro: so o Dono)"
    if VALOR_EM_REAIS.search(texto):
        return False, "fala de valor em reais (decisao de dinheiro: so o Dono)"
    return True, ""


# ---------- reservas: regras e consulta a familia ----------

RISCO = re.compile(r"\b(festa|evento|anivers[aá]rio|comemora\w*|churrasco|som\s+alto|caixa\s+de\s+som|pet|cachorro|cadela|gato|animais|animal|visitas?|casamento|confraterniza\w*|filmagem|ensaio|DJ|open\s+bar)\b", re.I)
STUDIO = re.compile(r"^\s*studio\b", re.I)


def _registrar_acao(nome, l, acao, ok, motivo, por):
    """Aceite/pre-aprovacao SEMPRE fica no banco (Jarvis lembra, Parceira pergunta)."""
    txt = f"Airbnb: {acao} de {l['hospede']} ({l['anuncio'][:40]}, {l['meta'][:28]}) " + ("feito" if ok else f"clicado mas NAO confirmado ({motivo}); pode ter sido aceito, conferir") + (f" a pedido de {por}" if por else " SEM decisao humana registrada")
    try:
        memoria.registrar_decisao(nome, f"[{acao}]", "A", txt)
        from . import banco
        banco.gravar_fato("agente Ilhéu", f"airbnb-{acao}:{l['id']}", txt, nivel="local", fonte="airbnb_vigia")
    except Exception as ex:
        _log(f"acao nao gravada: {ex!r}")


def regra_reserva(linha, cartao, textos_hospede, cfg):
    """('auto', None) se TUDO esta dentro do padrao; ('consultar', motivo) em qualquer duvida. Conservador de proposito."""
    if linha["protegido"]:
        return "consultar", "é o anúncio do apartamento do Amiga"
    if not (airbnb.eh_quarto(linha["anuncio"]) or STUDIO.match(linha["anuncio"])):
        return "consultar", "não é quarto/studio (casa inteira ou outro anúncio)"
    hosp = airbnb.parse_hospedes(cartao)
    if hosp is None or hosp > cfg["max_hospedes"]:
        return "consultar", f"são {hosp or '?'} hóspedes (meu limite automático é {cfg['max_hospedes']})"
    noites = airbnb.parse_noites(linha["meta"]) or airbnb.parse_noites(cartao.split("hóspedes", 1)[-1])
    if noites is None or noites > cfg["max_noites"]:
        return "consultar", f"são {noites or '?'} noites (meu limite automático é {cfg['max_noites']})"
    r = RISCO.search(" ".join(textos_hospede))
    if r:
        return "consultar", f"o hóspede falou de '{r.group(0)}'"
    return "auto", None


def pergunta_familia(linha, cartao, motivo, estado, quem):
    """Texto da consulta, no jeito de falar com cada pessoa."""
    acao = "pré-aprovar a consulta" if estado == "consulta" else "aceitar o pedido"
    valor = re.search(r"R\$\s*[\d.,]+", cartao)
    primeiro = (linha["hospede"].split() or [""])[0]
    corpo = (f"{linha['hospede']} ({linha['anuncio'][:34]}, {linha['meta'][:30]}, {airbnb.parse_hospedes(cartao) or '?'} hóspedes"
             f"{', ' + valor.group(0) if valor else ''}). Fiquei com dúvida porque {motivo}. Posso {acao}? "
             f"Responde 'sim {primeiro}' ou 'não {primeiro}'. Quem responder primeiro vale.")
    abre = {"Mãe": "Oi minha tia! Reserva no Airbnb: ", "Parceira": "Parceira, reserva no Airbnb: "}.get(quem, "Airbnb | reserva: ")
    return abre + corpo


SIM = re.compile(r"^\W*(sim|pode|aceita|aceito|aprova|aprovo|pr[eé]-?aprova|autorizo|manda ver|bora|isso)\b", re.I)
NAO = re.compile(r"^\W*(n[aã]o|recusa|recuso|rejeita|negativo)\b", re.I)


def familia():
    """(quem, contato no memoria.db, nome para enviar WhatsApp) do Dono, da Parceira e da Mae."""
    return [("Dono", "Dono(dono)", contexto.contato("dono")), ("Parceira", contexto.contato("parceira"), contexto.contato("parceira")),
            ("Mãe", contexto.contato("mae"), contexto.contato("mae"))]


def ler_decisao(nome_hospede, varias_abertas, mensagens):
    """mensagens = [(quem, ts, texto)] enviadas depois da consulta -> ('sim'|'nao'|None, quem). 'nao' vence 'sim'. Com varias consultas abertas exige o nome do hospede."""
    primeiro = (nome_hospede.split() or [""])[0].lower()
    achou = (None, None)
    for quem, ts, txt in mensagens:
        t = (txt or "").strip()
        if len(t) > 80 or (varias_abertas and primeiro not in t.lower()):
            continue
        if NAO.match(t):
            return "nao", quem
        if SIM.match(t) and not achou[0]:
            achou = ("sim", quem)
    return achou


def processar_respostas(est, mensagens_de=None):
    """Sem navegador: le o que o Dono/Parceira/Mae responderam as consultas abertas e marca est['consultas'][id]['decisao']."""
    mensagens_de = mensagens_de or memoria.mensagens_desde
    abertas = {k: v for k, v in est.get("consultas", {}).items() if not v.get("decisao")}
    for tid, c in abertas.items():
        msgs = []
        for quem, contato, _ in familia():
            if contato:
                msgs += [(quem, ts, tx) for ts, tx in mensagens_de(contato, c["ts0"])]
        msgs.sort(key=lambda x: x[1])
        d, quem = ler_decisao(c["hospede"], len(abertas) > 1, msgs)
        if d:
            c["decisao"], c["por"] = d, quem
            _log(f"{c['hospede']} | decisao da familia: {d} ({quem})")


# ---------- ciclo ----------

def _sig_cartao(cartao):
    return re.sub(r"\s+", " ", cartao or "")[:120]


def _ultimo_cartao(cartoes):
    return next((c for c in reversed(cartoes) if re.match(r"(Consulta de reserva|Pedido de reserva|Reserva pendente)", c)), "")


def ciclo(cfg, sessao=airbnb.AB, decidir=None, agora=None, mensagens_de=None):
    """Um ciclo. sessao() abre o navegador (so para LER e para ENVIAR/AGIR).
    Devolve {'candidatos','enviados','avisos','acoes','perguntas'}; 'perguntas' = [(linha, cartao, motivo, estado, reenvio)] para a familia.
    decidir(it, flags) -> (cod, texto) ou None (injetavel nos testes; padrao = Claude via protocolo JV1 + revisao)."""
    agora = agora if agora is not None else time.time()
    dt = datetime.fromtimestamp(agora)
    est = _estado()
    tratados = est.setdefault("tratados", {})
    tentativas = est.setdefault("tentativas", {})
    res_visto = est.setdefault("res_visto", {})
    res_tratado = est.setdefault("res_tratado", {})
    fc_feito = est.setdefault("firstcontact", {})
    consultas = est.setdefault("consultas", {})
    feito = {"candidatos": [], "enviados": [], "avisos": [], "acoes": [], "perguntas": []}
    processar_respostas(est, mensagens_de)
    duvidas = est.setdefault("duvidas", {})
    info_feito = est.setdefault("info_casa", {})
    _respostas_do_dono(est, duvidas, agora, mensagens_de)

    # fase 1: ler (navegador ocupado so aqui)
    leituras = {}
    with sessao() as ab:
        for l in ab.conversas(25):
            tid = l["id"]
            if l["suporte_airbnb"]:
                continue
            idade = idade_horas(l["quando"], dt)
            sig = f"{l['previa']}|{l['quando']}"
            recente = idade is not None and idade <= cfg["max_idade_h"]
            pendente = airbnb.pendente_de_resposta(l)
            if not pendente:
                tratados.pop(tid, None)
            eh_texto = pendente and tratados.get(tid) != sig
            if eh_texto and (not recente or contexto.encerramento(l["previa"])):
                tratados[tid] = sig                     # antiga, ou so 'ok/obrigado': nao responde sozinho
                eh_texto = False
            if eh_texto and tentativas.get(f"{tid}|{sig}", 0) >= 2:
                tratados[tid] = sig
                _log(f"{l['hospede']} | desistiu apos 2 tentativas")
                eh_texto = False
            if eh_texto and not limite_ok(est, tid, agora, cfg):
                eh_texto = False
            revisita = (not eh_texto and recente and agora - res_visto.get(tid, 0) > cfg["res_revisita_min"] * 60) or tid in consultas or bool(duvidas.get(tid, {}).get("resposta"))
            if not eh_texto and not revisita:
                continue
            if len(leituras) >= cfg["max_por_ciclo"] and tid not in consultas and not duvidas.get(tid, {}).get("resposta"):
                continue
            if eh_texto:
                tentativas[f"{tid}|{sig}"] = tentativas.get(f"{tid}|{sig}", 0) + 1
            res_visto[tid] = agora
            leituras[tid] = (l, sig, ab.ler(tid, 25), eh_texto)
    _salvar(est)

    # fase 2: decidir (navegador livre; o Claude pode demorar)
    decidir = decidir or _decidir_padrao
    plano = []
    for tid, (l, sig, leitura, eh_texto) in leituras.items():
        msgs = leitura["mensagens"]
        cartoes = [m["texto"] for m in msgs if m["de"] == "sistema"]
        estado = airbnb.estado_reserva(cartoes)
        cartao = _ultimo_cartao(cartoes) if estado else ""
        if estado and airbnb.prazo_vencido(cartao, dt):
            estado, cartao = None, ""                   # o prazo de 24 h ja passou: nao ha mais o que aceitar/pre-aprovar
        textos, _ = finais_do_hospede(msgs)
        if msgs and msgs[-1]["de"] == "sistema" and re.search(r"recusad|cancelad|expirou|expirad", msgs[-1]["texto"][:60], re.I):
            textos, eh_texto = [], False               # pedido recusado/cancelado/expirado: a conversa terminou, nao puxa assunto
            tratados[tid] = sig
        sem_nossa = not any(m["de"] in ("voce", "anfitriao") for m in msgs)
        precisa_fc = bool(textos or estado) and airbnb.eh_quarto(l["anuncio"]) and not l["protegido"] and sem_nossa and tid not in fc_feito and len(msgs) <= 24
        if not estado:
            consultas.pop(tid, None)                    # resolvida (por voces ou pelo proprio hospede): sai da espera
        nome = f"{l['hospede']} (Airbnb)"
        cod, texto = None, None
        if eh_texto and textos:
            ctx = [("C: " if m["de"] in ("voce", "anfitriao") else "E: ") + m["texto"][:100] for m in msgs[-8:]]
            s_anun = base.slug(l["anuncio"])
            if s_anun:
                ctx += ["BASE DO ANUNCIO (dado do Dono): " + f for f in base.fatos(s_anun, " ".join(textos))]
            if precisa_fc:
                ctx.append("C: (resposta rapida 'firstcontact' enviada agora: quarto privativo, areas compartilhadas, sem cafe)")
            it = {"nome": nome, "nl": len(textos), "msgs": textos, "ctx": ctx, "autores": {nome}, "midia": False, "grupo": False}
            flags = "B" + ("R" if estado else "")
            feito["candidatos"].append(nome)
            _log(f"{nome} | decidindo | flags={flags} | msgs={textos[-2:]!r}")
            dec = decidir(it, flags)
            if not dec:
                _log(f"{nome} | sem decisao (tenta no proximo ciclo)")
                continue
            cod, texto = dec
            if cod == "E":
                ok, motivo = validar_airbnb(texto)
                if not ok:
                    _log(f"{nome} | resposta barrada ({motivo}): {texto[:90]!r}")
                    feito["avisos"].append(f"Airbnb | {nome}: segurei a resposta ({motivo}). Ele disse: {' / '.join(textos)[:200]}")
                    tratados[tid] = sig
                    cod, texto = "P", None
            elif cod in ("A", "P"):
                if cod == "P":
                    duvidas[tid] = {"hospede": l["hospede"], "anuncio": l["anuncio"], "ts0": agora, "pergunta": " ".join(textos)[:300]}
                    texto = (texto or "precisa da sua decisao") + f" -> me responde '{(l['hospede'].split() or ['x'])[0]}: sua resposta' que eu mando pra ele e guardo na base."
                feito["avisos"].append(f"Airbnb | {nome} ({l['anuncio'][:40]}): {texto or 'precisa da sua decisao'}")
                memoria.registrar_decisao(nome, " ".join(textos), cod, texto)
                tratados[tid] = sig
            else:
                tratados[tid] = sig
                memoria.registrar_decisao(nome, " ".join(textos), "I", "")
                _log(f"{nome} | ignorada")
        elif eh_texto:
            tratados[tid] = sig
        acao = None
        if estado:
            c_sig = _sig_cartao(cartao)
            c = consultas.get(tid)
            tipo = "preaprovar" if estado == "consulta" else "aceitar"
            if c and c.get("decisao") == "sim":
                acao = tipo
            elif c and c.get("decisao") == "nao":
                feito["avisos"].append(f"Airbnb | {l['hospede']}: {c['por']} mandou RECUSAR. Eu não recuso sozinho: recusa lá no Airbnb (o prazo é de 24 h).")
                consultas.pop(tid, None)
                res_tratado[tid] = c_sig
            elif c:
                if agora - c["ts"] > cfg["consulta_reenvio_h"] * 3600 and c["n"] < 3:
                    feito["perguntas"].append((l, cartao, "ainda não tive resposta e o prazo de 24 h do Airbnb está correndo", estado, True))
            elif res_tratado.get(tid) != c_sig:
                regra, motivo = regra_reserva(l, cartao, textos_de_hospede(msgs), cfg)
                if regra == "auto" and cod in ("A", "P"):
                    regra, motivo = "consultar", "a conversa ficou com uma dúvida que precisa de vocês"
                if regra == "auto":
                    regra, motivo = "consultar", "toda reserva precisa do OK de vocês (regra do Dono, 26/10)"
                if True:
                    consultas[tid] = {"hospede": l["hospede"], "ts0": agora, "ts": agora, "n": 1, "estado": estado}
                    feito["perguntas"].append((l, cartao, motivo, estado, False))
        resp = duvidas.get(tid, {}).get("resposta")
        if resp:
            ok, motivo = validar_airbnb(resp)
            if ok:
                cod, texto = "E", resp
                if base.slug(l["anuncio"]):
                    base.guardar(base.slug(l["anuncio"]), f"P: {duvidas[tid]['pergunta'][:120]} R: {resp}")
            else:
                feito["avisos"].append(f"Airbnb | {l['hospede']}: não mandei sua resposta ({motivo}). Responda direto no Airbnb.")
            duvidas.pop(tid, None)
        precisa_info = bool(estado) and base.tipo(l["anuncio"]) == "casa" and tid not in info_feito
        info = None
        if precisa_info:
            info = base.info_casa()
            if not info:
                info_feito[tid] = agora
                feito["avisos"].append(f"Airbnb | {l['hospede']} pediu a Casa Princesinha e eu não tenho o texto da 'Info Casa' (outros espaços no mesmo terreno). Me manda 'info casa: texto' que eu guardo. Não aceito essa reserva sem você.")
        if (cod == "E" and texto) or precisa_fc or acao or info:
            plano.append((tid, l, sig, nome, texto if cod == "E" else None, precisa_fc, acao, cartao, textos, info))

    # fase 3: enviar / agir (navegador ocupado so aqui)
    if plano:
        with sessao() as ab:
            for tid, l, sig, nome, texto, precisa_fc, acao, cartao, textos, info in plano:
                if info:
                    ok, motivo = ab.enviar(tid, info)
                    if ok:
                        info_feito[tid] = agora
                        feito["enviados"].append(nome + " [info casa]")
                        memoria.registrar_msg(nome, "C", info, canal="airbnb")
                        _log(f"{nome} | INFO CASA enviada")
                    else:
                        feito["avisos"].append(f"Airbnb | {nome}: não consegui enviar a Info Casa ({motivo}).")
                        continue
                if precisa_fc:
                    fc = ab.resposta_rapida(tid, "firstcontact")
                    if not fc:
                        feito["avisos"].append(f"Airbnb | {nome}: não achei a resposta rápida 'firstcontact' no Airbnb.")
                        fc_feito[tid] = agora
                    else:
                        ok, motivo = ab.enviar(tid, fc)
                        if not ok:
                            _log(f"{nome} | FALHA firstcontact: {motivo}")
                            feito["avisos"].append(f"Airbnb | {nome}: não consegui enviar a firstcontact ({motivo}).")
                            continue
                        fc_feito[tid] = agora
                        _log(f"{nome} | FIRSTCONTACT enviada")
                        feito["enviados"].append(nome + " [firstcontact]")
                        memoria.registrar_msg(nome, "C", fc, canal="airbnb")
                if texto:
                    ok, motivo = ab.enviar(tid, texto)
                    if not ok:
                        _log(f"{nome} | FALHA no envio: {motivo}")
                        feito["avisos"].append(f"Airbnb | {nome}: não consegui enviar a resposta ({motivo}). Veja no Airbnb.")
                        continue
                    est.setdefault("envios", []).append([tid, agora])
                    tratados[tid] = sig
                    memoria.registrar_msg(nome, "E", " ".join(textos), canal="airbnb")
                    memoria.registrar_msg(nome, "C", texto, canal="airbnb")
                    memoria.registrar_decisao(nome, " ".join(textos), "E", texto)
                    feito["enviados"].append(nome)
                    _log(f"{nome} | ENVIADO | {texto!r}")
                if acao:
                    ok, motivo = ab.decidir_reserva(tid, acao)
                    res_tratado[tid] = _sig_cartao(cartao)
                    _registrar_acao(nome, l, acao, ok, motivo, consultas.get(tid, {}).get("por"))
                    por = consultas.pop(tid, {}).get("por")
                    verbo = "Pré-aprovei" if acao == "preaprovar" else "Aceitei"
                    if ok:
                        feito["acoes"].append(f"{l['hospede']}: {acao}")
                        _log(f"{nome} | {acao.upper()} OK" + (f" (decisao de {por})" if por else " (dentro do padrao)"))
                        feito["avisos"].append(f"Airbnb | {verbo} {l['hospede']} ({l['anuncio'][:32]}, {l['meta'][:28]}) " + (f"a pedido de {por}." if por else "- estava tudo dentro do padrão."))
                    else:
                        _log(f"{nome} | {acao.upper()} FALHOU: {motivo}")
                        feito["avisos"].append(f"Airbnb | {l['hospede']}: tentei {acao} e não deu ({motivo}). Veja no Airbnb, o prazo é de 24 h.")
    for l, cartao, motivo, estado, reenvio in feito["perguntas"]:
        c = consultas.get(l["id"])
        if c and reenvio:
            c["n"] += 1
            c["ts"] = agora
        _log(f"{l['hospede']} | consulta a familia ({'reenvio' if reenvio else 'nova'}): {motivo}")
    q = est.setdefault("quest", {})
    prox = next((s for s in base.ANUNCIOS if s not in q), None)
    if prox and not feito["avisos"] and agora - max(q.values(), default=0) > 3600:
        q[prox] = agora
        feito["avisos"].append(base.questionario(prox))
    est["ultimo_ciclo"] = dt.strftime("%Y-%m-%d %H:%M")
    _salvar(est)
    return feito


def _respostas_do_dono(est, duvidas, agora, mensagens_de=None):
    """Lê o WhatsApp do Dono: 'cacau: texto' vira fato do anuncio; 'Nome: texto' responde a duvida aberta daquele hospede."""
    mensagens_de = mensagens_de or memoria.mensagens_desde
    contato = familia()[0][1]
    ult = est.get("base_ts", agora)
    msgs = mensagens_de(contato, ult) if contato else []
    if not msgs:
        est.setdefault("base_ts", ult)
        return
    est["base_ts"] = max(ts for ts, _ in msgs)
    abertos = {(d["hospede"].split() or [""])[0].lower(): tid for tid, d in duvidas.items()}
    fa, rh = base.ler_respostas(msgs, set(abertos))
    for k, txt in fa:
        s, _, tema = k.partition(":")
        base.guardar(s, txt, tema or None)
        _log(f"base do anuncio {s}: {txt[:60]!r}")
    for nome, txt in rh:
        duvidas[abertos[nome]]["resposta"] = txt


def textos_de_hospede(msgs):
    return [m["texto"] for m in msgs if m["de"] == "hospede"]


def _decidir_padrao(it, flags):
    """Mesmo caminho do WhatsApp: Claude ao vivo (canal) ou Claude de fundo, depois auditoria/revisao."""
    dec = atender.decidir(it, flags)
    if not dec:
        return None
    cod, texto, _nota = revisao.decidir_com_revisao(it, flags, dec)
    return cod, texto


# ---------- uso manual (ferramentas do Jarvis: Dono / Mae / Parceira pedem pelo WhatsApp ou Telegram) ----------

def _achar(linhas, alvo):
    alvo = (alvo or "").strip().lower()
    if not alvo:
        return None
    for l in linhas:
        if alvo == l["id"] or alvo in l["hospede"].lower():
            return l
    return None


def pendentes_texto(sessao=airbnb.AB):
    try:
        with sessao() as ab:
            linhas = ab.conversas(25)
    except airbnb.AirbnbIndisponivel as e:
        return f"Não consegui abrir o Airbnb agora: {e}"
    pend = [l for l in linhas if airbnb.pendente_de_resposta(l)]
    if not pend:
        return "Airbnb: nenhum hóspede esperando resposta. ✅"
    return "Airbnb — esperando resposta:\n" + "\n".join(f"• {l['hospede']} ({l['anuncio'][:40]}, {l['meta'][:30]}) {l['quando']}: {l['previa'][:90]}" for l in pend)


def conversa_texto(alvo, sessao=airbnb.AB):
    try:
        with sessao() as ab:
            l = _achar(ab.conversas(25), alvo)
            if not l:
                return f"Não achei conversa do Airbnb com '{alvo}' entre as mais recentes."
            msgs = ab.ler(l["id"], 12)["mensagens"]
    except airbnb.AirbnbIndisponivel as e:
        return f"Não consegui abrir o Airbnb agora: {e}"
    quem = {"hospede": l["hospede"], "voce": "Nós", "anfitriao": "Anfitrião", "sistema": "Airbnb"}
    return f"{l['hospede']} — {l['anuncio'][:50]} ({l['meta'][:40]})\n" + "\n".join(f"{quem.get(m['de'], m['de'])}: {m['texto'][:300]}" for m in msgs)


def responder_manual(alvo, texto, sessao=airbnb.AB):
    """Envia um texto a um hospede a pedido de pessoa autorizada. Mesmas travas de conteudo do WhatsApp (sem link/numero/dado sensivel)."""
    ok, motivo = atender.validar_resposta(texto or "")
    if not ok:
        return f"Não enviei: {motivo}."
    try:
        with sessao() as ab:
            l = _achar(ab.conversas(25), alvo)
            if not l:
                return f"Não achei conversa do Airbnb com '{alvo}' entre as mais recentes."
            ok, motivo = ab.enviar(l["id"], texto)
    except airbnb.AirbnbIndisponivel as e:
        return f"Não consegui abrir o Airbnb agora: {e}"
    if ok:
        _log(f"{l['hospede']} | ENVIADO (pedido manual) | {texto!r}")
        memoria.registrar_msg(f"{l['hospede']} (Airbnb)", "C", texto, canal="airbnb")
        return f"✅ Mensagem enviada a {l['hospede']} no Airbnb."
    return f"Falhou ao enviar a {l['hospede']} ({motivo}). Confira o Airbnb."


def reserva_manual(alvo, acao, sessao=airbnb.AB):
    """Pre-aprova a consulta / aceita o pedido de um hospede a pedido do Dono (nunca recusa)."""
    if acao not in ("preaprovar", "aceitar"):
        return "Só consigo 'preaprovar' ou 'aceitar'. Recusar fica com você no Airbnb."
    try:
        with sessao() as ab:
            l = _achar(ab.conversas(25), alvo)
            if not l:
                return f"Não achei conversa do Airbnb com '{alvo}' entre as mais recentes."
            if l["protegido"]:
                return "Esse é o anúncio do apartamento do Amiga: eu só respondo hóspede lá, não mexo em reserva."
            ok, motivo = ab.decidir_reserva(l["id"], acao)
    except airbnb.AirbnbIndisponivel as e:
        return f"Não consegui abrir o Airbnb agora: {e}"
    _log(f"{l['hospede']} | {acao.upper()} (pedido manual) -> {ok} {motivo}")
    return f"✅ {l['hospede']}: {'pré-aprovado' if acao == 'preaprovar' else 'pedido aceito'}." if ok else f"Não consegui ({motivo})."


def notificar_dono(avisos, enviar=None):
    """Manda os avisos ao Dono no WhatsApp (texto curto). Fora da sessao do Airbnb, para nao disputar a aba."""
    if not avisos:
        return
    from . import whatsapp
    dono = contexto.contato("dono")
    if not dono:
        return
    enviar = enviar or whatsapp.enviar
    try:
        with whatsapp.LOCK:
            enviar(dono, "\n".join(avisos)[:900])
    except Exception as e:
        _log(f"aviso ao Dono falhou: {e!r}")


def notificar_familia(perguntas, enviar=None):
    """Consulta o Dono, a Parceira e a Mae por WhatsApp (cada um no seu jeito). Fora da sessao do Airbnb."""
    if not perguntas:
        return
    from . import whatsapp
    enviar = enviar or whatsapp.enviar
    for l, cartao, motivo, estado, reenvio in perguntas:
        for quem, _, nome_wpp in familia():
            if not nome_wpp:
                continue
            try:
                with whatsapp.LOCK:
                    enviar(nome_wpp, pergunta_familia(l, cartao, motivo, estado, quem)[:900])
            except Exception as e:
                _log(f"consulta a {quem} falhou: {e!r}")


def iniciar(router):
    """Thread do atendimento automatico do Airbnb. Nada acontece com ele desligado, com o Braniac pausado ou fora da janela de horario."""
    def loop():
        espera, avisou_indisp = 30, 0
        while True:
            time.sleep(espera)
            cfg = cfg_de(router.cfg)
            espera = cfg["intervalo_s"]
            try:
                if not ligado() or power.pausado() or not dentro_da_janela(cfg["janela"]):
                    continue
                if not _CICLO.acquire(blocking=False):
                    continue
                try:
                    feito = ciclo(cfg)
                finally:
                    _CICLO.release()
                notificar_dono(feito["avisos"])
                notificar_familia(feito["perguntas"])
                if feito["enviados"]:
                    _log(f"ciclo: respondeu {feito['enviados']}")
            except airbnb.AirbnbIndisponivel as e:
                _log(f"indisponivel: {e}")
                if time.time() - avisou_indisp > 6 * 3600:      # avisa o Dono no maximo a cada 6 h
                    avisou_indisp = time.time()
                    notificar_dono([f"Airbnb | atendimento automatico parado: {e}"])
            except Exception as e:
                _log(f"erro no ciclo: {e!r}")
    threading.Thread(target=loop, daemon=True, name="airbnb-vigia").start()
