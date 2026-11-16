# -*- coding: utf-8 -*-
"""Agente VAQUINHA (27/10/2026): acompanha a conta bancaria da vaquinha do Dono (aba logada no Chrome do Braniac; so LEITURA) e, a cada 5 min, soma os Pix
RECEBIDOS depois do inicio, grava o total em site/total.json e republica o site (Vercel) quando o valor muda. O site publico mostra SO o total e a barra de
progresso: nunca nome nem valor de quem contribuiu. Nunca paga, transfere nem mexe na conta; login e sempre o Dono.
So roda depois de `configurar(...)`: ate la nao le conta nenhuma."""
import json
import re
import subprocess
import threading
import time
from datetime import datetime

from .store import DATA

ESTADO = DATA / "vaquinha.json"
SITE = DATA.parent.parent.parent / "vaquinha-site"     # C:\Users\usuario\Projetos\vaquinha-site
META = 6000.0
INTERVALO_S = 300
MIN_ENTRE_DEPLOYS_S = 300
MAX_DEPLOYS_DIA = 40                                    # Vercel (plano gratis) limita deploys por dia


def _estado():
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _salvar(est):
    ESTADO.write_text(json.dumps(est, ensure_ascii=False), encoding="utf-8")


def _chave(m):
    return f"{m['data']}|{m['hora']}|{m['desc']}|{m['valor']}"


def _ler_infinitepay():
    from . import financeiro
    from datetime import date
    # a leitura do financeiro serve a qualquer conta InfinitePay logada na aba; a vaquinha usa so os movimentos
    return financeiro.ler_conta(date.today())[1]


LEITORES = {"infinitepay": _ler_infinitepay}           # banco novo = um leitor novo aqui (devolve movimentos {data, desc, valor, hora})


def configurar(banco, ler=None, agora=None):
    """Liga o agente. O que ja esta no extrato agora NAO conta (so Pix novos); devolve quantos movimentos antigos foram marcados."""
    agora = agora or datetime.now()
    ler = ler or LEITORES[banco]
    est = _estado()
    movs = ler()
    est.update({"ativo": True, "banco": banco, "inicio": agora.isoformat(timespec="minutes"), "meta": est.get("meta", META),
                "arrecadado": est.get("arrecadado", 0.0), "vistos": sorted({_chave(m) for m in movs} | set(est.get("vistos", [])))[-1500:]})
    _salvar(est)
    _escrever_total(est)
    return len(movs)


def ajustar(valor, motivo=""):
    """Soma/subtrai a mao (ex.: Pix recebido antes de ligar o agente, ou estorno). Registra o motivo."""
    est = _estado()
    est["arrecadado"] = round(est.get("arrecadado", 0.0) + float(valor), 2)
    est.setdefault("ajustes", []).append({"valor": float(valor), "motivo": motivo[:80], "ts": datetime.now().isoformat(timespec="minutes")})
    _salvar(est)
    _escrever_total(est)
    return est["arrecadado"]


def _escrever_total(est):
    SITE.mkdir(parents=True, exist_ok=True)
    (SITE / "total.json").write_text(json.dumps({"arrecadado": est.get("arrecadado", 0.0), "meta": est.get("meta", META),
                                                 "atualizado": datetime.now().isoformat(timespec="minutes"),
                                                 **({"escritorio_ate": est["escritorio_ate"]} if est.get("escritorio_ate") else {})}), encoding="utf-8")


def publicar():
    """Publica o total: commit + push do total.json no repositorio publico do site (a pagina le o arquivo de la). Devolve (ok, saida).
    Sem deploy do Vercel: nao ha limite de deploys nem login a manter. O cache do GitHub atrasa ate ~5 min."""
    def git(*args):
        return subprocess.run(["git", *args], cwd=str(SITE), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90, creationflags=0x08000000)
    try:
        git("add", "total.json", "escritorio.html", "index.html")
        if not git("status", "--porcelain").stdout.strip():
            return True, "sem mudanca"
        c = git("commit", "-m", "total da vaquinha")
        p = git("push")
        return c.returncode == 0 and p.returncode == 0, (c.stdout + c.stderr + p.stderr)[-300:]
    except Exception as e:
        return False, str(e)[:200]


