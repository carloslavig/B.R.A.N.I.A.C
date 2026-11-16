# -*- coding: utf-8 -*-
"""16/11: catalogo de vozes para a pagina /vozes: cada MODELO de voz com as VOZES de dentro dele, amostra falada na hora e escolha da voz.
Regra do Dono: nada que demore mais de 30 s para falar (Rafael e XTTS-v2 aparecem, mas desligados)."""
import concurrent.futures as cf, json, time, urllib.request
from pathlib import Path
from . import voz, vozes_agentes
from .store import DATA

LIMITE_S = 30
TEXTO = "Oi, Dono. Esta é a minha voz. Hoje você tem a prova do Exército às oito horas. Qualquer coisa, é só me chamar."
GEMINI_F = {"Zephyr", "Kore", "Leda", "Aoede", "Callirrhoe", "Autonoe", "Despina", "Erinome", "Laomedeia", "Achernar", "Gacrux", "Pulcherrima", "Vindemiatrix", "Sulafat"}
GEMINI_M = ["Puck", "Charon", "Fenrir", "Orus", "Enceladus", "Iapetus", "Umbriel", "Algieba", "Algenib", "Rasalgethi", "Alnilam", "Schedar", "Achird", "Zubenelgenubi", "Sadachbia", "Sadaltager"]
# vozes do Piper em portugues do Brasil (rhasspy/piper-voices); todas masculinas
PIPER = {"faber/medium": "Faber", "cadu/medium": "Cadu", "jeff/medium": "Jeff", "edresson/low": "Edresson (qualidade baixa)"}
_LINGUAS = {"a": "inglês EUA", "b": "inglês UK", "e": "espanhol", "f": "francês", "h": "hindi", "i": "italiano", "j": "japonês", "p": "português", "z": "chinês"}
_EDGE = {"v": None, "t": 0.0}
_POOL = cf.ThreadPoolExecutor(max_workers=2)


def _edge_vozes():
    if _EDGE["v"] is None or time.time() - _EDGE["t"] > 86400:
        try:
            import asyncio, edge_tts
            _EDGE["v"] = asyncio.run(edge_tts.list_voices())
        except Exception:   # sem internet: so as de portugues
            _EDGE["v"] = [{"ShortName": n, "Gender": g, "Locale": l} for n, g, l in (
                ("pt-BR-AntonioNeural", "Male", "pt-BR"), ("pt-BR-FranciscaNeural", "Female", "pt-BR"), ("pt-BR-ThalitaMultilingualNeural", "Female", "pt-BR"),
                ("pt-PT-DuarteNeural", "Male", "pt-PT"), ("pt-PT-RaquelNeural", "Female", "pt-PT"))]
        _EDGE["t"] = time.time()
    return _EDGE["v"]


def _kokoro_vozes():
    import numpy as np
    d = np.load(voz.MODELOS / "kokoro" / "voices-v1.0.bin", allow_pickle=True)
    return sorted(d.files, key=lambda n: (n[0] != "p", n))


def _v(id_, nome, genero, idioma, instalada=True):
    return {"id": id_, "nome": nome, "genero": genero, "idioma": idioma, "instalada": instalada}


# 16/11: pontos de partida para a Alma (voz feminina + o preset "sedutora" de vozes_agentes.PRESETS); o Dono ouve na aba Vozes e escolhe
COMBINACOES = [("Gemini, Kore", "gemini", "Kore"), ("Gemini, Aoede", "gemini", "Aoede"), ("Gemini, Leda", "gemini", "Leda"), ("Gemini, Zephyr", "gemini", "Zephyr"),
               ("Gemini, Sulafat", "gemini", "Sulafat"), ("Gemini, Callirrhoe", "gemini", "Callirrhoe"), ("Edge, Francisca", "edge", "pt-BR-FranciscaNeural"),
               ("Edge, Thalita", "edge", "pt-BR-ThalitaMultilingualNeural"), ("Kokoro, pf_dora", "kokoro", "pf_dora")]


