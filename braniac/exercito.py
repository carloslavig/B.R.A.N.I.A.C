# -*- coding: utf-8 -*-
"""CABO TITO (29/10/2026): dados do processo seletivo STT (TI) 2026/2027 da 11ª RM, tirados do edital (Aviso de Convocação 10-SSMR/11, 3/7/2026) e das
listas de 08/10/2026 (data/edital_stt/). Tudo LOCAL e sem IA: lista de exames, datas/prazos, EAF e a situação do Dono. O Tito entrega as datas à
Compasso (agenda) e responde Dono, Parceira e Mãe pelo Jarvis. O cronograma pode mudar: o edital manda acompanhar www.11rm.eb.mil.br."""
import re
from datetime import date, datetime

SITE = "www.11rm.eb.mil.br"
IS_DIA = date(2026, 11, 9)
EXAMES_ATE = date(2026, 10, 9)     # exames datados de no maximo 1 mes antes da IS (edital 12.1.7)

from . import pessoal as _pessoal
SITUACAO = _pessoal.get("exercito_situacao", "Situação do candidato não configurada (data/pessoal.json: exercito_situacao).")

EXAMES = [
    ("Sangue", ["Hemograma completo", "Tipagem sanguínea e fator Rh", "Coagulograma completo", "Colesterol total e frações", "Triglicerídeos",
                "Glicemia de jejum e glicemia de 2 horas (pós-prandial)", "Ureia e creatinina", "TGO e TGP", "PSA (homens)", "VDRL (sífilis)",
                "Chagas (IgG e IgM)", "Hepatite B (HBsAg e Anti-HBc IgG e IgM)", "Hepatite C", "HIV"]),
    ("Outros laboratoriais", ["Sumário de urina", "Parasitológico de fezes"]),
    ("Especialistas", ["Oftalmológico (acuidade visual, fundoscopia, tonometria, avaliação cromática)", "Audiometria", "Eletroencefalograma",
                       "Teste ergométrico", "Aptidão psicológica para manuseio de arma de fogo (psicólogo credenciado pela Polícia Federal, lista em www.pf.gov.br)"]),
    ("Imagem", ["Ecocardiograma com Doppler colorido", "Ressonância magnética dos joelhos (bilateral)", "Raio-X da coluna cervical, torácica e lombar (laudo + imagem; ângulos de Cobb e Ferguson se houver desvio)",
                "Raio-X dos campos pleuropulmonares", "Raio-X panorâmico dos dentes, com relatório odontológico", "MAPA (monitorização da pressão arterial)"]),
]
REGRAS_EXAMES = ("Todos com laudo, original + cópia, com nome completo e CPF ou RG, datados de no máximo 1 mês antes da IS (para 09/11, a partir de 09/10/2026). "
                 "Levar também documento oficial com foto, o CNIS (Cadastro Nacional de Informações Sociais) e roupa de banho por baixo (sunga). "
                 "Quem não apresentar todos os exames na data é eliminado. O edital manda fazer os exames só depois do chamamento (que o Dono já teve).")

EAF = ("EAF (Exame de Aptidão Física, só para quem for apto na IS; eliminatório; sem 2ª chamada). Mínimos para homens: flexão de braços 10, abdominal supra 20 "
       "(1º dia) e corrida de 12 minutos com 1.800 m (2º dia), em dois dias seguidos. Vai de calça, camisa de manga e calçado fechado, levando roupa de treino "
       "(troca no vestiário). Até 2 tentativas: flexão e abdominal repetem após 1 h de descanso; a corrida repete em dia útil depois, marcado pela comissão.")

