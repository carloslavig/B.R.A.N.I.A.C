# -*- coding: utf-8 -*-
"""AVALIACAO DE EFICACIA DO JARVIS (27/10/2026): manda perguntas tipicas ao Jarvis REAL (http://127.0.0.1:8765/api/chat) e confere se a resposta serve.
So perguntas de LEITURA (nada de enviar mensagem). Pega regressao como a do eco ('Dono disse em...') e a de atalhos disparando por texto de contexto.
Uso: python -m braniac.avaliar_jarvis   (gasta um pouco das IAs gratis; Alma ignora estas mensagens)."""
import json
import re
import sys
import time
import urllib.request

URL = "http://127.0.0.1:8765/api/chat"
P = "[AVALIACAO-AUTOMATICA] "
CASOS = [   # nome, mensagem, regex que a resposta DEVE ter, regex que NAO pode ter
    ("saldo", "qual o saldo da conta?", r"R\$", r"Dono disse em|n[aã]o sei"),
    ("meta", "como está a meta desse mês?", r"R\$.*(?:1\.?600|faltam|batida)", r"Dono disse em"),
    ("vaquinha", "como está a vaquinha?", r"[Vv]aquinha.*R\$|ainda não foi ligada", r"Dono disse em"),
    ("agenda", "o que eu tenho na agenda hoje?", r"Hoje|hoje|Levar|nada", r"Dono disse em"),
    ("agentes", "quais são os agentes do Braniac?", r"Sult[aã]o.*Alma|Alma.*Sult[aã]o|Cabo Tito", r"Dono disse em"),
    ("parceira", "quem é a Parceira?", r"Parceira[ií]na|Parceira", r"Dono disse em"),
    ("site", "qual é o endereço do site da vaquinha? só me responde aqui, não manda por WhatsApp", r"vaquinha-exemplo\.vercel\.app", r"Dono disse em"),
    ("eco", "vou mandar o link do site da vaquinha pro grupo da família", r".{20,}", r"^Dono disse em"),
    ("contexto", "66999990001\n\n[Conversa recente no WhatsApp: Dono: mostra a agenda de hoje ¦ Jarvis: ok]", r".{10,}", r"Levar Parceira|RESULTADO DE FERRAMENTA"),
    ("lembrete-vago", "Me lembre amanhã", r"(?i)de que|o que|qual|quê|que horas|hor[aá]rio|sobre", r"Dono disse em|anotado|09:00"),
    ("geral", "me explica em 3 linhas o que é um Pix copia e cola", r".{80,}", r"Dono disse em|RESULTADO DE FERRAMENTA"),
]


def perguntar(texto, conv):
    req = urllib.request.Request(URL, data=json.dumps({"texto": P + texto, "conv": conv}).encode("utf-8"), headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=240) as r:
        return json.load(r).get("resposta", "")


def casos_dos_erros(arquivo=None):
    """Erros que o Dono marcou ('errou' / 'seu cu'): so pedidos de CONSULTA (sem acao, sem efeito colateral) rodam sozinhos; os outros ficam para revisao manual.
    O caso passa quando a resposta NAO repete a resposta errada de antes."""
    from . import delegacao
    from .store import DATA
    arq = arquivo or (DATA / "erros_jarvis.jsonl")
    auto, manual = [], []
    try:
        linhas = arq.read_text(encoding="utf-8").splitlines()
    except OSError:
        return [], []
    for l in linhas[-60:]:
        try:
            e = json.loads(l)
        except ValueError:
            continue
        ped, ruim = (e.get("pedido") or "").strip(), (e.get("resposta_errada") or "").strip()
        if not ped or not ruim:
            continue
        caso = (f"erro-{int(e.get('ts', 0))}", ped, r".{10,}", re.escape(" ".join(ruim.split())[:70]).replace(r"\ ", r"\s+"))
        (auto if delegacao.eh_consulta(ped) else manual).append(caso)
    return auto, manual


def avaliar(perguntar=perguntar, casos=CASOS):
    """[(nome, ok, motivo, resposta)] ; ok=False se faltou o esperado ou apareceu o proibido."""
    out = []
    for nome, msg, deve, nao in casos:
        try:
            r = perguntar(msg, f"aval-{nome}-{int(time.time())}")
        except Exception as e:
            out.append((nome, False, f"erro: {str(e)[:80]}", ""))
            continue
        if not re.search(deve, r, re.S):
            out.append((nome, False, "faltou o esperado", r))
        elif nao and re.search(nao, r, re.S | re.M):
            out.append((nome, False, "apareceu algo proibido", r))
        else:
            out.append((nome, True, "", r))
    return out


if __name__ == "__main__":
    auto, manual = casos_dos_erros()
    res = avaliar(casos=CASOS + auto)
    if manual:
        print(f"{len(manual)} erro(s) marcado(s) por voce precisam de revisao manual (pedido com acao): " + "; ".join(m[1][:50] for m in manual[:5]))
    for nome, ok, motivo, r in res:
        print(("OK   " if ok else "FALHA"), nome, ("- " + motivo if motivo else ""), "|", r.replace("\n", " ")[:110])
    print(f"{sum(1 for x in res if x[1])}/{len(res)} ok")
    sys.exit(0 if all(x[1] for x in res) else 1)
