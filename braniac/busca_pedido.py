# -*- coding: utf-8 -*-
"""BUSCA A PEDIDO + PROATIVIDADE (05/11/2026, pedido do Dono). A Mae pediu por audio "quanto custa uma ressonancia em Itabuna". Agora, quando a familia
(ou a Parceira) pede para PROCURAR preco/lugar/telefone, o Jarvis: avisa que vai procurar -> acha os lugares no Google Maps (nome, nota, endereco, TELEFONE) e os precos
que aparecem em paginas da web -> manda tudo com os links. Depois age conforme o nivel de PROATIVIDADE da personalidade (0 a 10, `personalidade.py`):
  0-4  so informa;   5-7  (neutro) PERGUNTA se ela quer que ele mande mensagem aos lugares;   8-10  ja manda mensagem (so aos que tem celular/WhatsApp).
A mensagem ao lugar pergunta valor e datas disponiveis, diz que e um assistente de IA e que NADA sera agendado agora. As respostas dos lugares voltam para quem pediu
(o Jarvis nao responde, nao agenda, nao confirma nada sozinho; marcar exame so com o OK explicito dela).
Equipe (papeis): Faro = Google Maps (`busca_maps`), Garimpo = precos nas paginas (`pesquisa`), Voz = contato com o lugar, Ponte = devolve a resposta a quem pediu.
TRAVAS: so le paginas publicas; consulta sem dado sensivel; nenhum preco inventado (so os escritos na pagina); o contato nao leva nome completo, diagnostico, CPF nem plano;
no maximo 3 lugares por pedido; so manda mensagem a numero de celular; saude: so preco/lugar, nada de diagnostico ou indicacao de tratamento."""
import json
import re
import threading
import time
import unicodedata

from .store import DATA

PEDIDOS = DATA / "busca_pedidos.json"       # oferta pendente por solicitante: {nome_norm: {...}}
CONTATOS = DATA / "busca_contatos.json"     # lugares contatados: {ultimos 8 digitos: {...}}
VALIDADE_S = 24 * 3600
MAX_CONTATOS = 3
PEDE = re.compile(r"(?i)\b(?:procur\w*|pesquis\w*|busc\w*|acha\w*|descobr\w*|ver\s+(?:pra|para)\s+mim|d[aá]\s+(?:pra|para)\s+(?:ver|achar))\b")
TEMA = re.compile(r"(?i)\b(?:quanto|pre[cç]o\w*|valor\w*|custa\w*|onde|cl[ií]nica\w*|lugar\w*|endere[cç]o\w*|telefone\w*|loja\w*|farm[aá]cia\w*|laborat[oó]rio\w*|hospital\w*|consult[oó]rio\w*|exame\w*)\b")
SIM = re.compile(r"(?i)^\W*(?:sim|pode(?:\s+sim)?|quero|claro|manda|fa[cç]a|ok\s+pode|pode\s+mandar|por\s+favor|isso)\b")
NAO = re.compile(r"(?i)^\W*(?:n[aã]o|deixa|deixe|depois)\b")
PRECO = re.compile(r"R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})")
# erros comuns do Whisper em termos de saude (a Tia disse "nossa magnetica")
CORRECOES = [(re.compile(r"(?i)\b(?:nossa|a?\s*ressona\w*|resson\w*)\s+magn[eé]tica\b"), "ressonância magnética"), (re.compile(r"(?i)\bressonancia\b"), "ressonância")]
ROTULOS = {"mainha": "da Mãe", "mae": "da Mãe"}
_fn_pesquisar = None    # testes trocam
_fn_ia = None
_fn_lugares = None
_fn_nivel = None
_lock = threading.RLock()


def _norm(t):
    return "".join(c for c in unicodedata.normalize("NFD", (t or "").lower()) if unicodedata.category(c) != "Mn")