# (data, hora, titulo, so_se) - so_se descreve a condicao; "" = vale para todos
CRONOGRAMA = [
    (date(2026, 11, 9), "08:00", "Inspeção de Saúde em Capital: exames, RG, CNIS e sunga", ""),
    (date(2026, 11, 23), "", "Resultado da Inspeção de Saúde (no site da 11ª RM)", ""),
    (date(2026, 11, 24), "", "Prazo de recurso da IS, 24 e 25/11, no Protocolo Geral", "se for considerado inapto"),
    (date(2026, 12, 3), "", "Chamada dos aptos na IS para o EAF (no site)", ""),
    (date(2026, 12, 8), "", "Período do EAF, 08 a 18/12 (data e local na convocação)", ""),
    (date(2026, 12, 15), "", "IS em grau de recurso, 15 a 22/12", "se tiver entrado com recurso"),
    (date(2026, 12, 29), "", "Resultado da IS em grau de recurso e chamada ao EAF", "se tiver entrado com recurso"),
    (date(2027, 1, 4), "", "EAF dos aptos na IS em grau de recurso, 04 a 07/01", "se tiver entrado com recurso"),
    (date(2027, 1, 8), "", "Resultado do EAF (no site)", ""),
    (date(2027, 1, 22), "", "Divulgação da classificação final", ""),
    (date(2027, 1, 25), "", "Convocação para a incorporação (no site)", ""),
    (date(2027, 1, 27), "", "Medidas administrativas na OM (27 a 29/01)", ""),
    (date(2027, 2, 1), "", "Incorporação e início do estágio de Sargento Técnico Temporário (12 meses)", ""),
]
AVISO = f"Datas do cronograma inicial do edital; só vale o dia, hora e local da convocação específica. Acompanhar sempre em {SITE}."

CHAVE = re.compile(r"(?i)\bex[eé]rcito\b|\beaf\b|\bstt\b|\bsargento\b|\bincorpora|\binspe[cç][aã]o\s+de\s+sa[uú]de|\bexpress[aã]o\s+d[aeo]\s+sa[uú]de|\binspira[cç][aã]o\s+d[aeo]\s+sa[uú]de|\bexames?\s+(?:do|para|da|que)\b|\blista\s+de\s+exames|"
                   r"\bexames?\s+m[eé]dicos?|\b11\s?rm\b|\bedital\b|prazo.{0,30}(?:ex[eé]rcito|\bis\b|eaf)|\bcorrida\s+de\s+12\b")
PEDIDO = re.compile(r"(?i)\?|\b(?:qual|quais|quando|quanto|onde|que\s+dia|me\s+(?:manda|passa|fala|diz|envia|mostra)|manda|passa|lista|prazo|data|dia|hor[aá]rio|hor[ao]s?|falta|quero\s+saber|preciso\s+saber)\b")


def eh_pergunta(texto):
    t = texto or ""
    from . import modulos
    if not modulos.ativo("exercito"):
        return False
    return len(t) < 400 and bool(CHAVE.search(t)) and bool(PEDIDO.search(t)) and not re.search(r"(?i)vaquinha|vakinha|arrecad", t)


def _fmt(d):
    return d.strftime("%d/%m/%Y")


def lista_exames():
    linhas = ["Exames que o Exército pede na Inspeção de Saúde (edital item 12):"]
    for grupo, itens in EXAMES:
        linhas.append(f"• {grupo}: " + "; ".join(itens) + ".")
    return "\n".join(linhas) + "\n" + REGRAS_EXAMES


def proximos(hoje=None, n=4):
    hoje = hoje or date.today()
    return [c for c in CRONOGRAMA if c[0] >= hoje][:n]


def _linha(c):
    d, h, t, cond = c
    return f"• {_fmt(d)}" + (f" {h}" if h else "") + f": {t}" + (f" ({cond})" if cond else "")


def cronograma(hoje=None, so_proximos=False):
    itens = proximos(hoje, 5) if so_proximos else CRONOGRAMA
    return "\n".join(_linha(c) for c in itens)


def _marco(chave, hoje):
    """Primeiro item do cronograma (de hoje em diante, senao o ultimo) cujo titulo casa com `chave`: uma linha so."""
    achados = [c for c in CRONOGRAMA if re.search(chave, c[2], re.I)]
    c = next((c for c in achados if c[0] >= hoje), achados[-1] if achados else None)
    return _linha(c) if c else None


