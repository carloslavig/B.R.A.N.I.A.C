"""Agente MONZA (29/10/2026): corridas de carro pelo WhatsApp. Quem pede corrida recebe perguntas (onde esta / pra onde vai), a rota e a distancia saem do
OpenStreetMap (Nominatim + OSRM, gratis, sem chave) e o preco medio e R$ 2,30 por km (10 km = R$ 23,00). Nao precisa de IA. So da o VALOR ESTIMADO:
nunca pede dado de pagamento nem fecha a corrida sozinho; quando o preco sai, avisa o Dono (via Jarvis) para ele combinar o resto."""
import json, re, time, urllib.parse, urllib.request
from .store import DATA

PRECO_KM = 2.30
from . import pessoal as _pessoal
CIDADE = _pessoal.get("cidade", "")   # shortcut: endereco sem cidade e buscado aqui (data/pessoal.json)
ARQ = DATA / "monza.json"
VALIDADE_S = 3 * 3600                    # conversa parada ha mais de 3 h recomeca do zero
UA = {"User-Agent": "braniac-monza/1.0 (" + _pessoal.get("email_contato", "") + ")"}
PEDIDO = re.compile(r"\b(corrida|uber|taxi|t[áa]xi|motorista|me\s+busca|vem\s+me\s+buscar|pode\s+me\s+levar|quanto\s+(?:custa|fica|[ée])\s+(?:uma?\s+)?(?:corrida|ir|at[ée]))\b", re.I)
DE_PARA = re.compile(r"\bde\s+(.+?)\s+(?:pra|para|at[ée]|ao|a)\s+(.+)$", re.I)


def _ler():
    try:
        return json.loads(ARQ.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _gravar(d):
    ARQ.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def _get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def geocodar(lugar):
    """(lat, lon) do primeiro resultado ou None. Sem virgula no texto, assume a cidade padrao."""
    q = lugar if "," in lugar else f"{lugar}, {CIDADE}"
    r = _get("https://nominatim.openstreetmap.org/search?format=json&limit=1&q=" + urllib.parse.quote(q))
    return (float(r[0]["lat"]), float(r[0]["lon"])) if r else None


def distancia_km(a, b):
    """Distancia de carro pela rota (OSRM), em km. None se nao houver rota."""
    r = _get(f"https://router.project-osrm.org/route/v1/driving/{a[1]},{a[0]};{b[1]},{b[0]}?overview=false")
    return r["routes"][0]["distance"] / 1000 if r.get("routes") else None


def preco(km):
    return round(km * PRECO_KM, 2)


def _brl(v):
    return f"R$ {v:.2f}".replace(".", ",")


def eh_pedido(texto, nome=""):
    """Mensagem nova de corrida, ou conversa de corrida ja em andamento com esse contato."""
    return bool(PEDIDO.search(texto or "")) or _ler().get(nome, {}).get("ts", 0) > time.time() - VALIDADE_S


def responder(nome, texto, avisar_dono=None):
    """Proxima fala do Monza. Estado por contato em data/monza.json: origem -> destino -> valor."""
    est = _ler()
    c = est.get(nome) or {}
    if c.get("ts", 0) < time.time() - VALIDADE_S:
        c = {}
    texto = (texto or "").strip()
    m = DE_PARA.search(texto)
    if m and not c.get("origem"):
        c["origem"], c["destino"] = m.group(1).strip(), m.group(2).strip()
    elif not c.get("origem"):
        if PEDIDO.search(texto) and len(texto) < 60 or not texto:
            c["origem"] = None
        else:
            c["origem"] = texto
    elif not c.get("destino"):
        c["destino"] = texto
    c["ts"] = time.time()
    if not c.get("origem"):
        est[nome] = c
        _gravar(est)
        return "Oi! Aqui é o Monza, assistente de corridas do Dono. Me diz onde você está agora (rua, bairro ou ponto de referência)?"
    if not c.get("destino"):
        est[nome] = c
        _gravar(est)
        return "Beleza! E pra onde você quer ir?"
    est.pop(nome, None)       # conversa fechada
    _gravar(est)
    try:
        a, b = geocodar(c["origem"]), geocodar(c["destino"])
        km = distancia_km(a, b) if a and b else None
    except Exception:
        km = None
    if km is None:
        return "Não consegui achar esse trajeto no mapa. Pode me mandar o endereço com rua e bairro (ou um ponto de referência)? Vou refazer o cálculo."
    v = preco(km)
    if avisar_dono:
        avisar_dono(f"Monza: {nome} pediu corrida de «{c['origem']}» até «{c['destino']}», {km:.1f} km, valor médio {_brl(v)}.")
    return (f"Saindo de {c['origem']} até {c['destino']} são cerca de {km:.1f} km, então o valor médio da corrida fica em {_brl(v)} "
            f"(R$ 2,30 por km). É uma estimativa: já avisei o Dono e ele confirma com você a corrida.")