def ciclo(enviar_dono, ler=None, publicar_fn=publicar, agora=None):
    """Le a conta, soma Pix novos, avisa o Dono e republica o site se o total mudou. Devolve o total ou None se desligado/erro."""
    est = _estado()
    if not est.get("ativo"):
        return None
    agora = agora or datetime.now()
    try:
        movs = (ler or LEITORES[est["banco"]])()
    except Exception:
        return None
    vistos = set(est.get("vistos", []))
    novos = [m for m in movs if _chave(m) not in vistos and m["valor"] > 0 and m["desc"].lower().startswith("pix")]
    est["vistos"] = sorted(vistos | {_chave(m) for m in movs})[-1500:]
    for m in novos:
        est["arrecadado"] = round(est.get("arrecadado", 0.0) + m["valor"], 2)
    if novos:
        enviar_dono(f"🐮 Vaquinha: entrou R$ {sum(m['valor'] for m in novos):.2f}".replace(".", ",") +
                      f" ({', '.join(m['desc'][4:30].strip() or 'Pix' for m in novos[:3])}). Total: R$ {est['arrecadado']:.2f} de R$ {est.get('meta', META):.0f}.".replace(".", ",", 1))
    est["ts"] = time.time()
    _escrever_total(est)
    mudou = est.get("publicado") != est["arrecadado"]
    hoje = agora.strftime("%Y-%m-%d")
    deploys = est.get("deploys", {}).get(hoje, 0)
    if mudou and time.time() - est.get("ultimo_deploy", 0) >= MIN_ENTRE_DEPLOYS_S and deploys < MAX_DEPLOYS_DIA:
        ok, saida = publicar_fn()
        est["ultimo_deploy"] = time.time()
        est["deploys"] = {hoje: deploys + 1}
        if ok:
            est["publicado"] = est["arrecadado"]
        else:
            est["ultimo_erro"] = saida
    _salvar(est)
    try:
        from . import barramento
        if novos:
            barramento.enviar("Vaquinha", "Compasso", "status", f"{len(novos)} Pix novo(s); total R$ {est['arrecadado']:.2f}")
    except Exception:
        pass
    return est["arrecadado"]


def resposta():
    est = _estado()
    if not est.get("ativo"):
        return "A vaquinha ainda não foi ligada (falta logar o banco e eu ligar o agente)."
    meta = est.get("meta", META)
    return (f"🐮 Vaquinha: R$ {est['arrecadado']:.2f} de R$ {meta:.0f} ({est['arrecadado'] / meta * 100:.0f}%), faltam R$ {max(meta - est['arrecadado'], 0):.2f}. ".replace(".", ",", 1) +
            (f"Site atualizado com R$ {est['publicado']:.2f}." if est.get("publicado") is not None else "Site ainda não publicado."))


def iniciar(enviar_dono):
    """Thread local: a cada 5 min (so se a vaquinha estiver ligada)."""
    from . import modulos
    if not modulos.ativo("vaquinha"):
        return
    def loop():
        time.sleep(90)
        while True:
            try:
                from . import power
                if not power.pausado():
                    ciclo(enviar_dono)
            except Exception:
                pass
            time.sleep(INTERVALO_S)
    threading.Thread(target=loop, daemon=True, name="vaquinha").start()


# ---------- modo "Parceira informa" (27/10/2026): sem login em banco; a Parceira responde a cada 6 h quanto tem e o Jarvis atualiza o site ----------
HORAS_PERGUNTA = (8, 14, 20)         # 6 h entre uma e outra, sempre em hora acordada
LEMBRETE_APOS_S = 3 * 3600           # 1 lembrete gentil se ela nao responder
TETO = 100000.0