def _exame(p):
    """Exames citados na pergunta (casa por palavra de 5+ letras do nome do exame)."""
    pal = set(re.findall(r"\w{5,}", p.lower())) - {"exame", "exames", "total", "completo", "completa", "quais", "levar"}
    return [i for _, itens in EXAMES for i in itens if pal & set(re.findall(r"\w{5,}", i.lower()))]


def resposta(pergunta="", hoje=None):
    """Resposta do Cabo Tito: SO o pedaco que a pergunta pede (hora, local, exame, EAF, resultado...). Devolve (texto, resumo_curto)."""
    hoje = hoje or date.today()
    p = pergunta or ""
    falt = (IS_DIA - hoje).days
    dia = "hoje" if falt == 0 else "amanhã" if falt == 1 else f"em {_fmt(IS_DIA)}"
    prox = proximos(hoje, 1)
    resumo = ("próximo marco: " + _fmt(prox[0][0]) + " " + prox[0][2][:60]) if prox else "processo sem marcos futuros no cronograma"
    if re.search(r"(?i)\btudo\b|todas as datas|cronograma|calend", p):
        return cronograma(hoje) + "\n" + AVISO, resumo
    partes = []
    eh_eaf = re.search(r"(?i)\beaf\b|f[ií]sic|corrida|flex[aã]o|abdominal|m[ií]nimo", p)
    if re.search(r"(?i)hor[aá]rio|que\s+horas|\bhoras?\b|\bcome[cç]a", p) and falt >= 0 and not eh_eaf:
        partes.append(f"A Inspeção de Saúde é {dia} ({_fmt(IS_DIA)}), às 8h.")
    if re.search(r"(?i)\bonde\b|\blocal\b|endere[cç]o", p):
        partes.append("Na Base administrativa do COpEsp, Av. Salvador S/N, Jardim Guanabara I, Capital.")
    if re.search(r"(?i)\bquando\b|que\s+dia|\bdata\b", p) and not partes and not re.search(r"(?i)eaf|resultado|recurso|incorpora|classifica", p):
        partes.append(f"A Inspeção de Saúde é {dia} ({_fmt(IS_DIA)}), às 8h." if falt >= 0 else (_marco(r"Resultado da Inspe", hoje) or ""))
    if re.search(r"(?i)\bfalta|quantos dias", p) and falt >= 0 and not eh_eaf:
        partes.append(f"Faltam {falt} dia(s) para a Inspeção de Saúde." if falt else "A Inspeção de Saúde é HOJE.")
    if re.search(r"(?i)\blevar|\bleve\b|trazer|documento|sunga|cnis|roupa de banho", p):
        partes.append("Leve os exames (laudo original + cópia, de até 1 mês antes), RG, CNIS e sunga.")
    if re.search(r"(?i)resultado", p):
        partes.append(_marco(r"Resultado do EAF" if eh_eaf else r"Resultado da Inspeção de Saúde \(", hoje) or "")
    if re.search(r"(?i)recurso", p):
        partes.append(_marco(r"recurso da IS", hoje) or "")
    if re.search(r"(?i)incorpora|classifica", p):
        partes.append(_marco(r"classifica|Incorpora", hoje) or "")
    if eh_eaf and not partes:
        partes.append((_marco(r"Período do EAF", hoje) or "") if re.search(r"(?i)quando|\bdata\b|\bdia\b|prazo", p) else EAF)
    if not partes and re.search(r"(?i)\bexames?\b|laudo|lista|sangue|preciso|pede", p):
        ex = _exame(p)
        partes.append("Pede: " + "; ".join(ex[:3]) + "." if ex and not re.search(r"(?i)lista|quais|todos", p) else lista_exames())
    if re.search(r"(?i)situa[cç][aã]o|meu caso|como estou", p):
        partes.append(SITUACAO)
    if not partes and re.search(r"(?i)\bprazos?\b|pr[oó]xim", p) and prox:
        partes = [_linha(prox[0])] + ([f"Faltam {falt} dia(s) para a Inspeção de Saúde."] if falt > 0 else [])
    partes = [x for x in partes if x]
    if not partes:  # pergunta vaga: so o essencial, nunca o texto todo
        partes = [_linha(prox[0]) if prox else "Não há marcos futuros no cronograma.", "Quer saber de horário, local, exames, EAF ou resultado?"]
    return ("\n" if len(partes) > 2 else " ").join(partes), resumo


