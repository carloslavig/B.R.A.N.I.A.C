# -*- coding: utf-8 -*-
"""Gmail do Dono, SOMENTE LEITURA (escopo gmail.readonly): ver nao lidas, buscar e ler um e-mail. NAO envia, apaga nem altera nada.

Login: API oficial do Google (OAuth 'App para computador', PKCE, redirect http://127.0.0.1:8765/email/callback). O Dono cria o cliente OAuth no
Google Cloud (passo a passo em http://127.0.0.1:8765/email), cola o Client ID e o segredo la e aprova UMA vez. Tokens e segredo ficam so em
braniac/data/gmail.json (acesso restrito ao usuario do Windows).

PRIVACIDADE (regra do Dono): o conteudo dos e-mails NUNCA vai para IA online. Estas funcoes devolvem texto para o PROPRIO Dono (resposta direta
ou saida_direta); nada aqui passa pelo roteador de IAs.
"""
import base64, email.header, email.utils, hashlib, html, json, re, secrets, time, urllib.parse
import requests
from .store import DATA

ARQ = DATA / "gmail.json"
REDIRECT = "http://127.0.0.1:8765/email/callback"
ESCOPO = "https://www.googleapis.com/auth/gmail.readonly"
API = "https://gmail.googleapis.com/gmail/v1/users/me"
HTTP = requests          # injetavel nos testes


class GmailErro(Exception):
    pass


# ---------- estado salvo ----------

def _ler():
    try:
        return json.loads(ARQ.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _gravar(d):
    DATA.mkdir(exist_ok=True)
    ARQ.write_text(json.dumps(d), encoding="utf-8")


def definir_cliente(client_id, client_secret):
    cid, sec = (client_id or "").strip(), (client_secret or "").strip()
    if not cid.endswith(".apps.googleusercontent.com") or len(sec) < 10:
        raise GmailErro("o Client ID deve terminar com .apps.googleusercontent.com e o segredo (Client secret) precisa ser colado inteiro")
    d = _ler()
    d.update(client_id=cid, client_secret=sec)
    d.pop("refresh_token", None)          # cliente novo = login novo
    d.pop("access_token", None)
    _gravar(d)


def logado():
    d = _ler()
    return bool(d.get("client_id") and d.get("refresh_token"))


def estado():
    d = _ler()
    return {"cliente": bool(d.get("client_id") and d.get("client_secret")), "logado": logado(), "conta": d.get("conta")}


def configurado():
    return logado()


COMO_CONECTAR = "Falta conectar o Gmail (leitura). Abra http://127.0.0.1:8765/email no PC: tem o passo a passo e leva uns 5 minutos."


# ---------- login (OAuth, PKCE) ----------

def url_login():
    d = _ler()
    if not (d.get("client_id") and d.get("client_secret")):
        raise GmailErro("antes, cole o Client ID e o segredo do Google em http://127.0.0.1:8765/email")
    verificador = secrets.token_urlsafe(64)
    d["verificador"], d["estado"] = verificador, secrets.token_urlsafe(16)
    _gravar(d)
    desafio = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b"=").decode()
    q = urllib.parse.urlencode({"client_id": d["client_id"], "redirect_uri": REDIRECT, "response_type": "code", "scope": ESCOPO,
                                "access_type": "offline", "prompt": "consent", "code_challenge_method": "S256", "code_challenge": desafio,
                                "state": d["estado"]})
    return "https://accounts.google.com/o/oauth2/v2/auth?" + q


def concluir_login(codigo, estado_recebido):
    d = _ler()
    if not codigo or estado_recebido != d.get("estado"):
        raise GmailErro("retorno do login inválido")
    r = HTTP.post("https://oauth2.googleapis.com/token", data={
        "grant_type": "authorization_code", "code": codigo, "redirect_uri": REDIRECT, "client_id": d["client_id"],
        "client_secret": d["client_secret"], "code_verifier": d.get("verificador", "")}, timeout=20)
    if r.status_code != 200:
        raise GmailErro(f"o Google recusou o login ({r.status_code})")
    _guardar_token(r.json())
    try:
        perfil = HTTP.get(API + "/profile", headers={"Authorization": "Bearer " + _ler()["access_token"]}, timeout=20).json()
        d = _ler()
        d["conta"] = perfil.get("emailAddress")
        _gravar(d)
    except Exception:
        pass


