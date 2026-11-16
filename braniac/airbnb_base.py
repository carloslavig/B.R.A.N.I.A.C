"""Base de conhecimento POR ANUNCIO do Airbnb (fatos no jarvis.db, escopo 'airbnb') + perguntas ao Dono + 'Info Casa' antes de aceitar a casa inteira.
Fatos entram quando o Dono responde no WhatsApp: 'Cacau: o wifi é X' (anuncio: texto) ou 'Elvira: o endereço é X' (hospede: resposta, que tambem vai ao hospede)."""
import re
import time

from . import banco

# slug -> (regex do titulo do anuncio, tipo)
ANUNCIOS = {
    "cacau": (r"quarto a", "quarto"), "gabriela": (r"quarto b", "quarto"), "jorge-amado": (r"su[ií]te suite c", "quarto"),
    "casa": (r"casa princesinha", "casa"), "arleo": (r"apartamento completo", "apto"), "studio": (r"^\s*studio", "apto"),
    "adriana": (r"adriana|jardim atl", "apto"),
}
PERGUNTAS = {
    "quarto": "wifi (nome/senha podem ir ao hóspede?), como chegar/endereço, estacionamento, horário e regra de uso da piscina e áreas comuns, barulho/visitas, ar-condicionado/toalhas",
    "casa": "wifi, estacionamento, quem mora nos fundos e o que o hóspede pode usar, regras de barulho/visitas, o texto da 'Info Casa'",
    "apto": "wifi, estacionamento/portaria, como chegar, regras do prédio, ar-condicionado/utensílios",
}
INFO_CASA = "info-casa"


def slug(anuncio):
    for s, (rx, _) in ANUNCIOS.items():
        if re.search(rx, anuncio or "", re.I):
            return s
    return None


def tipo(anuncio):
    s = slug(anuncio)
    return ANUNCIOS[s][1] if s else None


def guardar(s, texto, tema=None):
    banco.gravar_fato("airbnb", f"{s}:{tema or int(time.time())}", texto.strip()[:600], nivel="local", fonte="dono")


def fatos(s, pergunta="", n=4):
    """Fatos do anuncio, os que mais batem com a pergunta primeiro."""
    rows = banco._q("SELECT chave,texto FROM fatos WHERE escopo='airbnb' AND chave LIKE ? AND (validade IS NULL OR validade>?)", (f"{s}:%", time.time())).fetchall()
    pal = set(re.findall(r"\w{4,}", (pergunta or "").lower()))
    rows = [r for r in rows if not r[0].endswith(":" + INFO_CASA)]
    return [t for _, t in sorted(rows, key=lambda r: -len(pal & set(re.findall(r"\w{4,}", r[1].lower()))))[:n]]


def info_casa():
    r = banco._q("SELECT texto FROM fatos WHERE escopo='airbnb' AND chave=?", (f"casa:{INFO_CASA}",)).fetchone()
    return r[0] if r else None


def questionario(s):
    return f"Airbnb | montando a base do anúncio '{s}'. Me responde começando com '{s}:' e o que souber de: {PERGUNTAS[ANUNCIOS[s][1]]}. Pode mandar em várias mensagens (cada uma começando com '{s}:')."


def ler_respostas(msgs, hospedes_abertos):
    """msgs=[(ts,texto)] do Dono. -> (anuncio_facts [(slug,texto)], respostas_hospede [(primeiro_nome_minusculo,texto)])."""
    fa, rh = [], []
    for _, t in msgs:
        m = re.match(r"^\s*([\w-]{3,20}(?: casa)?)\s*:\s*(.{4,})$", (t or "").strip(), re.S)
        if not m:
            continue
        k, txt = m.group(1).lower().replace(" ", "-"), m.group(2)
        if k == INFO_CASA or k in ("info", "infocasa"):
            fa.append(("casa:" + INFO_CASA, txt))
        elif k in ANUNCIOS:
            fa.append((k, txt))
        elif k in hospedes_abertos:
            rh.append((k, txt))
    return fa, rh
