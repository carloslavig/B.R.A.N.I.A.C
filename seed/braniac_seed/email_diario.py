# -*- coding: utf-8 -*-
"""RESUMO DIARIO DO E-MAIL de CADA PESSOA (opcional). Nada aqui e do Carlos: cada pessoa conecta o proprio Gmail e define o horario.
- SOMENTE LEITURA (escopo gmail.readonly): le cabecalhos e o comeco do texto; nunca envia, apaga ou altera.
- 100% LOCAL: o conteudo dos e-mails NUNCA vai para IA nenhuma (filtro por palavras), e o resumo so e entregue a PESSOA (Telegram dela, se pareado, e na tela do assistente).
- Login pela API oficial do Google: a pessoa cria o proprio 'ID do cliente OAuth' (app para computador) e cola aqui; tokens e segredo ficam no cofre do Windows.
- Aviso de oportunidade de TRABALHO com PRAZO: entregue SO a pessoa (Telegram dela e tela do assistente). Avisar terceiros (ex.: companheira) nao esta ligado:
  cada pessoa decide e isso exigira um canal proprio dela (campo reservado 'contatos_aviso')."""
import base64, hashlib, json, re, secrets, threading, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime
from . import cofre, paths, remoto

ESCOPO = "https://www.googleapis.com/auth/gmail.readonly"
API = "https://gmail.googleapis.com/gmail/v1/users/me"
AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
PADRAO = {"client_id": "", "hora_resumo": 7, "avisos_trabalho": True, "resumo_ativo": True, "contatos_aviso": [], "alertados": [], "ultimo_resumo": "", "ultima_checagem": 0}

PRAZO = re.compile(r"\b(?:prazo|deadline|at[ée]\s+(?:o\s+dia\s+)?\d{1,2}(?:[/.]\d{1,2})?|inscri[cç][oõ]es?\s+(?:at[ée]|abertas)|due\s+(?:by|on|date)|apply\s+by|"
                   r"encerra(?:m)?\s+(?:em|dia|hoje|amanh[ãa])|vence(?:m)?\s+(?:em|dia|hoje|amanh[ãa])|[uú]ltimos?\s+dias|expira)\b", re.I)
TRABALHO = re.compile(r"\b(?:vaga|vagas|emprego|contrata[cç][ãa]o|processo\s+seletivo|entrevista|oportunidade|proposta|freelance|freela|job|hiring|position|"
                      r"recrutador|recruiter|candidatura|curr[ií]culo|projeto|or[çc]amento|contrato)\b", re.I)
RUIDO = re.compile(r"\b(?:unsubscribe|descadastr|newsletter|promo[cç][ãa]o|cupom|desconto|black\s*friday|oferta)\b", re.I)


class EmailErro(RuntimeError):
    pass


# ---------- configuracao ----------

def _arq():
    return paths.arquivo("email_diario.json")