def _guardar_token(j):
    d = _ler()
    d["access_token"] = j["access_token"]
    d["expira"] = time.time() + int(j.get("expires_in", 3600)) - 60
    if j.get("refresh_token"):
        d["refresh_token"] = j["refresh_token"]
    d.pop("verificador", None)
    _gravar(d)


def _token():
    d = _ler()
    if not d.get("refresh_token"):
        raise GmailErro(COMO_CONECTAR)
    if d.get("access_token") and time.time() < d.get("expira", 0):
        return d["access_token"]
    r = HTTP.post("https://oauth2.googleapis.com/token", data={
        "grant_type": "refresh_token", "refresh_token": d["refresh_token"], "client_id": d["client_id"], "client_secret": d["client_secret"]}, timeout=20)
    if r.status_code != 200:
        raise GmailErro("o login do Gmail expirou (no modo de teste do Google ele vale só 7 dias: na tela de consentimento clique em “Publicar app”). "
                        "Entre de novo em http://127.0.0.1:8765/email/login")
    _guardar_token(r.json())
    return _ler()["access_token"]


def _get(caminho, **params):
    r = HTTP.get(API + caminho, params=params, headers={"Authorization": "Bearer " + _token()}, timeout=25)
    if r.status_code == 403 and "insufficient" in r.text.lower():
        raise GmailErro("o Gmail recusou: falta a permissão de leitura. Entre de novo em /email/login e marque a permissão.")
    if r.status_code == 403 or r.status_code == 429:
        raise GmailErro("o Gmail limitou o acesso agora (cota). Tente de novo em alguns minutos.")
    if r.status_code != 200:
        raise GmailErro(f"o Gmail respondeu {r.status_code}")
    return r.json()


# ---------- leitura ----------

def _cabecalho(msg, nome):
    for h in (msg.get("payload") or {}).get("headers", []):
        if h.get("name", "").lower() == nome.lower():
            partes = email.header.decode_header(h.get("value", ""))
            return "".join(p.decode(c or "utf-8", "replace") if isinstance(p, bytes) else p for p, c in partes).strip()
    return ""


def _data(msg):
    try:
        return email.utils.parsedate_to_datetime(_cabecalho(msg, "Date")).astimezone().strftime("%d/%m %H:%M")
    except (TypeError, ValueError):
        return ""


def _remetente(msg):
    nome, end = email.utils.parseaddr(_cabecalho(msg, "From"))
    return (nome or end or "?").strip()


def _texto(parte):
    """Texto do e-mail: prefere text/plain; senao tira as tags do HTML."""
    if not parte:
        return ""
    tipo = parte.get("mimeType", "")
    dados = (parte.get("body") or {}).get("data")
    if dados and tipo in ("text/plain", "text/html"):
        bruto = base64.urlsafe_b64decode(dados + "=" * (-len(dados) % 4)).decode("utf-8", "replace")
        if tipo == "text/html":
            bruto = re.sub(r"(?is)<(script|style).*?</\1>", " ", bruto)
            bruto = html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"(?i)<br\s*/?>|</p>", "\n", bruto)))
            bruto = re.sub(r"[ \t\xa0]+", " ", bruto)
            bruto = re.sub(r" *\n *", "\n", bruto)
        return bruto
    partes = parte.get("parts") or []
    plano = [p for p in partes if p.get("mimeType") == "text/plain"]
    for p in (plano or partes):
        t = _texto(p)
        if t.strip():
            return t
    return ""


def _resumo(msg, i=None):
    pref = f"{i}) " if i is not None else "• "
    nao_lida = "🔵 " if "UNREAD" in (msg.get("labelIds") or []) else ""
    return f"{pref}{nao_lida}{_data(msg)} · {_remetente(msg)[:40]} — {(_cabecalho(msg, 'Subject') or '(sem assunto)')[:90]}"