def fatos():
    """Fatos que o Cabo Tito guarda no banco do assunto 'exercito' (escopo, chave, texto)."""
    return [
        ("dossie", "exercito:situacao", "exercito: " + SITUACAO),
        ("dossie", "exercito:exames", "exercito: " + lista_exames().replace("\n", " ")),
        ("dossie", "exercito:eaf", "exercito: " + EAF),
        ("dossie", "exercito:cronograma", "exercito: cronograma do edital: " + " | ".join(f"{_fmt(d)} {t}" for d, _, t, _ in CRONOGRAMA) + ". " + AVISO),
        ("dossie", "exercito:consulta", "exercito: Se o Dono, a Parceira ou a Mãe perguntarem prazo, data, lista de exames ou EAF do Exército, o Jarvis consulta o Cabo Tito (python -m braniac.exercito)."),
    ]


def sincronizar(agora=None):
    """Grava os fatos no banco, entrega as datas à Compasso (agenda) sem duplicar e avisa pelo barramento. Devolve o que foi feito."""
    from . import agenda, banco, barramento, modulos
    modulos.exigir("exercito")
    agora = agora or datetime.now()
    for esc, chave, texto in fatos():
        banco.gravar_fato(esc, chave, texto, nivel="local", fonte="cabo-tito")
    itens = agenda._ler()
    for i in [i for i in itens if i["titulo"] == "Inspeção de saúde para EAF"]:    # item antigo, trocava IS por EAF
        agenda.remover(i["id"])
    ja = {i["titulo"] for i in agenda._ler()}
    novos = []
    for d, h, t, cond in CRONOGRAMA:
        if d < agora.date():
            continue
        titulo = ("Exército: " + t + (f" ({cond})" if cond else ""))[:120]
        if titulo in ja:
            continue
        agenda.adicionar(titulo, f"{d.isoformat()} {h}".strip(), duracao=60 if h else 0, lembrar=1440 if h else 0, notas=AVISO[:290], agora=agora)
        novos.append(titulo)
    try:
        barramento.enviar("Cabo Tito", "Compasso", "pedido", f"Anotei na agenda {len(novos)} data(s) do processo seletivo do Exército (IS 09/11, EAF dez/jan, incorporação 01/02/2027)."[:140])
    except Exception:
        pass
    return novos


if __name__ == "__main__":
    import sys
    if "--sincronizar" in sys.argv:
        print("\n".join(sincronizar()) or "agenda já estava em dia")
    else:
        print(resposta(" ".join(a for a in sys.argv[1:]))[0])


# ---------- CHECKLIST (30/10/2026): o Dono responde o que ja fez e o Cabo Tito marca ----------
import json as _json
from pathlib import Path as _Path

