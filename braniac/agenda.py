# -*- coding: utf-8 -*-
"""AGENDA DO DONO (pedido de 14/10/2026): o Jarvis organiza tarefas, compromissos e a rotina dele.
100% local (data/agenda.json), sem IA no caminho: o modelo so chama a ferramenta 'agenda' com os campos; aqui se interpreta a data
('amanha 14h', '15/10 9:30', 'segunda 10h', ISO), se repete (diario, dias uteis, semanal, mensal), se acham horarios livres e se
mandam LEMBRETES ao Dono no WhatsApp (pela rotina, a cada ~10 min). A agenda do dia entra no bom dia falado das 6h."""
import json
import os
import re
import threading
import time
import unicodedata
import uuid
from datetime import date, datetime, timedelta

from .store import DATA

ARQ = DATA / "agenda.json"
_LOCK_LEMBRETES = threading.Lock()
REPETICOES = ("", "diario", "dias_uteis", "semanal", "mensal")
DIAS_SEMANA = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
DIA_COMECA, DIA_TERMINA = 8, 22          # janela usada para achar horarios livres
LEMBRAR_PADRAO = 15                      # minutos antes


def _norm(x):
    return "".join(c for c in unicodedata.normalize("NFD", str(x or "").lower()) if unicodedata.category(c) != "Mn").strip()