ULTIMA_LISTA = []        # ids da ultima lista mostrada: 'le o 2' abre o segundo


def _listar(consulta, n, titulo):
    ids = [m["id"] for m in _get("/messages", q=consulta, maxResults=n).get("messages", [])]
    ULTIMA_LISTA[:] = ids
    if not ids:
        return f"{titulo}: nada encontrado."
    linhas = []
    for i, id_ in enumerate(ids, 1):
        m = _get(f"/messages/{id_}", format="metadata", metadataHeaders=["From", "Subject", "Date"])
        linhas.append(_resumo(m, i))
    return f"{titulo} ({len(ids)}):\n" + "\n".join(linhas) + "\n\nPara abrir um: «lê o e-mail 2»."


def nao_lidas(n=8):
    return _listar("is:unread in:inbox", n, "E-mails não lidos")


def buscar(consulta, n=8):
    """Aceita a sintaxe do Gmail (from:, subject:, after:...) ou texto livre."""
    consulta = (consulta or "").strip()
    if not consulta:
        raise GmailErro("o que devo procurar no e-mail?")
    return _listar(consulta, n, f"E-mails sobre «{consulta[:50]}»")


def ler(ref, max_chars=2500):
    """ref = numero da ultima lista (1, 2...) ou id da mensagem."""
    ref = str(ref).strip()
    if ref.isdigit() and 1 <= int(ref) <= len(ULTIMA_LISTA):
        ref = ULTIMA_LISTA[int(ref) - 1]
    elif ref.isdigit():
        raise GmailErro("esse número não está na última lista; peça os e-mails de novo")
    m = _get(f"/messages/{ref}", format="full")
    corpo = re.sub(r"\n{3,}", "\n\n", _texto(m.get("payload")).strip())
    anexos = [p.get("filename") for p in (m.get("payload", {}).get("parts") or []) if p.get("filename")]
    return (f"De: {_remetente(m)}\nAssunto: {_cabecalho(m, 'Subject') or '(sem assunto)'}\nData: {_data(m)}\n\n{corpo[:max_chars] or '(sem texto)'}"
            + (f"\n\n[anexos: {', '.join(anexos)}]" if anexos else "") + ("\n…(cortado)" if len(corpo) > max_chars else ""))


# ---------- vagas de emprego (criterio do Dono: SO remoto e salario >= R$ 5 mil/mes) ----------
# Filtro 100% local (regex), sem IA: o conteudo do e-mail nao sai do PC.

CONSULTA_VAGAS = ("newer_than:{dias}d (vaga OR vagas OR emprego OR job OR jobs OR hiring OR oportunidade OR position OR remote OR remoto "
                  "OR from:linkedin.com OR from:indeed.com OR from:gupy.io OR from:glassdoor.com OR from:catho.com.br OR from:infojobs.com.br "
                  "OR from:remoteok.com OR from:weworkremotely.com OR from:wellfound.com OR from:vagas.com.br) -in:sent -in:spam")
REMOTO = re.compile(r"\b(?:remot[oa]s?|remote|100\s*%\s*(?:remot\w*|home\s*office)|home[\s-]*office|trabalho\s+a\s+dist[âa]ncia|"
                    r"work\s+from\s+(?:home|anywhere)|anywhere|teletrabalho|wfh)\b", re.I)
NAO_REMOTO = re.compile(r"\b(?:presencial|on[\s-]?site|in[\s-]?office|h[íi]brid[oa]|hybrid)\b", re.I)
SALARIO_MIN_BRL = 5000
MOEDA_FORTE = {"usd": 5.0, "us$": 5.0, "$": 5.0, "eur": 5.5, "€": 5.5, "gbp": 6.5, "£": 6.5}   # cambio aproximado, so p/ comparar com 5 mil
_VALOR = re.compile(r"(?P<moeda>R\$|US\$|USD|EUR|GBP|€|£|\$)\s?(?P<num>\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d{1,2})?)\s*(?P<k>k|mil)?"
                    r"(?:\s*(?:-|–|a|to|até)\s*(?:R\$|US\$|USD|EUR|€|£|\$)?\s?\d[\d.,]*\s*(?:k|mil)?)?"
                    r"(?P<per>\s*(?:/|por|per|an?)\s*(?:h|hr|hora|hour|m[êe]s|month|mo|ano|year|yr|annum))?", re.I)