def valor_da_resposta(texto):
    """Extrai o TOTAL informado ('R$ 1.234,56', '1234', '350 reais', 'nada ainda'). None se nao achou numero claro. Pura (testavel)."""
    import re
    t = (texto or "").lower().replace("\xa0", " ")
    if re.search(r"\b(nada|zero|nenhum|ainda n[aã]o|n[aã]o (?:entrou|caiu|tem))\b", t) and not re.search(r"\d", t):
        return 0.0
    achados = re.findall(r"\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:[.,]\d{1,2})?", t)
    if len(achados) != 1:
        return None                     # nenhum ou varios numeros: nao arrisca
    n = achados[0]
    n = n.replace(".", "").replace(",", ".") if ("," in n or re.fullmatch(r"\d{1,3}(?:\.\d{3})+", n)) else n
    try:
        v = float(n)
    except ValueError:
        return None
    return round(v, 2) if 0 <= v <= TETO else None


def ligar_manual():
    est = _estado()
    est.update({"ativo": True, "modo": "parceira", "banco": None, "meta": est.get("meta", META), "arrecadado": est.get("arrecadado", 0.0)})
    _salvar(est)
    _escrever_total(est)


def tick(enviar_parceira, enviar_dono, agora=None):
    """Chamado no tick (~10 min). Pergunta a saldo a Parceira nas horas combinadas e lembra 1x. Devolve 'perguntou'/'lembrou'/None."""
    from . import modulos
    if not modulos.ativo("vaquinha"):
        return None
    est = _estado()
    if est.get("modo") != "parceira" or est.get("encerrada"):      # 28/10: meta batida, vaquinha encerrada a pedido do Dono
        return None
    agora = agora or datetime.now()
    marca = agora.strftime("%Y-%m-%d") + f" {agora.hour:02d}"
    if agora.hour in HORAS_PERGUNTA and est.get("pergunta_marca") != marca:
        est.update({"pergunta_marca": marca, "aguardando": True, "pergunta_ts": time.time(), "lembrou": False})
        _salvar(est)
        enviar_parceira("Oi, Parceira! É o Jarvis. 🐮 Pra atualizar o site da vaquinha: quanto já recebemos até agora e quanto já gastamos? Me responde assim: recebemos R$ 350 e gastamos R$ 100. Obrigado!")
        return "perguntou"
    if est.get("aguardando") and not est.get("lembrou") and time.time() - est.get("pergunta_ts", 0) >= LEMBRETE_APOS_S and 8 <= agora.hour < 21:
        est["lembrou"] = True
        _salvar(est)
        enviar_parceira("Parceira, só lembrando da vaquinha: quando puder, me diz quanto já recebemos e quanto já gastamos. 🙏")
        return "lembrou"
    return None


def aguardando():
    from . import modulos
    if not modulos.ativo("vaquinha"):
        return False
    est = _estado()
    return est.get("modo") == "parceira" and bool(est.get("aguardando"))


def valores_da_resposta(texto):
    """{'recebido': x|None, 'gasto': y|None} a partir de 'recebemos R$ 350 e gastamos 100'. Sem rotulo: 1o = recebido, 2o = gasto. Pura (testavel)."""
    import re
    t = (texto or "").lower().replace("\xa0", " ")
    achados = [(m.start(), m.group()) for m in re.finditer(r"\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:[.,]\d{1,2})?", t)]
    if not achados and re.search(r"\b(nada|zero|nenhum)\b", t):
        return {"recebido": 0.0, "gasto": None}
    if not achados or len(achados) > 2:
        return {}
    out, livres = {}, []
    for pos, n in achados:
        v = valor_da_resposta(n)
        if v is None:
            return {}
        antes = t[max(0, pos - 28):pos]
        g = [m.end() for m in re.finditer(r"gast|saiu|sa[ií]ram|paguei|pagamos|pago", antes)]
        r = [m.end() for m in re.finditer(r"receb|entrou|entraram|arrecad|caiu|ca[ií]ram|total", antes)]
        sd = [m.end() for m in re.finditer(r"saldo|na conta|temos|\btem\b|sobr|restam|restou|dispon", antes)]
        cands = [(lst[-1], nome) for lst, nome in ((g, "gasto"), (r, "recebido"), (sd, "saldo")) if lst]
        melhor = max(cands) if cands else None
        if melhor:                                  # vale o rotulo mais perto do numero
            out[melhor[1]] = v
        else:
            livres.append(v)
    for v in livres:
        out["recebido" if "recebido" not in out else "gasto"] = v
    res = {k: out.get(k) for k in ("recebido", "gasto", "saldo")} if out else {}
    if res.get("recebido") is not None and re.search(r"receb\w*\s+(?:mais|a mais|novos?)|\ba mais|al[eé]m d", t):
        res["a_mais"] = True                         # 'recebemos MAIS R$ 4.126' = soma ao total (28/10: o Jarvis trocou o total por 4126)
    return res