def _ler():
    try:
        return json.loads(ARQ.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _gravar(itens):
    DATA.mkdir(exist_ok=True)
    tmp = ARQ.with_suffix(".tmp")
    tmp.write_text(json.dumps(itens, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(ARQ)


# ---------- datas em portugues ----------

def _hora(txt):
    """'14h', '14:30', '14h30', '9 da manha', '8 da noite' -> (h, m) ou None."""
    m = re.search(r"\b(\d{1,2})\s*(?:h|:|horas?)\s*(\d{2})?\b(?:\s*(?:da|de)\s*(manha|tarde|noite))?", txt) or \
        re.search(r"\b(?:as|às)\s*(\d{1,2})()\b(?:\s*(?:da|de)\s*(manha|tarde|noite))?", txt)
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    if m.group(3) in ("tarde", "noite") and h < 12:
        h += 12
    return (h, mi) if h < 24 and mi < 60 else None


def interpretar_quando(texto, agora=None):
    """Texto livre -> (date|None, (h, m)|None). Sem data e sem hora -> (None, None) = tarefa sem data."""
    agora = agora or datetime.now()
    t = _norm(texto)
    if not t:
        return None, None
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})(?:[ t](\d{2}):(\d{2}))?", t)
    if m:
        d = date(int(m[1]), int(m[2]), int(m[3]))
        return d, ((int(m[4]), int(m[5])) if m[4] else _hora(t[m.end():]))
    hora = _hora(t)
    d = None
    m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", t)
    mes = re.search(r"\b(\d{1,2})\s+de\s+(" + "|".join(MESES) + r")\w*(?:\s+de\s+(\d{4}))?", t)
    if not m and mes:
        m = [None, mes[1], str(MESES.index(mes[2]) + 1), mes[3]]
    if m:
        ano = int(m[3]) if m[3] else agora.year
        ano = ano + 2000 if ano < 100 else ano
        d = date(ano, int(m[2]), int(m[1]))
        if not m[3] and d < agora.date():
            d = date(ano + 1, d.month, d.day)
    elif re.search(r"\bdepois de amanha\b", t):
        d = agora.date() + timedelta(days=2)
    elif re.search(r"\bamanha\b", t):
        d = agora.date() + timedelta(days=1)
    elif re.search(r"\bhoje\b", t):
        d = agora.date()
    else:
        for i, nome in enumerate(DIAS_SEMANA):
            if re.search(r"\b" + nome[:3] + r"\w*", t):
                delta = (i - agora.weekday()) % 7
                if delta == 0 and (hora is None or (hora[0], hora[1]) <= (agora.hour, agora.minute)):
                    delta = 7
                d = agora.date() + timedelta(days=delta)
                break
    if d is None and hora:
        d = agora.date() if hora > (agora.hour, agora.minute) else agora.date() + timedelta(days=1)
    return d, hora


def _dia(texto, agora=None):
    agora = agora or datetime.now()
    if not texto:
        return agora.date()
    d, _ = interpretar_quando(texto, agora)
    return d or agora.date()


# ---------- itens e ocorrencias ----------

def _ocorre(item, d):
    if not item.get("data"):
        return False
    ini = date.fromisoformat(item["data"])
    if d < ini or (item.get("ate") and d > date.fromisoformat(item["ate"])):
        return False
    rep = item.get("repetir", "")
    return {"": d == ini, "diario": True, "dias_uteis": d.weekday() < 5,
            "semanal": d.weekday() == ini.weekday(), "mensal": d.day == ini.day}.get(rep, d == ini)


def ocorrencias(d, itens=None):
    """Itens que acontecem no dia d, ordenados por hora (dia inteiro primeiro)."""
    itens = _ler() if itens is None else itens
    oc = [i for i in itens if _ocorre(i, d)]
    return sorted(oc, key=lambda i: i.get("hora") or "00:00")


def _feito(item, d):
    return (d.isoformat() if item.get("data") else "sem-data") in item.get("feitos", [])


def _fmt(item, d=None):
    h = item.get("hora")
    fim = ""
    if h and item.get("duracao"):
        t = datetime.strptime(h, "%H:%M") + timedelta(minutes=int(item["duracao"]))
        fim = "–" + t.strftime("%H:%M")
    rep = {"diario": " 🔁 todo dia", "dias_uteis": " 🔁 dias úteis", "semanal": " 🔁 toda semana", "mensal": " 🔁 todo mês"}.get(item.get("repetir") or "", "")
    marca = "✅" if d and _feito(item, d) else "▫️"
    return f"{marca} {(h + fim + ' ') if h else ''}{item['titulo']}{rep}  [{item['id']}]"


def adicionar(titulo, quando="", duracao=60, repetir="", lembrar=LEMBRAR_PADRAO, notas="", ate="", agora=None):
    agora = agora or datetime.now()
    titulo = (titulo or "").strip()
    if not titulo:
        return "Faltou o que é o compromisso/tarefa."
    repetir = _norm(repetir).replace(" ", "_").replace("dias_util", "dias_uteis").replace("dias_uteiss", "dias_uteis")
    repetir = {"todo_dia": "diario", "diaria": "diario", "diariamente": "diario", "semanalmente": "semanal",
               "toda_semana": "semanal", "mensalmente": "mensal", "todo_mes": "mensal", "nao": "", "nenhum": ""}.get(repetir, repetir)
    if repetir not in REPETICOES:
        return f"Repetição '{repetir}' não existe. Use: diario, dias_uteis, semanal ou mensal."
    d, h = interpretar_quando(quando, agora)
    if repetir and not d:
        d = agora.date()
    item = {"id": uuid.uuid4().hex[:5], "titulo": titulo[:120], "data": d.isoformat() if d else "",
            "hora": f"{h[0]:02d}:{h[1]:02d}" if h else "", "duracao": int(duracao or 0) if h else 0,
            "repetir": repetir, "lembrar": int(lembrar if lembrar is not None else LEMBRAR_PADRAO),
            "notas": (notas or "")[:300], "ate": (_dia(ate, agora).isoformat() if ate else ""),
            "feitos": [], "avisos": [], "criado": time.time()}
    itens = _ler()
    if d and h and not repetir:      # 29/10: 'me lembre antes' logo depois de marcar a reuniao criou um 2o item; mesmo dia/hora e titulo parecido = atualiza o que ja existe
        for o in itens:
            if o.get("data") == item["data"] and o.get("hora") == item["hora"] and not o.get("repetir") and set(_norm(o["titulo"]).split()) & set(_norm(titulo).split()) - {"de", "da", "do", "para", "com"}:
                o.update(titulo=max(o["titulo"], item["titulo"], key=len), duracao=item["duracao"] or o["duracao"], lembrar=item["lembrar"], notas=item["notas"] or o.get("notas", ""))
                _gravar(itens)
                return f"📅 Atualizei o que já estava marcado: {o['titulo']} — {_data_txt(d, agora)} às {item['hora']}. Te lembro {o['lembrar']} min antes. [{o['id']}]"
    conflito = [o for o in ocorrencias(d, itens) if h and o.get("hora") and _sobrepoe(o, item)] if d else []
    itens.append(item)
    _gravar(itens)
    quando_txt = (f"{_data_txt(d, agora)}" + (f" às {item['hora']}" if h else " (dia todo)")) if d else "sem data (lista de tarefas)"
    aviso = f" ⚠️ Bate com: {', '.join(c['titulo'] for c in conflito)}." if conflito else ""
    lembrete = f" Te lembro {item['lembrar']} min antes." if h and item["lembrar"] > 0 else ""
    rep = {"diario": ", todo dia", "dias_uteis": ", dias úteis", "semanal": ", toda semana", "mensal": ", todo mês"}.get(repetir, "")
    return f"📅 Anotado: {titulo} — {quando_txt}{rep}.{lembrete}{aviso} [{item['id']}]"


def _min(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _sobrepoe(a, b):
    a0, b0 = _min(a["hora"]), _min(b["hora"])
    return a0 < b0 + max(b.get("duracao") or 30, 1) and b0 < a0 + max(a.get("duracao") or 30, 1)


def _data_txt(d, agora=None):
    agora = agora or datetime.now()
    delta = (d - agora.date()).days
    nome = {0: "hoje", 1: "amanhã", -1: "ontem"}.get(delta)
    base = f"{DIAS_SEMANA[d.weekday()].replace('terca', 'terça').replace('sabado', 'sábado')} {d.strftime('%d/%m')}"
    return f"{nome} ({base})" if nome else base


def _achar(alvo, itens):
    a = _norm(alvo)
    if not a:
        return []
    por_id = [i for i in itens if i["id"] == a]
    if por_id:
        return por_id
    palavras = a.split()
    return [i for i in itens if all(p in _norm(i["titulo"]) for p in palavras)]


def concluir(alvo, dia="", agora=None):
    agora = agora or datetime.now()
    itens = _ler()
    achados = _achar(alvo, itens)
    if not achados:
        return f"Não achei '{alvo}' na agenda."
    if len(achados) > 1:
        return "Achei mais de um, qual? " + "; ".join(f"{i['titulo']} [{i['id']}]" for i in achados[:6])
    it = achados[0]
    chave = _dia(dia, agora).isoformat() if it.get("data") else "sem-data"
    if chave not in it["feitos"]:
        it["feitos"] = (it["feitos"] + [chave])[-120:]
    _gravar(itens)
    return f"✅ Feito: {it['titulo']}" + (f" ({chave})" if it.get("repetir") else "") + "."


def remover(alvo):
    itens = _ler()
    achados = _achar(alvo, itens)
    if not achados:
        return f"Não achei '{alvo}' na agenda."
    if len(achados) > 1:
        return "Achei mais de um, qual remover? " + "; ".join(f"{i['titulo']} [{i['id']}]" for i in achados[:6])
    _gravar([i for i in itens if i["id"] != achados[0]["id"]])
    return f"🗑️ Removido da agenda: {achados[0]['titulo']}."


def tarefas_sem_data(itens=None):
    itens = _ler() if itens is None else itens
    return [i for i in itens if not i.get("data") and "sem-data" not in i.get("feitos", [])]


def listar(dia="", dias=1, agora=None):
    agora = agora or datetime.now()
    d0 = _dia(dia, agora)
    itens = _ler()
    linhas = []
    for k in range(max(1, min(int(dias or 1), 31))):
        d = d0 + timedelta(days=k)
        oc = ocorrencias(d, itens)
        if oc or int(dias or 1) == 1:
            linhas.append(f"*{_data_txt(d, agora).capitalize()}*")
            linhas += [_fmt(i, d) for i in oc] or ["(dia livre)"]
    pend = tarefas_sem_data(itens)
    if pend:
        linhas.append("*Tarefas sem data:*")
        linhas += [_fmt(i) for i in pend[:15]]
    return "\n".join(linhas) if linhas else "Agenda vazia nesse período."


def livres(dia="", agora=None, minimo=30):
    """Horarios livres do dia (entre 8h e 22h; se for hoje, a partir de agora). Devolve [(ini_min, fim_min)]."""
    agora = agora or datetime.now()
    d = _dia(dia, agora)
    ini = DIA_COMECA * 60
    if d == agora.date():
        ini = max(ini, agora.hour * 60 + agora.minute)
    ocupado = sorted((_min(i["hora"]), _min(i["hora"]) + (i.get("duracao") or 30)) for i in ocorrencias(d) if i.get("hora"))
    buracos, cur = [], ini
    for a, b in ocupado:
        if a - cur >= minimo:
            buracos.append((cur, a))
        cur = max(cur, b)
    if DIA_TERMINA * 60 - cur >= minimo:
        buracos.append((cur, DIA_TERMINA * 60))
    return buracos


def _hm(m):
    return f"{m // 60:02d}:{m % 60:02d}"


def organizar(dia="", agora=None):
    """Material para o Jarvis montar a rotina do dia: o que ja esta marcado, os horarios livres e as tarefas sem data."""
    agora = agora or datetime.now()
    d = _dia(dia, agora)
    l = livres(dia, agora)
    pend = tarefas_sem_data()
    partes = [listar(d.isoformat(), 1, agora)]
    partes.append("Horários livres: " + (", ".join(f"{_hm(a)}–{_hm(b)}" for a, b in l) if l else "nenhum (dia cheio)"))
    if pend:
        partes.append("Para encaixar, use a ação 'adicionar' com hora (e depois 'concluir' a tarefa sem data pelo id), uma de cada vez, "
                      "respeitando os horários livres; proponha ao Dono antes se ele não pediu para já marcar.")
    return "\n".join(partes)


# ---------- lembretes e bom dia ----------

def lembretes(agora, enviar):
    """Chamado pela rotina (~10 min). Avisa o Dono 'lembrar' minutos antes de cada compromisso com hora (uma vez por ocorrencia)."""
    with _LOCK_LEMBRETES:      # 26/10: uma execucao por vez (lembretes chegavam em dobro)
        return _lembretes(agora, enviar)


def _log_envio(msg):
    try:
        with (DATA / "agenda_envios.log").open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} | pid={os.getpid()} | {threading.current_thread().name} | {msg}\n")
    except OSError:
        pass


def _lembretes(agora, enviar):
    itens = _ler()
    mudou, enviados = False, []
    for i in ocorrencias(agora.date(), itens):
        if not i.get("hora") or i.get("lembrar", 0) <= 0 or _feito(i, agora.date()):
            continue
        ini = datetime.combine(agora.date(), datetime.strptime(i["hora"], "%H:%M").time())
        chave = f"{agora.date().isoformat()} {i['hora']}"
        if chave in i.get("avisos", []) or not (ini - timedelta(minutes=i["lembrar"]) <= agora < ini + timedelta(minutes=10)):
            continue
        falta = int((ini - agora).total_seconds() // 60)
        quando = f"daqui a {falta} min ({i['hora']})" if falta > 0 else f"agora ({i['hora']})"
        # reserva ANTES de enviar e grava: se outra thread/processo rodar agora, ve o aviso como ja feito (so desfaz se o envio falhar de verdade)
        i["avisos"] = (i.get("avisos", []) + [chave])[-60:]
        _gravar(itens)
        r = str(enviar(f"⏰ Lembrete: {i['titulo']} — {quando}." + (f"\n{i['notas']}" if i.get("notas") else "")))
        _log_envio(f"{i['titulo']} ({chave}) -> {r[:60]}")
        if not r.startswith("✅"):
            i["avisos"] = [c for c in i["avisos"] if c != chave]
            _gravar(itens)
            continue
        mudou = True
        enviados.append(i["titulo"])
    if mudou:
        _gravar(itens)
    return enviados


def resumo_falado(agora=None):
    """Uma frase para o bom dia: compromissos de hoje e quantas tarefas sem data."""
    agora = agora or datetime.now()
    oc = [i for i in ocorrencias(agora.date()) if not _feito(i, agora.date())]
    pend = tarefas_sem_data()
    if not oc and not pend:
        return ""
    partes = []
    if oc:
        partes.append("Na sua agenda de hoje: " + "; ".join((f"às {i['hora'].replace(':00', ' horas').replace(':', ' e ')}, " if i.get("hora") else "") + i["titulo"]
                                                           for i in oc[:6]) + ".")
    if pend:
        partes.append(f"E você tem {len(pend)} tarefa{'s' if len(pend) > 1 else ''} sem data esperando um horário.")
    return " ".join(partes)


# ---------- ferramenta do Jarvis ----------

def titulo_vazio(titulo):
    """True para titulo sem assunto ('Lembrar', 'Lembrar Dono', 'lembrete', 'tarefa'...): o item seria lixo."""
    t = re.sub(r"[^a-zà-ÿ ]", " ", str(titulo or "").lower())
    resto = [p for p in t.split() if p not in ("me", "lembre", "lembra", "lembrar", "lembrete", "dono", "de", "do", "da", "um", "uma", "o", "a", "para", "pra", "tarefa", "compromisso", "evento", "amanha", "amanhã", "hoje")]
    return len("".join(resto)) < 3


def ferramenta(args, agora=None):
    acao = (args.get("acao") or "listar").strip()
    if acao == "adicionar":
        # modelos as vezes mandam a data em outros campos ('data'/'dia' + 'hora'/'horario'): junta tudo em 'quando' (14/10: item ficou sem data)
        quando = args.get("quando") or " ".join(str(args.get(k) or "") for k in ("data", "dia", "hora", "horario")).strip()
        if titulo_vazio(args.get("titulo", "")):     # 'me lembra amanha' sem dizer do que: nao inventa item, manda perguntar
            return "Falta dizer do que lembrar (e a que horas). NÃO crie nada ainda: pergunte ao Dono 'lembrar de quê?' e espere a resposta."
        return adicionar(args.get("titulo", ""), quando, args.get("duracao", 60), args.get("repetir", ""),
                         args.get("lembrar", LEMBRAR_PADRAO), args.get("notas", ""), args.get("ate", ""), agora)
    if acao == "concluir":
        return concluir(args.get("alvo") or args.get("titulo", ""), args.get("dia", ""), agora)
    if acao == "remover":
        return remover(args.get("alvo") or args.get("titulo", ""))
    if acao == "livres":
        l = livres(args.get("dia", ""), agora)
        return "Horários livres: " + (", ".join(f"{_hm(a)}–{_hm(b)}" for a, b in l) if l else "nenhum.")
    if acao == "organizar":
        return organizar(args.get("dia", ""), agora)
    return listar(args.get("dia", ""), args.get("dias", 1), agora)