CHECKLIST_JSON = _Path(__file__).parent / "data" / "exercito_checklist.json"   # fora do Git (data/)
# (nome, [palavras-chave normalizadas]) na ordem do edital; os 3 ultimos sao documentos a levar
_GRUPOS = {"sangue": range(0, 14), "laboratorio": range(14, 16), "especialistas": range(16, 21), "imagem": range(21, 27)}
ITENS = [(i, ks) for i, ks in [
    ("Hemograma completo", ["hemograma"]), ("Tipagem sanguínea e fator Rh", ["tipagem", "fator rh", "tipo sanguineo"]),
    ("Coagulograma completo", ["coagulograma"]), ("Colesterol total e frações", ["colesterol"]), ("Triglicerídeos", ["triglicer"]),
    ("Glicemia de jejum e de 2 horas", ["glicemia", "glicose"]), ("Ureia e creatinina", ["ureia", "creatinina"]), ("TGO e TGP", ["tgo", "tgp"]),
    ("PSA", ["psa"]), ("VDRL", ["vdrl", "sifilis"]), ("Chagas (IgG e IgM)", ["chagas"]), ("Hepatite B (HBsAg e Anti-HBc)", ["hepatite b", "hbsag"]),
    ("Hepatite C", ["hepatite c"]), ("HIV", ["hiv"]),
    ("Sumário de urina", ["urina", "sumario"]), ("Parasitológico de fezes", ["fezes", "parasitologico"]),
    ("Oftalmológico", ["oftalmo", "vista", "oculista"]), ("Audiometria", ["audiometria"]), ("Eletroencefalograma", ["eletroencefalo", "eeg"]),
    ("Teste ergométrico", ["ergometrico", "esteira"]), ("Aptidão psicológica p/ arma de fogo (psicólogo da PF)", ["psicolog", "arma de fogo"]),
    ("Ecocardiograma com Doppler", ["ecocardio", "eco"]), ("Ressonância dos joelhos (bilateral)", ["ressonancia", "joelho"]),
    ("Raio-X da coluna (cervical, torácica, lombar)", ["coluna"]), ("Raio-X dos campos pleuropulmonares", ["pleuropulmonar", "pulmao", "torax"]),
    ("Raio-X panorâmico dos dentes + relatório odontológico", ["panoramico", "dentes", "odontolog", "dentista"]),
    ("MAPA (pressão arterial)", ["mapa", "pressao"]),
    ("Documento oficial com foto (original)", ["documento", "rg", "identidade"]), ("CNIS", ["cnis"]), ("Roupa de banho (sunga)", ["sunga", "roupa de banho"]),
]]


def _estado():
    try:
        return set(_json.loads(CHECKLIST_JSON.read_text(encoding="utf-8")).get("feitos", []))
    except (OSError, ValueError):
        return set()


def _gravar(feitos):
    CHECKLIST_JSON.parent.mkdir(parents=True, exist_ok=True)
    CHECKLIST_JSON.write_text(_json.dumps({"feitos": sorted(feitos)}, ensure_ascii=False), encoding="utf-8")


def checklist(hoje=None):
    """Texto do checklist com ✅/⬜ numerado e a contagem; so o pendente se ja tem muita coisa feita nao muda: sempre a lista toda."""
    hoje = hoje or date.today()
    feitos = _estado()
    out = ["Checklist da Inspeção de Saúde (STT TI) — responda 'fiz hemograma e audiometria' ou 'fiz 3 e 5' que eu marco:"]
    for grupo, rng in (("Sangue", _GRUPOS["sangue"]), ("Outros laboratoriais", _GRUPOS["laboratorio"]), ("Especialistas", _GRUPOS["especialistas"]),
                       ("Imagem", _GRUPOS["imagem"]), ("Levar no dia", range(27, 30))):
        out.append(f"\n{grupo}:")
        out += [f"{'✅' if i in feitos else '⬜'} {i + 1}. {ITENS[i][0]}" for i in rng]
    falt = (IS_DIA - hoje).days
    out.append(f"\nFeitos: {len(feitos)}/{len(ITENS)}" + (f" · faltam {falt} dia(s) para a IS ({_fmt(IS_DIA)})" if falt >= 0 else ""))
    out.append("Lembrete: laudo original + cópia, com nome e CPF/RG, datado a partir de " + _fmt(EXAMES_ATE) + ".")
    return "\n".join(out)


