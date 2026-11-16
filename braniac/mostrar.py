# -*- coding: utf-8 -*-
""""ME MOSTRA" POR VOZ (15/11/2026, pedido do Dono): perguntas de situacao ('como ta o NexoDev?', 'como ta a esteira?') abrem a tela certa
DENTRO do Braniac (aba do /b2 ou a pagina de voz ja aberta, nunca navegador novo) e o Jarvis fala o estado em uma frase.
Tambem cuida dos LINKS de fora: em vez de abrir sozinho, pergunta se abre aqui ou manda no celular (WhatsApp por padrao, o PC esta pesado).

A tela pedida fica em TELA {id, url, t}; as paginas (b2/hud/voz) leem pelo /api/escuta-estado e trocam de tela uma vez por id.
Crescer: uma linha nova em TELAS (assunto, url, funcao que resume)."""
import re, time, unicodedata
from .store import DATA

TELA = {"id": 0, "url": None, "t": 0.0}
VALIDADE_S = 20          # pagina que so ler depois disso (aba fechada) nao troca de tela atrasada

PERGUNTA = re.compile(r"\b(como (ta|esta|anda|vai|que ta|que esta)|situacao|status|me mostra|mostra|abre|abrir|ve pra mim|da uma olhada)\b")
ANDAR_API = {"escritorio": 1, "nexodev": 2, "marketing": 3, "investimentos": 4, "cortes": 5, "compras": 6}