def config():
    try:
        return {**PADRAO, **json.loads(_arq().read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return dict(PADRAO)


def _salvar(c):
    _arq().write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")


def configurar(client_id=None, client_secret=None, hora_resumo=None, avisos_trabalho=None, resumo_ativo=None, contatos_aviso=None):
    c = config()
    if client_id is not None:
        c["client_id"] = client_id.strip()
    if client_secret:
        cofre.guardar("gmail_secret", client_secret.strip())
    if hora_resumo is not None:
        h = int(hora_resumo)
        if not 0 <= h <= 23:
            raise EmailErro("hora inválida (0 a 23)")
        c["hora_resumo"] = h
    if avisos_trabalho is not None:
        c["avisos_trabalho"] = bool(avisos_trabalho)
    if resumo_ativo is not None:
        c["resumo_ativo"] = bool(resumo_ativo)
    if contatos_aviso is not None:
        c["contatos_aviso"] = [str(x).strip() for x in contatos_aviso if str(x).strip()][:5]
    _salvar(c)
    return estado()


def estado():
    c = config()
    try:
        tem_segredo = cofre.tem("gmail_secret")
        logado = cofre.tem("gmail_token")
    except cofre.CofreErro:
        tem_segredo = logado = False
    return {"configurado": bool(c["client_id"] and tem_segredo), "logado": logado, "hora_resumo": c["hora_resumo"], "avisos_trabalho": c["avisos_trabalho"],
            "resumo_ativo": c["resumo_ativo"], "contatos_aviso": c["contatos_aviso"], "ultimo_resumo": c["ultimo_resumo"]}


def desconectar():
    for k in ("gmail_token", "gmail_secret"):
        try:
            cofre.remover(k)
        except cofre.CofreErro:
            pass
    c = config()
    c["client_id"] = ""
    _salvar(c)


# ---------- login OAuth (PKCE, so leitura) ----------
_PENDENTE = {}


def url_login(redirect):
    e = estado()
    if not e["configurado"]:
        raise EmailErro("Cole primeiro o ID do cliente e o segredo do Google.")
    verificador = secrets.token_urlsafe(48)
    desafio = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b"=").decode()
    estado_ = secrets.token_urlsafe(16)
    _PENDENTE.clear()
    _PENDENTE.update(estado=estado_, verificador=verificador, redirect=redirect, ate=time.time() + 600)
    q = {"client_id": config()["client_id"], "redirect_uri": redirect, "response_type": "code", "scope": ESCOPO, "access_type": "offline",
         "prompt": "consent", "state": estado_, "code_challenge": desafio, "code_challenge_method": "S256"}
    return AUTH + "?" + urllib.parse.urlencode(q)


def _post(url, dados, post=None):
    if post:
        return post(url, dados)
    req = urllib.request.Request(url, urllib.parse.urlencode(dados).encode())
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise EmailErro(f"o Google recusou ({e.code}): confira o ID/segredo e se o app está em modo teste com o seu e-mail adicionado") from e


def concluir_login(codigo, estado_recebido, post=None):
    p = dict(_PENDENTE)
    if not p or time.time() > p["ate"] or not secrets.compare_digest(p["estado"], estado_recebido or ""):
        raise EmailErro("Login expirou ou veio de outra origem. Tente de novo.")
    _PENDENTE.clear()
    j = _post(TOKEN, {"client_id": config()["client_id"], "client_secret": cofre.ler("gmail_secret"), "code": codigo, "code_verifier": p["verificador"],
                      "redirect_uri": p["redirect"], "grant_type": "authorization_code"}, post)
    _guardar_token(j)


def _guardar_token(j, antigo=None):
    atual = antigo or {}
    novo = {"access_token": j["access_token"], "refresh_token": j.get("refresh_token") or atual.get("refresh_token", ""), "expira": time.time() + int(j.get("expires_in", 3000)) - 60}
    cofre.guardar("gmail_token", json.dumps(novo))
    return novo


def _token(post=None):
    bruto = cofre.ler("gmail_token")
    if not bruto:
        raise EmailErro("Gmail não conectado.")
    t = json.loads(bruto)
    if time.time() < t["expira"]:
        return t["access_token"]
    j = _post(TOKEN, {"client_id": config()["client_id"], "client_secret": cofre.ler("gmail_secret"), "refresh_token": t["refresh_token"], "grant_type": "refresh_token"}, post)
    return _guardar_token(j, t)["access_token"]


def _get(caminho, get=None, **params):
    if get:
        return get(caminho, params)
    url = API + caminho + "?" + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + _token()})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


# ---------- resumo e avisos (tudo local) ----------

def promissor(assunto, texto=""):
    """(True, prazo) se parece oportunidade de TRABALHO com PRAZO. Palavras-chave, sem IA."""
    alvo = f"{assunto}\n{texto}"
    if not TRABALHO.search(alvo) or RUIDO.search(assunto):
        return False, ""
    m = PRAZO.search(alvo)
    return (True, m.group(0)) if m else (False, "")


def _cab(msg, nome):
    for h in msg.get("payload", {}).get("headers", []):
        if h["name"].lower() == nome.lower():
            return h["value"]
    return ""