def catalogo():
    escolha = vozes_agentes.escolha("jarvis")
    motores = []
    try:
        kok = [_v(n, n, "F" if n[1] == "f" else "M", _LINGUAS.get(n[0], n[0])) for n in _kokoro_vozes()]
    except Exception:
        kok = []
    motores.append({"id": "kokoro", "nome": "Kokoro", "onde": "Local (CPU), sem limite de uso", "lento": False, "vozes": kok})
    motores.append({"id": "piper", "nome": "Piper", "onde": "Local (CPU), sem limite de uso", "lento": False,
                    "vozes": [_v(i, n, "M", "português BR", voz.piper_caminho(i).exists()) for i, n in PIPER.items()]})
    ed = [_v(x["ShortName"], x["ShortName"].split("-", 2)[2].replace("Neural", ""), "F" if x["Gender"] == "Female" else "M", x["Locale"]) for x in _edge_vozes()]
    ed.sort(key=lambda v: (not v["idioma"].startswith("pt"), v["idioma"], v["nome"]))
    motores.append({"id": "edge", "nome": "Edge TTS (Microsoft)", "onde": "Online, sem chave nem cota (depende da Microsoft)", "lento": False, "vozes": ed})
    ge = [_v(n, n, "F", "multilíngue") for n in sorted(GEMINI_F)] + [_v(n, n, "M", "multilíngue") for n in GEMINI_M]
    motores.append({"id": "gemini", "nome": "Gemini TTS (Google)", "onde": "Online, com cota por chave", "lento": False, "vozes": ge})
    motores.append({"id": "rafael", "nome": "Rafael (Pocket TTS)", "onde": "Local, mas leva ~60 s: passa dos 30 s", "lento": True, "vozes": [_v("rafael", "Rafael", "M", "português")]})
    motores.append({"id": "xtts", "nome": "XTTS-v2 (placa de vídeo)", "onde": "Local, mas leva ~110 s: passa dos 30 s", "lento": True, "vozes": [_v("referencia", "Clone de voz (referência)", "M", "português")]})
    combos = [{"id": f"{m}:{v}", "nome": f"{n}, sedutora", "motor": m, "voz": v, "ajustes": vozes_agentes.PRESETS["sedutora"]["ajustes"]} for n, m, v in COMBINACOES]
    return {"presets": vozes_agentes.PRESETS, "combinacoes": combos, "motores": motores, "escolha": escolha, "limite_s": LIMITE_S,
            "agentes": [{**a, "escolha": vozes_agentes.escolha(a["id"])} for a in vozes_agentes.agentes()]}


def _gerar(motor, voz_id, texto, estilo=None):
    if motor == "kokoro":
        return voz._kokoro_wav(texto, voz_nome=voz_id)
    if motor == "piper":
        return voz._falar_wav_piper(texto, voz_id=voz_id)
    if motor == "edge":
        return voz._edge_wav(texto, voz_nome=voz_id)
    if motor == "gemini":
        return voz._gemini_wav(texto, voz_nome=voz_id, estilo=estilo)
    raise ValueError("motor sem amostra rápida (passa de 30 s)")


def amostra(motor, voz_id, texto=None, ajustes=None):
    """Devolve (wav, segundos que levou) ou levanta erro. Passou de LIMITE_S = erro (a regra do Dono)."""
    t0 = time.time()
    fut = _POOL.submit(_gerar, motor, voz_id, voz.limpar_para_fala(texto or TEXTO), (ajustes or {}).get("estilo"))
    try:
        wav = voz.aplicar_ajustes(fut.result(timeout=LIMITE_S), ajustes)   # o que o Dono ouve ja leva os controles da tela
    except cf.TimeoutError:
        raise RuntimeError(f"passou de {LIMITE_S} s: essa voz não serve")
    return wav, round(time.time() - t0, 1)


def escolher(motor, voz_id, agente="jarvis", posicao=1):
    """posicao 1 = primaria, 2 = secundaria, 3 = terciaria (16/11: reserva quando a primaria falha)."""
    cat = {m["id"]: m for m in catalogo()["motores"]}
    if motor not in cat or cat[motor]["lento"]:
        raise ValueError("esse motor passa de 30 s e está desligado")
    v = next((x for x in cat[motor]["vozes"] if x["id"] == voz_id), None)
    if not v or not v["instalada"]:
        raise ValueError("voz inexistente ou não instalada")
    so = next((a.get("so_genero") for a in vozes_agentes.agentes() if a["id"] == agente), None)
    if so and v["genero"] != so:
        raise ValueError("esse agente só usa voz feminina" if so == "F" else "esse agente só usa voz masculina")
    return vozes_agentes.escolher(agente, motor, voz_id, v["genero"], posicao)


def limpar_escolha(agente="jarvis"):
    vozes_agentes.limpar(agente)


def baixar_piper(voz_id):
    """Baixa o modelo do Piper (so a pedido do Dono, ao clicar). Fonte: rhasspy/piper-voices no Hugging Face."""
    if voz_id not in PIPER:
        raise ValueError("voz do Piper desconhecida")
    nome, qual = voz_id.split("/")
    alvo = voz.piper_caminho(voz_id)
    alvo.parent.mkdir(parents=True, exist_ok=True)
    base = f"https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/{nome}/{qual}/pt_BR-{nome}-{qual}.onnx"
    for url, destino in ((base, alvo), (base + ".json", Path(str(alvo) + ".json"))):
        tmp = Path(str(destino) + ".baixando")
        urllib.request.urlretrieve(url, tmp)
        tmp.replace(destino)
    return True
