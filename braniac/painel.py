# -*- coding: utf-8 -*-
"""Painel da interface (08/10/2026, ideias do conselho de IAs): BOTAO DE PANICO, status dos bracos e historico de acoes.
O panico so DESLIGA/DESARMA (direcao segura): por isso pode vir de qualquer canal. Nada aqui arma ou liga algo."""
from datetime import datetime


def _data():
    from . import store       # lido na hora: os testes isolam store.DATA
    return store.DATA


def panico(origem="web"):
    """Desarma a autonomia remota e desliga o atendimento automatico do WhatsApp e do Airbnb. Devolve o que foi feito."""
    from . import airbnb_vigia, power, vigia
    feito = []
    if power.armada():
        feito.append("autonomia remota desarmada")
    power.armar(0)
    if power.atendimento_auto():
        feito.append("atendimento automático do WhatsApp desligado")
    vigia.desligar()
    try:
        if airbnb_vigia.resumo().get("ligado"):
            feito.append("atendimento automático do Airbnb desligado")
        airbnb_vigia.desligar()
    except Exception as e:
        feito.append(f"Airbnb: não consegui confirmar ({str(e)[:60]})")
    linha = f"PANICO ({origem}): " + ("; ".join(feito) if feito else "tudo já estava desligado")
    try:
        with (_data() / "painel.log").open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {linha}\n")
    except OSError:
        pass
    return {"ok": True, "feito": feito,
            "texto": "🛑 Pânico acionado: " + ("; ".join(feito) if feito else "tudo já estava desligado") +
                     ". Para religar, use os botões da interface no PC."}


def _seguro(fn, padrao):
    try:
        return fn()
    except Exception:
        return padrao


def bracos(status=None):
    """[{nome, ok (ligado/saudavel), detalhe}] para o painel. status = o /api/status ja montado (evita recalcular)."""
    from . import power
    s = status or {}
    v = s.get("atendimento_auto") or {}
    a = s.get("airbnb_auto") or {}
    esc = s.get("escuta_voz") or {}
    em = s.get("email") or {}
    out = [
        {"nome": "Atendimento WhatsApp", "ok": bool(v.get("ligado")),
         "detalhe": f"ligado · {v.get('respostas_ultima_hora', 0)} resp./h" if v.get("ligado") else "desligado"},
        {"nome": "Airbnb", "ok": bool(a.get("ligado")), "detalhe": "ligado" if a.get("ligado") else "desligado"},
        {"nome": "Autonomia remota", "ok": power.armada(),
         "detalhe": f"ARMADA · {power.armada_restante_min()} min" if power.armada() else "desarmada"},
        {"nome": "Microfone (voz)", "ok": esc.get("estado") not in (None, "parada"), "detalhe": esc.get("estado") or "parada"},
        {"nome": "E-mail (Gmail)", "ok": bool(em.get("logado")), "detalhe": "conectado" if em.get("logado") else "não conectado (/email)"},
    ]
    from . import guarda
    out.append({"nome": "Guarda de segurança", "ok": True, "detalhe": _seguro(guarda.resumo, "sem leitura")[:90]})
    rot = _seguro(lambda: __import__("json").loads((_data() / "rotina.json").read_text(encoding="utf-8")), {})
    hoje = datetime.now().strftime("%Y-%m-%d")
    out.append({"nome": "Bom dia das 6h", "ok": rot.get("bom_dia") == hoje,
                "detalhe": "enviado hoje" if rot.get("bom_dia") == hoje else f"último: {rot.get('bom_dia') or 'nunca'}"})
    from . import manutencao
    m = manutencao.ultimo()
    out.append({"nome": "Manutenção da madrugada", "ok": bool(m) and m.get("testes_ok", False),
                "detalhe": (f"{m.get('quando', '?')} · " + ("testes OK" if m.get("testes_ok") else "ATENÇÃO: " + m.get("resumo", "")[:60])) if m else "ainda não rodou"})
    return out


LOGS = (("vigia.log", "WhatsApp"), ("atendimentos.log", "WhatsApp"), ("dono.log", "Dono"), ("airbnb.log", "Airbnb"),
        ("delegacoes.log", "Claude"), ("seguranca.log", "Segurança"), ("painel.log", "Painel"), ("manutencao.log", "Manutenção"))


def historico(n=40, max_linha=140):
    """Ultimas acoes dos bracos, lidas dos logs LOCAIS (so a interface 127.0.0.1 ve). [{quando, braco, texto}] do mais novo ao mais antigo."""
    itens = []
    for arq, braco in LOGS:
        try:
            with (_data() / arq).open("rb") as f:
                f.seek(0, 2)
                f.seek(max(0, f.tell() - 20000))
                linhas = f.read().decode("utf-8", "replace").splitlines()[-n:]
        except OSError:
            continue
        for l in linhas:
            if len(l) > 21 and l[4] == "-" and l[19:22] == " | ":
                itens.append({"quando": l[:19], "braco": braco, "texto": l[22:22 + max_linha]})
    itens.sort(key=lambda x: x["quando"], reverse=True)
    return itens[:n]