def registrar_valores(vals, quem="Parceira", publicar_fn=None, enviar_dono=None, rotulado=False):
    """A Parceira informou recebido e/ou gasto: grava, atualiza o site (so o recebido, o gasto fica privado) e avisa o Dono. Devolve a resposta para ela."""
    est = _estado()
    ant_r, ant_g = est.get("arrecadado", 0.0), est.get("gasto", 0.0)
    conf_ok = est.pop("conf_ok", False)
    if vals.pop("a_mais", False) and vals.get("recebido") is not None:
        vals["recebido"] = round(ant_r + vals["recebido"], 2)
    if vals.get("saldo") is not None:               # ela disse o que TEMOS na conta: recebido = saldo + o que ja foi gasto
        gasto = vals["gasto"] if vals.get("gasto") is not None else ant_g
        vals = {"recebido": round(vals["saldo"] + gasto, 2), "gasto": vals.get("gasto") if vals.get("gasto") is not None else (ant_g if est.get("gasto") is not None else 0.0)}
    if est.get("falta") == "gasto" and vals.get("recebido") is not None and vals.get("gasto") is None and not rotulado:
        vals = {"recebido": None, "gasto": vals["recebido"]}      # numero SOLTO (sem 'recebemos'/'gastamos') logo depois de perguntarmos o gasto
    brl0 = lambda v: f"R$ {v:.2f}".replace(".", ",")
    if vals.get("recebido") is not None and ant_r and vals["recebido"] + 0.01 < ant_r and not conf_ok:
        # o total RECEBIDO nunca diminui sozinho (o site e publico): pede confirmacao em vez de sobrescrever
        est["conf"] = {"valor": round(vals["recebido"], 2), "ts": time.time()}
        est["aguardando"] = True
        _salvar(est)
        if enviar_dono:
            enviar_dono(f"🐮 Vaquinha: a Parceira disse que recebemos {brl0(vals['recebido'])}, mas o site mostra {brl0(ant_r)}. Perguntei a ela se é a mais ou o total; nada foi alterado.")
        return (f"Entendi {brl0(vals['recebido'])}, mas antes você tinha dito {brl0(ant_r)} (é o que o site mostra). Esses {brl0(vals['recebido'])} são a MAIS "
                f"(o total ficaria {brl0(ant_r + vals['recebido'])}) ou o total recebido até agora é só {brl0(vals['recebido'])}? Responde: a mais, ou total.")
    if vals.get("recebido") is not None:
        est["arrecadado"] = round(vals["recebido"], 2)
    if vals.get("gasto") is not None:
        est["gasto"] = round(vals["gasto"], 2)
    completo = vals.get("recebido") is not None and vals.get("gasto") is not None or (est.get("falta") == "gasto" and vals.get("gasto") is not None)
    est["aguardando"] = not completo
    est["falta"] = None if completo else ("gasto" if vals.get("recebido") is not None else "recebido")
    est.update({"informado_por": quem, "informado_em": datetime.now().isoformat(timespec="minutes")})
    est.setdefault("historico", []).append({"recebido": est.get("arrecadado"), "gasto": est.get("gasto", 0.0), "quem": quem, "ts": est["informado_em"]})
    est["historico"] = est["historico"][-200:]
    _salvar(est)
    _escrever_total(est)
    ok, saida = (publicar_fn or publicar)()
    est = _estado()
    if ok:
        est["publicado"] = est["arrecadado"]
    else:
        est["ultimo_erro"] = saida
    est["ultimo_deploy"] = time.time()
    _salvar(est)
    meta, r, g = est.get("meta", META), est.get("arrecadado", 0.0), est.get("gasto", 0.0)
    brl = lambda v: f"R$ {v:.2f}".replace(".", ",")
    if enviar_dono:
        enviar_dono(f"🐮 Vaquinha ({quem} informou): recebido {brl(r)} de {brl(meta)}, gasto {brl(g)}, saldo {brl(r - g)} (antes: recebido {brl(ant_r)}, gasto {brl(ant_g)}).")
    if est.get("falta") == "gasto":
        return f"Anotei: recebemos {brl(r)}. E quanto já gastamos até agora?"
    if est.get("falta") == "recebido":
        return f"Anotei: gastamos {brl(g)}. E quanto já recebemos até agora?"
    return f"Anotado! Recebido {brl(r)} de {brl(meta)}, gasto {brl(g)}. " + ("Site atualizado. ✅" if ok else "O site ainda não atualizou (o Dono já foi avisado).")


