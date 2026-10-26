# -*- coding: utf-8 -*-
"""MÓDULOS DE AGENTE (v1.1): cada módulo é um AGENTE de IA independente (nome próprio, instruções, palavras-chave, ferramentas, banco SQLite próprio).
Na instalação a pessoa ESCOLHE quais módulos quer e pode ligar/desligar depois (Configurações › Módulos). O assistente principal detecta o assunto da
mensagem e entrega SÓ o contexto do agente certo (poucas linhas: gasta pouco custo de IA). Tudo local: nada de um módulo sai do PC.

Segurança: um módulo é uma PASTA com manifest.json (dados, sem código). As FERRAMENTAS que ele pode usar vêm de uma lista fixa embutida no programa
(FERRAMENTAS abaixo); módulo de terceiros não executa código nenhum. Módulo desinstalado só deixa de responder: os dados dele continuam no PC da pessoa."""
import json
import re
import sqlite3
import threading
import time
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

from . import paths, perfil

EMBUTIDOS = Path(__file__).parent / "modulos_embutidos"
_lock = threading.RLock()
CAMPOS_OBRIGATORIOS = ("id", "nome", "agente", "descricao", "instrucao", "palavras")
CAMPOS_PROIBIDOS = ("codigo", "code", "script", "exec", "comando", "command", "python", "powershell", "url_download")
# ferramentas que um módulo pode pedir: nome -> (função, descrição curta para o prompt). Implementadas no programa; o manifest só ESCOLHE entre elas.
FERRAMENTAS = {}


def registrar_ferramenta(nome, funcao, descricao):
    FERRAMENTAS[nome] = (funcao, descricao)


