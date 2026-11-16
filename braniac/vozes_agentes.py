# -*- coding: utf-8 -*-
"""MODULO DE VOZES POR AGENTE (16/11/2026): cada agente do Braniac pode ter a sua propria voz.

Hoje: Jarvis, Alma e o Zelo (16/11: agente que fala com o pai e a mae do Dono e, por enquanto, se apresenta como Jarvis; id "zelo").
O Dono escolhe a voz de cada um na aba "Vozes" do painel (/b2#/vozes) ou em /vozes.

COMO FUNCIONA
- A escolha fica em data/voz_escolhida.json. O Jarvis fica no TOPO do arquivo ({"motor","genero","vozes"}), formato antigo que o voz.py ja lia;
  os outros agentes ficam em {"agentes": {"alma": {"motor","genero","vozes"}, ...}}.
- Para um agente FALAR com a voz dele: `vozes_agentes.falar_wav("alma", texto)` (ou `voz.falar_wav(texto, agente="alma")`).
  Sem voz escolhida para o agente, vale a ordem de sempre do Jarvis (Gemini, Edge, Kokoro, Piper).
- Regra do Dono: nenhuma voz pode passar de 30 s para responder (Rafael e XTTS-v2 ficam desligados).

PARA QUEM CONTINUAR (a Alma ainda nao fala em nenhum lugar: hoje ela so escreve)
- Onde ela passar a mandar audio, use `vozes_agentes.falar_wav("alma", texto)` em vez de `voz.falar_wav(texto)`.
- Agente novo: acrescente em data/vozes_agentes.json {"agentes":[{"id":"nome_curto","nome":"Nome bonito"}]}; ele aparece sozinho na aba Vozes.
- Codigo da tela: ui/painel.html (funcao vVozes); catalogo e amostras: vozes_catalogo.py; rotas: /api/vozes* no server.py; testes: tests/test_humor_voz.py.
"""
import json
from .store import DATA

PADRAO = [{"id": "jarvis", "nome": "Jarvis"}, {"id": "alma", "nome": "Alma", "so_genero": "F", "combinacoes": True}, {"id": "zelo", "nome": "Zelo (fala como Jarvis)"}]
ARQ = "voz_escolhida.json"


def agentes():
    """Lista de agentes com voz. data/vozes_agentes.json pode renomear ou acrescentar."""
    try:
        extra = json.loads((DATA / "vozes_agentes.json").read_text(encoding="utf-8")).get("agentes") or []
    except (OSError, ValueError):
        extra = []
    por_id = {a["id"]: dict(a) for a in PADRAO}
    for a in extra:
        if isinstance(a, dict) and a.get("id"):
            por_id[str(a["id"])] = {**por_id.get(str(a["id"]), {}), **{k: v for k, v in a.items() if k in ("so_genero", "combinacoes")}, "id": str(a["id"]), "nome": str(a.get("nome") or a["id"])}
    return list(por_id.values())