def emails_do_dia(horas=24, n=60, get=None):
    dias = max(1, int(horas / 24 + 0.99))
    ids = [m["id"] for m in _get("/messages", get, q=f"in:inbox newer_than:{dias}d", maxResults=n).get("messages", [])]
    corte, out = time.time() - horas * 3600, []
    for i in ids:
        m = _get(f"/messages/{i}", get, format="metadata", metadataHeaders=["From", "Subject", "Date"])
        if int(m.get("internalDate", 0)) / 1000 >= corte:
            rem = re.sub(r"<.*?>", "", _cab(m, "From")).strip(' "')[:40] or "(sem remetente)"
            out.append((i, rem, (_cab(m, "Subject") or "(sem assunto)")[:90], "UNREAD" in (m.get("labelIds") or [])))
    return out


def resumo_emails(horas=24, get=None):
    msgs = emails_do_dia(horas, get=get)
    if not msgs:
        return "📧 Nenhum e-mail novo nas últimas 24 h."
    prom = [(r, a, p) for _, r, a, _ in msgs for ok, p in [promissor(a)] if ok]
    ruido = sum(1 for _, _, a, _ in msgs if RUIDO.search(a))
    linhas = [f"📧 {len(msgs)} e-mails nas últimas 24 h ({sum(1 for m in msgs if m[3])} não lidos; ~{ruido} promoções/newsletters)."]
    if prom:
        linhas.append("⭐ Possíveis oportunidades com prazo:")
        linhas += [f"  • {r} — {a} [{p}]" for r, a, p in prom[:5]]
    principais = [(r, a) for _, r, a, _ in msgs if not RUIDO.search(a)][:8]
    if principais:
        linhas.append("Principais:")
        linhas += [f"  • {r} — {a}" for r, a in principais]
    return "\n".join(linhas)


def verificar_promissores(avisar, get=None):
    """Avisa UMA vez por e-mail de trabalho com prazo (guarda os ids). `avisar(texto)` entrega so a pessoa (e contatos que ela cadastrou)."""
    c = config()
    if not c["avisos_trabalho"]:
        return 0
    vistos, novos = set(c["alertados"]), 0
    for i, rem, assunto, _ in emails_do_dia(24, get=get):
        if i in vistos:
            continue
        ok, prazo = promissor(assunto)
        if not ok:
            continue
        avisar(f"📌 E-mail de trabalho com prazo ({prazo}): {rem} — {assunto}. Vale conferir na caixa de entrada.")
        vistos.add(i)
        novos += 1
    c = config()
    c["alertados"] = list(vistos)[-300:]
    _salvar(c)
    return novos


def entregar(texto):
    """Entrega a PESSOA (Telegram dela, se pareado). Sempre deixa o texto na tela do assistente (campo ultimo_resumo)."""
    c = config()
    c["ultimo_resumo"] = f"{datetime.now():%d/%m %H:%M}\n{texto}"[:3000]
    _salvar(c)
    try:
        remoto.avisar_dono(texto)
    except Exception:
        pass


def tick(agora=None, avisar=entregar, get=None):
    """Chamado a cada ~10 min: resumo diario na hora que a pessoa escolheu (uma vez por dia) e checagem de oportunidades 1x/hora (7h-22h)."""
    if not estado()["logado"]:
        return
    agora = agora or datetime.now()
    c = config()
    hoje = agora.strftime("%Y-%m-%d")
    if c["resumo_ativo"] and agora.hour >= c["hora_resumo"] and c.get("ultimo_dia") != hoje:
        avisar("Bom dia! Resumo dos seus e-mails:\n" + resumo_emails(get=get))
        c = config()
        c["ultimo_dia"] = hoje
        _salvar(c)
    c = config()
    if 7 <= agora.hour < 22 and agora.timestamp() - c.get("ultima_checagem", 0) > 3300:
        c["ultima_checagem"] = agora.timestamp()
        _salvar(c)
        verificar_promissores(avisar, get=get)


def iniciar(intervalo_s=600):
    def laco():
        while True:
            try:
                tick()
            except Exception:
                pass
            time.sleep(intervalo_s)
    threading.Thread(target=laco, daemon=True, name="email-diario").start()