def _norm(x):
    s = "".join(c for c in unicodedata.normalize("NFD", str(x).lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", s)).strip()


# ---------- catálogo ----------
def _usuario():
    p = paths.arquivo("modulos_usuario")
    p.mkdir(exist_ok=True)
    return p


def validar_manifest(m):
    """Levanta ValueError se o manifest fugir do formato ou tentar trazer código."""
    if not isinstance(m, dict):
        raise ValueError("manifest inválido")
    for c in CAMPOS_OBRIGATORIOS:
        if not m.get(c):
            raise ValueError(f"falta o campo '{c}'")
    if any(k in m for k in CAMPOS_PROIBIDOS):
        raise ValueError("módulo não pode trazer código nem comandos")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,29}", str(m["id"])):
        raise ValueError("id: só letras minúsculas, números e hífen (2 a 30)")
    if not isinstance(m["palavras"], list) or len(m["palavras"]) < 3:
        raise ValueError("palavras: pelo menos 3 palavras-chave")
    if len(str(m["instrucao"])) > 1500 or len(str(m["agente"])) > 30 or len(str(m["nome"])) > 60:
        raise ValueError("instrução (máx. 1500), agente (30) ou nome (60) grandes demais")
    for f in m.get("ferramentas") or []:
        if f not in FERRAMENTAS:
            raise ValueError(f"ferramenta desconhecida: {f}")
    return m


def catalogo():
    """[manifest] dos módulos embutidos + os da pessoa (data-only). Manifest inválido é ignorado."""
    out = {}
    for origem, base in (("embutido", EMBUTIDOS), ("seu", _usuario())):
        for arq in sorted(base.glob("*/manifest.json")):
            try:
                m = validar_manifest(json.loads(arq.read_text(encoding="utf-8-sig")))
            except (ValueError, OSError):
                continue
            if origem == "seu" and m["id"] in out:
                continue          # um módulo da pessoa nunca substitui um embutido
            m["origem"] = origem
            out[m["id"]] = m
    return list(out.values())


def _m(id_):
    return next((m for m in catalogo() if m["id"] == id_), None)


# ---------- instalação ----------
def instalados():
    ids = perfil.carregar().get("modulos") or []
    return [m for m in catalogo() if m["id"] in ids]


def estado():
    ins = {m["id"] for m in instalados()}
    return [{**{k: m.get(k) for k in ("id", "nome", "agente", "descricao", "icone", "origem", "ferramentas", "exemplos", "permissoes")}, "instalado": m["id"] in ins} for m in catalogo()]


def escolher(lista):
    """Define os módulos instalados (usado pela instalação e pela tela Módulos). Cria o banco de cada um."""
    ok = [m["id"] for m in catalogo() if m["id"] in set(lista or [])]
    perfil.atualizar(modulos=ok, modulos_escolhidos=True)
    for i in ok:
        _db(i).close()
    return ok


def instalar(id_):
    atuais = list(perfil.carregar().get("modulos") or [])
    if _m(id_) is None:
        raise ValueError("módulo desconhecido")
    return escolher(atuais + [id_]) if id_ not in atuais else atuais


def backup(id_):
    """Copia o banco do módulo para modulos/backup/ (o conselho de IAs apontou corrupção/migração como risco). Devolve o caminho ou None."""
    import shutil
    origem = paths.arquivo("modulos") / f"{id_}.db"
    if not origem.exists():
        return None
    dest = paths.arquivo("modulos") / "backup"
    dest.mkdir(exist_ok=True)
    alvo = dest / f"{id_}-{time.strftime('%Y%m%d-%H%M%S')}.db"
    shutil.copy2(origem, alvo)
    return str(alvo)


def desinstalar(id_):
    """Desliga o módulo. Os dados dele FICAM (reinstalar traz tudo de volta); antes, guarda um backup."""
    backup(id_)
    return escolher([i for i in (perfil.carregar().get("modulos") or []) if i != id_])


# ---------- banco de cada módulo ----------
def _db(id_):
    p = paths.arquivo("modulos")
    p.mkdir(exist_ok=True)
    c = sqlite3.connect(str(p / f"{id_}.db"), check_same_thread=False)
    c.executescript("""
        CREATE TABLE IF NOT EXISTS fatos(id INTEGER PRIMARY KEY, chave TEXT UNIQUE, texto TEXT, ts REAL, validade REAL, ativo INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS log(id INTEGER PRIMARY KEY, ts REAL, evento TEXT);""")
    return c


def validade_do_texto(texto, agora=None):
    """'só hoje' vale até as 5h do dia seguinte; 'esta semana' 7 dias; 'temporariamente' 3 dias. None = sem prazo."""
    agora = agora or datetime.now()
    t = _norm(texto)
    if re.search(r"\b(so|apenas|somente) (por )?hoje\b|\bso vale hoje\b", t):
        return (agora + timedelta(days=1 if agora.hour >= 5 else 0)).replace(hour=5, minute=0, second=0, microsecond=0).timestamp()
    if re.search(r"\b(nesta|esta|essa) semana\b", t):
        return (agora + timedelta(days=7)).timestamp()
    if re.search(r"\btemporariamente\b", t):
        return (agora + timedelta(days=3)).timestamp()
    return None


def lembrar(id_, chave, texto, agora=None):
    """Guarda um fato no banco do módulo (com validade, se for temporário)."""
    agora = agora or datetime.now()
    with _lock:
        c = _db(id_)
        c.execute("INSERT INTO fatos(chave,texto,ts,validade,ativo) VALUES(?,?,?,?,1) ON CONFLICT(chave) DO UPDATE SET texto=excluded.texto, ts=excluded.ts, validade=excluded.validade, ativo=1",
                  (chave[:120], texto.strip()[:600], agora.timestamp(), validade_do_texto(texto, agora)))
        c.commit()
        c.close()


# ---------- detectar o módulo e montar o contexto ----------
def detectar(texto):
    """[(id, pontos)] entre os módulos INSTALADOS, do mais forte ao mais fraco. Só palavras-chave: custo zero de IA."""
    alvo = set(_norm(texto).split())
    out = []
    for m in instalados():
        p = len(alvo & {_norm(w) for w in m["palavras"]})
        if p:
            out.append((m["id"], p))
    return sorted(out, key=lambda x: -x[1])


def contexto_para(texto, limite=1100):
    """Bloco CURTO do agente do módulo detectado: instrução + poucos fatos válidos. '' se nenhum módulo instalado casar."""
    d = detectar(texto)
    if not d:
        return ""
    m = _m(d[0][0])
    pal = set(_norm(texto).split())
    c = _db(m["id"])
    rows = c.execute("SELECT texto,ts FROM fatos WHERE ativo=1 AND (validade IS NULL OR validade>?)", (time.time(),)).fetchall()
    c.close()
    melhores = sorted(rows, key=lambda r: (-len(set(_norm(r[0]).split()) & pal), -r[1]))[:4]
    fatos = "\n".join(f"- {t[:200]}" for t, _ in melhores) or "- (nada registrado ainda)"
    return (f"\n\nMÓDULO ATIVO — responda como o agente {m['agente']} ({m['nome']}). {m['instrucao']}\nFATOS VÁLIDOS DESTE MÓDULO:\n{fatos}")[:limite]


def ferramentas_texto():
    """Linhas para o prompt do assistente: só as ferramentas dos módulos INSTALADOS (quem não instalou não gasta token com isso)."""
    linhas = []
    for m in instalados():
        for f in m.get("ferramentas") or []:
            linhas.append(f"- {f}: {FERRAMENTAS[f][1]}")
    return ("\nFerramentas dos módulos instalados (use como 'acao', com os args indicados):\n" + "\n".join(linhas)) if linhas else ""


def eh_ferramenta(acao):
    return any(acao in (m.get("ferramentas") or []) for m in instalados())


def executar(acao, args):
    """Roda uma ferramenta de módulo. Devolve o texto da resposta."""
    if not eh_ferramenta(acao):
        return "Esse módulo não está instalado. Ative em Configurações › Módulos."
    try:
        return str(FERRAMENTAS[acao][0](args or {}))
    except ValueError as e:
        return f"Não consegui: {e}"


from . import modulo_financeiro  # noqa: E402,F401  (registra as ferramentas do módulo Financeiro)