def _numero(s):
    s = s.strip()
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", s):
        return float(re.sub(r"[.,]", "", s))
    return float(s.replace(",", "."))


def salarios_mensais_brl(texto):
    """Valores de salario achados no texto, convertidos (aprox.) para R$/mes. Lista vazia = salario nao informado."""
    out = []
    for m in _VALOR.finditer(texto or ""):
        try:
            v = _numero(m["num"])
        except ValueError:
            continue
        if m["k"]:
            v *= 1000
        per = (m["per"] or "").lower()
        if re.search(r"\b(?:h|hr|hora|hour)\b", per):
            v *= 160
        elif re.search(r"ano|year|yr|annum", per):
            v /= 12
        elif not per and v >= 40000:          # valor grande sem periodo: provavelmente anual
            v /= 12
        moeda = m["moeda"].lower()
        v *= MOEDA_FORTE.get(moeda, 1.0) if moeda != "r$" else 1.0
        if v >= 300:                           # descarta precos pequenos (cursos, assinaturas)
            out.append(round(v))
    return out


def avaliar_vaga(texto):
    """('ok'|'sem_salario'|'fora', motivo). Remoto obrigatorio; salario >= 5 mil/mes (quando informado)."""
    t = texto or ""
    if not REMOTO.search(t):
        return "fora", "não diz que é remota"
    if NAO_REMOTO.search(t) and not re.search(r"100\s*%\s*remot|fully\s+remote|totalmente\s+remot", t, re.I):
        return "fora", "presencial/híbrida"
    sal = salarios_mensais_brl(t)
    if not sal:
        return "sem_salario", "remota, salário não informado"
    if max(sal) >= SALARIO_MIN_BRL:
        return "ok", f"remota, ~R$ {max(sal):,.0f}/mês".replace(",", ".")
    return "fora", f"salário abaixo de 5 mil (~R$ {max(sal):,.0f}/mês)".replace(",", ".")


def vagas(dias=7, n=25):
    """E-mails de vaga dos ultimos dias filtrados pelo criterio do Dono (remoto + salario >= 5 mil)."""
    ids = [m["id"] for m in _get("/messages", q=CONSULTA_VAGAS.format(dias=int(dias)), maxResults=n).get("messages", [])]
    boas, sem_sal, fora = [], [], 0
    for id_ in ids:
        m = _get(f"/messages/{id_}", format="full")
        texto = _cabecalho(m, "Subject") + "\n" + _texto(m.get("payload"))
        veredito, motivo = avaliar_vaga(texto)
        if veredito == "ok":
            boas.append((id_, m, motivo))
        elif veredito == "sem_salario":
            sem_sal.append((id_, m, motivo))
        else:
            fora += 1
    ULTIMA_LISTA[:] = [i for i, _, _ in boas + sem_sal]
    if not ids:
        return f"Nenhum e-mail de vaga nos últimos {dias} dias."
    linhas, i = [], 1
    if boas:
        linhas.append("✅ Remotas com salário ≥ R$ 5 mil:")
        for _, m, motivo in boas:
            linhas.append(_resumo(m, i) + f"  [{motivo}]")
            i += 1
    if sem_sal:
        linhas.append(("\n" if boas else "") + "🟡 Remotas sem salário no e-mail (vale conferir):")
        for _, m, motivo in sem_sal:
            linhas.append(_resumo(m, i))
            i += 1
    if not (boas or sem_sal):
        linhas.append("Nenhuma vaga remota com salário ≥ R$ 5 mil.")
    linhas.append(f"\n({len(ids)} e-mails de vaga analisados nos últimos {dias} dias; {fora} descartados: presencial/híbrida, sem ser remota ou salário baixo.)")
    if boas or sem_sal:
        linhas.append("Para abrir um: «lê o e-mail 2».")
    return "Vagas no e-mail (critério: só remoto, salário ≥ 5 mil)\n" + "\n".join(linhas)