def _ler(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _gravar(p, d):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def nivel():
    """Proatividade 0-10 (a mesma que o Dono ajusta conversando: 'mais proatividade')."""
    if _fn_nivel:
        return _fn_nivel()
    from . import personalidade
    return personalidade.niveis()["proatividade"]


def eh_pedido(texto):
    t = texto or ""
    return 25 < len(t) < 1500 and bool(PEDE.search(t)) and bool(TEMA.search(t))


def _corrigir(t):
    for rx, novo in CORRECOES:
        t = rx.sub(novo, t)
    return t


def cidade_de(texto):
    """Cidade citada no pedido ('em Itabuna'); None se nao houver."""
    m = re.search(r"\b(?:em|de|na|no)\s+([A-ZÀ-Ý][\wà-ÿ]{3,}(?:\s+[A-ZÀ-Ý][\wà-ÿ]+)?)", texto or "")
    return m.group(1) if m else None


def consulta_de(texto, cidade_padrao="Cidade"):
    """Frase de busca limpa a partir do audio transcrito. IA gratis (neutra) corrige a transcricao; sem IA, um recorte simples."""
    t = _corrigir(re.sub(r"\s+", " ", texto or "")).strip()
    try:
        if _fn_ia:
            r = _fn_ia(t)
        else:
            from .router import Router
            r = Router().responder_neutro(
                "Voce transforma o pedido falado (transcrito por audio, pode ter palavras erradas) numa consulta curta para o Google: servico/produto + cidade + 'preco' se pediu valor. "
                "Devolva SO a consulta, sem aspas, ate 10 palavras, em portugues. Nao invente cidade nem servico que nao estejam no texto. Cidade citada: use ela. Sem cidade, use " + cidade_padrao + ".",
                t[:900])[0]
        r = re.sub(r"[\"\n]", " ", (r or "")).strip(" .")
        if 3 <= len(r) <= 120:
            return r
    except Exception:
        pass
    m = re.search(r"(?i)(ressonância magnética[^.?!]*|(?:exame|consulta|cl[ií]nica|farm[aá]cia|loja)[^.?!]*)", t)
    return ((m.group(1) if m else t)[:100] + " preço").strip()


def _precos(texto, n=3):
    vistos = []
    for m in PRECO.finditer(texto or ""):
        v = "R$ " + m.group(1)
        if v not in vistos:
            vistos.append(v)
    return vistos[:n]


def servico_de(consulta, cidade=None):
    """'ressonância magnética ombro direito preço Itabuna' -> 'ressonância magnética ombro direito'."""
    s = re.sub(r"(?i)\b(?:pre[cç]o|valor|quanto custa)\b", "", consulta or "")
    if cidade:
        s = re.sub(re.escape(cidade), "", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip(" ,.-")


# ---------- contato com os lugares (Voz) ----------
def mensagem_ao_lugar(servico, solicitante):
    quem = ROTULOS.get(_norm(solicitante), "do Dono")
    return (f"Olá, tudo bem? Aqui é o Jarvis, assistente de IA {quem}. Estou pesquisando: qual o valor particular de {servico} "
            "e quais as datas disponíveis para realizar? Por enquanto é só uma consulta, nada será agendado agora. Muito obrigado!")


def _chave(fone):
    return re.sub(r"\D", "", fone or "")[-8:]


def contatar(solicitante, lugares, servico, enviar_numero, avisar=None):
    """Manda a pergunta (valor + datas) aos lugares com celular. Devolve os nomes contatados."""
    from . import busca_maps
    feitos = []
    with _lock:
        contatos = _ler(CONTATOS)
        for l in lugares:
            zap = busca_maps.whatsapp_de(l.get("telefone"))
            recente = zap and _chave(zap) in contatos and time.time() - contatos[_chave(zap)]["ts"] < VALIDADE_S
            if not zap or recente or len(feitos) >= MAX_CONTATOS:
                continue
            r = enviar_numero(zap, mensagem_ao_lugar(servico, solicitante))
            if str(r).startswith("✅"):
                contatos[_chave(zap)] = {"nome": l["nome"], "fone": zap, "solicitante": solicitante, "servico": servico, "ts": time.time()}
                feitos.append(l["nome"])
            elif avisar:
                avisar(f"⚠️ Não consegui mandar mensagem para {l['nome']} ({zap}): {str(r)[:100]}")
        _gravar(CONTATOS, contatos)
    return feitos


def resposta_de_lugar(nome_chat, texto):
    """Mensagem recebida de um lugar que contatamos? Devolve (solicitante, texto_para_ele) ou None. Nao responde ao lugar: so repassa."""
    contatos = _ler(CONTATOS)
    achado = None
    d = _chave(nome_chat)
    for k, c in contatos.items():
        if time.time() - c["ts"] > 7 * VALIDADE_S:
            continue
        nome_c = _norm(c["nome"]).split(":")[0].strip()
        if (len(d) >= 8 and d == k) or (len(nome_c) >= 6 and nome_c in _norm(nome_chat)):
            achado = c
    if not achado:
        return None
    msg = re.sub(r"\s+", " ", texto or "").strip()[:500]
    tia = _norm(achado["solicitante"]) in ROTULOS
    return achado["solicitante"], (f"{'Tia, a' if tia else 'A'} {achado['nome']} respondeu: «{msg}». "
                                   "Quer que eu responda alguma coisa? Não marco nada sem a sua confirmação.")


# ---------- resposta ao pedido ----------
def montar_resposta(consulta, fontes, apelido="tia", cidade=None, lugares=None, final=""):
    """Maps primeiro (nome, nota, endereco, telefone); depois precos das paginas (so os escritos nelas). Devolve texto para o WhatsApp."""
    lugares = lugares or []
    if not fontes and not lugares:
        return f"Não consegui achar nada sobre \"{consulta}\" agora, {apelido}. Vou avisar o Dono pra ele ver isso contigo."
    linhas = []
    if lugares:
        linhas.append(f"Achei no Google Maps {len(lugares)} lugar(es) pra \"{consulta}\", {apelido}:")
        for l in lugares[:4]:
            det = " · ".join(x for x in (f"nota {l['nota']}" if l.get("nota") else "", l.get("endereco") or "") if x)
            linhas.append(f"• {l['nome'][:70]}" + (f"\n  {det}" if det else "") + f"\n  📞 {l['telefone'] or 'sem telefone no Maps'}" + (f"\n  {l['url'].split('/data=')[0]}" if l.get("url") else ""))
    cit = lambda f: bool(cidade) and _norm(cidade) in _norm(f.get("texto", ""))
    fontes = sorted(fontes or [], key=lambda f: not cit(f))[:3]
    if fontes:
        linhas.append(("Preços que aparecem em sites" if lugares else f"Achei {len(fontes)} página(s) pra \"{consulta}\", {apelido}") + ":")
        for f in fontes:
            pr = _precos(f.get("texto", ""))
            local = "" if not cidade else (f" (cita {cidade})" if cit(f) else f" (não vi {cidade} na página, pode ser de outra cidade)")
            linhas.append(f"• {(f.get('titulo') or f['url'])[:60]}{local}\n  {f['url']}" + (f"\n  preços na página: {', '.join(pr)}" if pr else "\n  (sem preço na página)"))
    linhas.append("Os valores são os dos sites e podem mudar; confirma por telefone antes de ir.")
    if final:
        linhas.append(final)
    return "\n".join(linhas)


def _final_por_nivel(solicitante, servico, lugares, enviar_numero, avisar):
    """Texto de fecho conforme a proatividade; no nivel 8+ ja contata, no 5-7 guarda a oferta e pergunta."""
    from . import busca_maps
    n = nivel()
    zaps = [l for l in lugares if busca_maps.whatsapp_de(l.get("telefone"))][:MAX_CONTATOS]
    if n <= 4 or not lugares:
        return ""
    if not zaps:
        return "Os telefones que achei são fixos (não dá pra mandar WhatsApp); se quiser, o Dono pode ligar pra perguntar valor e datas."
    if n >= 8:
        feitos = contatar(solicitante, zaps, servico, enviar_numero, avisar)
        if feitos:
            return f"Já mandei mensagem pra {', '.join(feitos)} perguntando o valor e as datas disponíveis. Não marquei nada; te aviso quando responderem."
        return ""
    with _lock:
        d = _ler(PEDIDOS)
        d[_norm(solicitante)] = {"servico": servico, "lugares": zaps, "ts": time.time()}
        _gravar(PEDIDOS, d)
    return f"Quer que eu mande mensagem pra {', '.join(l['nome'] for l in zaps)} perguntando o valor e as datas disponíveis? Só pergunto, não marco nada sem você confirmar."


def confirmacao(solicitante, texto, enviar_numero, avisar=None):
    """Resposta curta (sim/nao) a uma oferta pendente. Devolve o texto a enviar a quem pediu, ou None se nao ha oferta/nao e resposta."""
    t = (texto or "").strip()
    if len(t) > 80:
        return None
    with _lock:
        d = _ler(PEDIDOS)
        o = d.get(_norm(solicitante))
        if not o or time.time() - o["ts"] > VALIDADE_S or not (SIM.match(t) or NAO.match(t)):
            return None
        d.pop(_norm(solicitante))
        _gravar(PEDIDOS, d)
    if NAO.match(t) and not SIM.match(t):
        return "Tudo bem, não mando nada. Se mudar de ideia é só falar. 💛"
    feitos = contatar(solicitante, o["lugares"], o["servico"], enviar_numero, avisar)
    if not feitos:
        return "Não consegui mandar as mensagens agora. Vou avisar o Dono pra ver isso."
    if avisar:
        avisar(f"📨 {solicitante} autorizou: mandei mensagem para {', '.join(feitos)} (valor e datas de {o['servico']}). Nada agendado.")
    return f"Mandei mensagem pra {', '.join(feitos)} perguntando o valor e as datas. Assim que responderem eu te conto. Não marquei nada."


def _trabalho(nome, texto, enviar, avisar, enviar_numero):
    texto = _corrigir(texto)
    consulta = consulta_de(texto)
    cidade = cidade_de(texto) or cidade_de(consulta)
    servico = servico_de(consulta, cidade)
    lugares, fontes = [], []
    try:
        lugares = (_fn_lugares or __import__("braniac.busca_maps", fromlist=["x"]).lugares)(f"{servico} {cidade or ''}".strip(), 5)
    except Exception as e:
        if avisar:
            avisar(f"⚠️ Google Maps falhou para {nome} (\"{consulta}\"): {str(e)[:100]}")
    pesq = _fn_pesquisar or (lambda c, n: __import__("braniac.pesquisa", fromlist=["x"]).pesquisar(c, n)["fontes"])
    try:
        fontes = pesq(consulta, 3)
    except Exception as e:
        if avisar:
            avisar(f"⚠️ Busca na web falhou para {nome} (\"{consulta}\"): {str(e)[:100]}")
    final = _final_por_nivel(nome, servico, lugares, enviar_numero, avisar) if lugares else ""
    enviar(montar_resposta(consulta, fontes, cidade=cidade, lugares=lugares, final=final))
    if avisar:
        avisar(f"🔎 {nome} pediu uma busca (\"{consulta}\"); respondi com {len(lugares)} lugar(es) e {len(fontes)} página(s).")


def iniciar(nome, texto, enviar, avisar=None, enviar_numero=None, sincrono=False):
    """Devolve o recado imediato; a pesquisa roda em segundo plano e `enviar(texto)` manda o resultado depois."""
    args = (nome, texto, enviar, avisar, enviar_numero or (lambda fone, t: "não enviado"))
    if sincrono:
        _trabalho(*args)
    else:
        threading.Thread(target=_trabalho, args=args, daemon=True, name="braniac-busca-pedido").start()
    return "Já tô procurando isso pra você, minha tia, e daqui a pouquinho te mando os links e os telefones. 🔎" if _norm(nome) in ROTULOS else "Já tô procurando isso pra você e daqui a pouquinho te mando os links e os telefones. 🔎"