def tem_rotulo(texto):
    """A frase diz o que o numero e (recebemos, gastamos, saldo...)? Sem rotulo, um numero solto responde a ultima pergunta."""
    return bool(re.search(r"receb|gast|saldo|na conta|temos|\btem\b|entrou|arrecad|sobr|saiu|paguei|pagamos", (texto or "").lower()))


def confirmando():
    return bool(_estado().get("conf"))


def resolver_confirmacao(texto, publicar_fn=None, enviar_dono=None):
    """A Parceira respondeu 'a mais' ou 'total' ao conflito de valores. Devolve a resposta a ela, ou None se nao deu para entender."""
    est = _estado()
    c = est.get("conf")
    if not c:
        return None
    t = (texto or "").lower()
    if re.search(r"a mais|al[eé]m|novos?|\bmais\b", t):
        total = round(est.get("arrecadado", 0.0) + c["valor"], 2)
    elif re.search(r"total|mesmo|isso|\bs[óo]\b|certo|\bsim\b|correto", t):
        total = c["valor"]
    else:
        return None
    est.pop("conf", None)
    est["conf_ok"] = True
    _salvar(est)
    return registrar_valores({"recebido": total, "gasto": None}, "Parceira", publicar_fn, enviar_dono, rotulado=True)


def registrar_saldo(valor, quem="Parceira", publicar_fn=None, enviar_dono=None, agora=None):
    return registrar_valores({"recebido": valor}, quem, publicar_fn, enviar_dono)


def publicar_escritorio(horas=1.0):
    """Mostra o escritorio (animacao ILUSTRATIVA, sem dado real dos agentes) no site da vaquinha por `horas`: gera escritorio.html a partir da tela
    do Braniac (so modo demo, em festa, com as placas) e grava escritorio_ate no total.json; o site se esconde sozinho quando o prazo acaba."""
    from pathlib import Path
    h = (Path(__file__).resolve().parent / "ui" / "sauraki.html").read_text(encoding="utf-8")
    for a, b in (("/[?&]demo=1/.test(location.search)", "true"),
                 ("if(DEMO){snap=demoSnap();painel();return}", "if(DEMO){snap=demoSnap();snap.festa_ate=Date.now()/1000+3600;painel();return}"),
                 ('"erro","desconectado","ocioso"', '"ocioso","ocioso","ocioso"'),   # no site publico nao aparece agente com erro/desconectado
                 ("</head>", "<style>aside{display:none!important}#app{display:block!important}#stage{height:100vh!important}</style></head>"),   # so o palco, sem painel lateral
                 ("cols=W<700?2:4,rows=W<700?4:2", "cols=4,rows=2"),
                 ("H*(festa()?.46:.24)", "H*.58"),            # no site a area da festa e a maior parte da tela
                 ('<div id="demo">DADOS SIMULADOS</div>', '<div id="demo">ANIMAÇÃO ILUSTRATIVA</div>')):
        if a not in h:
            return False, "tela do escritorio mudou: " + a[:30]
        h = h.replace(a, b, 1)
    (SITE / "escritorio.html").write_text(h, encoding="utf-8")
    est = _estado()
    est["escritorio_ate"] = int(time.time() + horas * 3600)
    _salvar(est)
    _escrever_total(est)
    return publicar()