def _norm(x):
    s = "".join(c for c in unicodedata.normalize("NFD", str(x).lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", s)).strip()


# ---------- resumos falados (uma frase, so dado real; sem dado diz que nao tem) ----------

def _lote():
    from .link import lote_parceiro
    e = lote_parceiro.ler().get("esteira") or {}
    if not e:
        return "Não achei os dados da esteira do Parceiro agora."
    meta, prontos = int(e.get("meta") or 50), len(e.get("prontos") or [])
    a = (e.get("atual") or {}).get("cidade")
    return f"Esteira do Parceiro: {prontos} de {meta} vídeos prontos no lote" + (f", agora fazendo {a}." if a else ".")


def _estacoes():
    from . import sauraki
    est = ((sauraki._esteira(time.time()) or {}).get("estacoes")) or []
    if not est:
        return "Não achei os dados do andar da esteira agora."
    ativos = [s.get("agente") for s in est if s.get("estado") == "executando"]
    if not ativos:
        return f"Andar da esteira: as {len(est)} estações estão paradas agora."
    return f"Andar da esteira: {len(ativos)} de {len(est)} estações trabalhando ({', '.join(ativos[:4])})."


def _andar(chave, nome):
    def resumo():
        from . import sauraki
        ags = [a for a in (sauraki.snapshot().get("agentes") or []) if a.get("andar") == ANDAR_API[chave]]
        if not ags:
            return f"Não achei os dados do {nome} agora."
        ativos = sum(1 for a in ags if a.get("estado") in ("executando", "analisando", "planejando", "consultando"))
        if not ativos:
            return f"{nome}: o time está ocioso agora, {len(ags)} agentes parados."
        return f"{nome}: {ativos} de {len(ags)} agentes trabalhando agora."
    return resumo


# o Whisper escreve "estreia" para "esteira" (visto ao vivo em 15/11)
# (palavras do assunto, tela, resumo). Ordem importa: o mais especifico primeiro ('andar da esteira' antes de 'esteira').
TELAS = [
    (r"\b(time|andar|equipe|pessoal|estacoes?) da (esteira|estreia)\b", "/sauraki?andar=esteira", _estacoes),
    (r"\b(esteira|estreia do parceiro|estreia de parceiro|lote|videos? do parceiro|parceiro)\b", "/parceiro", _lote),
    (r"\b(nexo ?dev|nexus ?dev|nexo de?v|time de programacao)\b", "/sauraki?andar=nexodev", _andar("nexodev", "NexoDev")),
    (r"\b(fornalha|marketing)\b", "/sauraki?andar=marketing", _andar("marketing", "Fornalha")),
    (r"\b(claquete|cortes)\b", "/sauraki?andar=cortes", _andar("cortes", "Claquete")),
    (r"\b(pechincha|compras)\b", "/sauraki?andar=compras", _andar("compras", "Pechincha")),
    (r"\b(quantix|investimentos?)\b", "/sauraki?andar=investimentos", _andar("investimentos", "Quantix")),
    (r"\b(escritorio|predio)\b", "/sauraki", None),
]


def intencao(texto):
    """(url, resumo) se for pergunta de situacao de um assunto da tabela; senao None."""
    n = _norm(texto)
    if not PERGUNTA.search(n):
        return None
    for padrao, url, resumo in TELAS:
        if re.search(padrao, n):
            return url, resumo
    return None


def abrir_tela(url):
    TELA.update(id=TELA["id"] + 1, url=url, t=time.time())


def tela_atual():
    """Para o /api/escuta-estado: a ultima tela pedida, enquanto vale."""
    return {"id": TELA["id"], "url": TELA["url"]} if TELA["url"] and time.time() - TELA["t"] < VALIDADE_S else None


def mostrar(texto):
    """Abre a tela e devolve a frase a falar, ou None se nao for pergunta de situacao."""
    achou = intencao(texto)
    if not achou:
        return None
    url, resumo = achou
    abrir_tela(url)
    try:
        return resumo() if resumo else "Abri o prédio do Braniac pra você."
    except Exception:
        return "Abri a tela, mas não consegui ler os números agora."


# ---------- links de fora ----------
URL = re.compile(r"https?://[^\s)>\]]+")
PERGUNTA_LINK = "Isso é um link. Abro aqui no navegador ou te mando no celular, no WhatsApp ou no Telegram? Se não souber, mando no WhatsApp, que pesa menos no PC."


def links(texto):
    return [u.rstrip(".,;:!?") for u in URL.findall(texto or "")]


def eh_local(url):
    return bool(re.match(r"https?://(127\.0\.0\.1|localhost)(:8765)?(/|$)", url))


def escolha(texto):
    """'aqui' | 'whatsapp' | 'telegram' | 'nao' | None (nao respondeu a pergunta do link)."""
    n = _norm(texto)
    if re.search(r"\btelegram\b", n):
        return "telegram"
    if re.search(r"\b(nao|deixa|esquece|nada|cancela)\b", n) and not re.search(r"\b(manda|envia|abre)\b", n):
        return "nao"
    if re.search(r"\b(whats ?app|zap|zapzap|celular|telefone|manda|mande|envia|pode mandar)\b", n):
        return "whatsapp"
    if re.search(r"\b(aqui|navegador|computador|pc|abre|abrir|abra)\b", n):
        return "aqui"
    return None


def entregar_link(urls, como, mandar_whatsapp=None, mandar_telegram=None, abrir=None):
    """Executa a escolha do Dono. WhatsApp vai pela caixa de saida do Braniac (ele entrega; script de fora corta audio e atropela a trava)."""
    texto = "Link que você pediu:\n" + "\n".join(urls)
    if como == "aqui":
        for u in urls:
            if eh_local(u):
                abrir_tela(re.sub(r"^https?://[^/]+", "", u) or "/")
            else:
                (abrir or _abrir_navegador)(u)
        return "Pronto, abri aqui."
    if como == "telegram":
        from . import telegram_bot
        ok = (mandar_telegram or telegram_bot.avisar_dono)(texto)
        return "Mandei no seu Telegram." if ok else "Não consegui mandar no Telegram. Quer que eu mande no WhatsApp?"
    if como == "whatsapp":
        (mandar_whatsapp or _outbox)(texto)
        return "Beleza, mandei no seu WhatsApp."
    return "Tudo bem, deixei pra lá."


def _abrir_navegador(url):
    import webbrowser
    webbrowser.open(url)


def _outbox(texto):
    with (DATA / "outbox_dono.txt").open("a", encoding="utf-8") as f:
        f.write("\n---\n" + texto)