_VERBO = re.compile(r"(?i)\b(?:j[aá]\s+)?(?:fiz|fez|feito|feitos|conclu[ií]|terminei|peguei|busquei|tenho|marca(?:r)?|desmarca(?:r)?|n[aã]o\s+fiz|ainda\s+n[aã]o\s+fiz)\b")
_PEDE_LISTA = re.compile(r"(?i)\bchecklist\b|\bcheck\s*list\b|o\s+que\s+(?:falta|j[aá]\s+fiz)\b.{0,25}\bexames?\b|quais\s+exames\s+(?:faltam|j[aá]\s+fiz)")


def eh_checklist(texto):
    from . import modulos
    t = texto or ""
    if not modulos.ativo("exercito") or len(t) > 400:
        return False
    return bool(_PEDE_LISTA.search(t)) or (bool(_VERBO.search(t)) and bool(_achar(re.sub(r"\d+", " ", t))[0] or re.search(r"(?i)\bexames?\b", t) or CHAVE.search(t)))


def _achar(texto):
    """(indices achados, grupos) a partir de palavras-chave, numeros ('3 e 5', '1-4') e nomes de grupo."""
    import unicodedata
    t = "".join(c for c in unicodedata.normalize("NFD", (texto or "").lower()) if unicodedata.category(c) != "Mn")
    achados = set()
    for i, (_, ks) in enumerate(ITENS):
        if any(re.search(r"\b" + re.escape(k), t) for k in ks):
            achados.add(i)
    for a, b in re.findall(r"\b(\d{1,2})\s*(?:a|ate|-)\s*(\d{1,2})\b", t):
        achados |= {n - 1 for n in range(int(a), int(b) + 1) if 1 <= n <= len(ITENS)}
    for n in re.findall(r"\b(\d{1,2})\b", re.sub(r"\b\d{1,2}\s*(?:a|ate|-)\s*\d{1,2}\b", " ", t)):
        if 1 <= int(n) <= len(ITENS):
            achados.add(int(n) - 1)
    grupos = [g for g, kw in (("sangue", r"\bsangue\b|\bexames? de sangue"), ("laboratorio", r"\blaboratori"), ("imagem", r"\bimagens?\b"), ("especialistas", r"\bespecialist"))
              if re.search(kw, t)]
    if re.search(r"\btudo\b|\btodos\b|\btodas\b", t) and not grupos and re.search(r"\bexames?\b|\btudo\b", t):
        grupos = list(_GRUPOS)
    for g in grupos:
        achados |= set(_GRUPOS[g])
    return achados, grupos


def marcar(texto):
    """Marca (ou desmarca, se disser 'desmarca'/'nao fiz') o que o Dono disse. Devolve o texto de resposta com o checklist atualizado."""
    achados, _ = _achar(texto)
    neg = re.search(r"(?i)desmarca|n[aã]o\s+fiz|ainda\s+n[aã]o", texto or "")
    if _PEDE_LISTA.search(texto or "") and not _VERBO.search(texto or ""):
        return checklist()
    if not achados:
        return "Não entendi qual exame. Diga o nome (ex.: 'fiz hemograma e audiometria') ou o número da lista.\n\n" + checklist()
    feitos = _estado()
    feitos = feitos - achados if neg else feitos | achados
    _gravar(feitos)
    nomes = ", ".join(ITENS[i][0] for i in sorted(achados))
    return (("Desmarquei: " if neg else "Marquei como feito: ") + nomes + ".\n\n" + checklist())


def selftest():
    global CHECKLIST_JSON
    import tempfile
    CHECKLIST_JSON = _Path(tempfile.mkdtemp()) / "c.json"
    assert "Marquei" in marcar("fiz hemograma e audiometria") and _estado() == {0, 17}
    marcar("fiz 3 e 5-6"); assert {2, 4, 5} <= _estado()
    marcar("fiz todos os exames de sangue"); assert set(range(14)) <= _estado()
    marcar("não fiz hiv"); assert 13 not in _estado()
    assert eh_checklist("o que falta dos exames?") is True and not eh_checklist("tenho 2 filhos") and not eh_checklist("o que falta?") and "Feitos:" in checklist()