def _ler():
    try:
        return json.loads((DATA / ARQ).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def escolha(agente="jarvis"):
    d = _ler()
    return d if agente in (None, "jarvis") else (d.get("agentes") or {}).get(agente, {})


def todas():
    return {a["id"]: escolha(a["id"]) for a in agentes()}


def _valido(agente):
    if agente not in {a["id"] for a in agentes()}:
        raise ValueError("agente desconhecido")


def escolher(agente, motor, voz_id, genero, posicao=1):
    """Grava a voz do agente (a validacao do motor/voz e do catalogo). Devolve a escolha dele.
    16/11: posicao 1 = PRIMARIA (formato antigo: motor/genero/vozes); 2 e 3 = SECUNDARIA e TERCIARIA, em "reservas": [{motor, voz, genero}, ...].
    Se a primaria falhar (cota, fora do ar, erro, audio vazio), o voz.py tenta as reservas na ordem."""
    _valido(agente)
    posicao = int(posicao or 1)
    if posicao not in (1, 2, 3):
        raise ValueError("posicao deve ser 1, 2 ou 3")
    d = _ler()
    alvo = d if agente == "jarvis" else d.setdefault("agentes", {}).setdefault(agente, {})
    if posicao == 1:
        vozes = dict(alvo.get("vozes") or {})
        vozes[motor] = voz_id
        alvo.update({"motor": motor, "genero": genero, "vozes": vozes})
    else:
        res = [r for r in (alvo.get("reservas") or []) if isinstance(r, dict) and r.get("motor")][:2]
        item = {"motor": motor, "voz": voz_id, "genero": genero}
        if posicao - 2 < len(res):
            res[posicao - 2] = item
        else:
            res.append(item)   # terciaria sem secundaria vira a secundaria
        alvo["reservas"] = res
    (DATA / ARQ).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return escolha(agente)


def reservas(agente="jarvis"):
    """Vozes de reserva do agente, na ordem (secundaria, terciaria)."""
    return [r for r in (escolha(agente).get("reservas") or []) if isinstance(r, dict) and r.get("motor") and r.get("voz")][:2]


def tirar_reserva(agente, posicao):
    """Tira a secundaria (2) ou a terciaria (3); a terciaria sobe se a secundaria sair."""
    _valido(agente)
    d = _ler()
    alvo = d if agente == "jarvis" else (d.get("agentes") or {}).get(agente)
    if alvo is not None:
        res = list(alvo.get("reservas") or [])
        if 0 <= int(posicao) - 2 < len(res):
            res.pop(int(posicao) - 2)
        if res:
            alvo["reservas"] = res
        else:
            alvo.pop("reservas", None)
        (DATA / ARQ).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return escolha(agente)


def limpar(agente="jarvis"):
    """Volta o agente para a ordem de sempre."""
    _valido(agente)
    d = _ler()
    if agente == "jarvis":
        for k in ("motor", "genero", "vozes", "ajustes", "reservas"):
            d.pop(k, None)
    else:
        (d.get("agentes") or {}).pop(agente, None)
    (DATA / ARQ).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def falar_wav(agente, texto, **kw):
    """Texto -> WAV com a voz escolhida para `agente`."""
    from . import voz
    return voz.falar_wav(texto, agente=agente, **kw)


PRESETS = {   # pontos de partida para o Dono; ele ajusta os controles depois
    "natural": {"nome": "Natural", "ajustes": {}},
    "acolhedora": {"nome": "Acolhedora", "ajustes": {"estilo": "Fale em português do Brasil com voz suave, calorosa e acolhedora, em volume normal, sem sussurrar, ritmo calmo, como quem cuida de alguém querido",
                                                      "velocidade": 0.95, "tom": 0, "calor": 40}},
    "sedutora": {"nome": "Sedutora", "ajustes": {"estilo": "Fale em português do Brasil com voz grave, quente e envolvente, em volume normal e bem projetada, sem sussurrar, em ritmo lento e seguro, com sensualidade e confiança, com um sorriso discreto na voz",
                                                  "velocidade": 0.92, "tom": -1, "calor": 55}},
}


def ajustar(agente, ajustes):
    """Grava os ajustes de voz do agente (velocidade, tom, calor, estilo). Valores fora da faixa sao cortados."""
    _valido(agente)
    a = {}
    if ajustes.get("velocidade") is not None:
        a["velocidade"] = round(min(max(float(ajustes["velocidade"]), 0.7), 1.3), 2)
    if ajustes.get("tom") is not None:
        a["tom"] = round(min(max(float(ajustes["tom"]), -6.0), 3.0), 1)
    if ajustes.get("calor") is not None:
        a["calor"] = round(min(max(float(ajustes["calor"]), 0.0), 100.0))
    if str(ajustes.get("estilo") or "").strip():
        a["estilo"] = str(ajustes["estilo"]).strip()[:300]
    d = _ler()
    alvo = d if agente == "jarvis" else d.setdefault("agentes", {}).setdefault(agente, {})
    if a:
        alvo["ajustes"] = a
    else:
        alvo.pop("ajustes", None)
    (DATA / ARQ).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return escolha(agente)
