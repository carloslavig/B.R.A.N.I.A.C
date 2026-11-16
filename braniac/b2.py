# -*- coding: utf-8 -*-
"""B.R.A.N.I.A.C 1 (24/10/2026): projetos e conversas SEPARADOS (cada conversa tem historico proprio, 'b2:<id>'), instrucoes por projeto
e habilidades novas criadas pela interface ou pelo proprio Jarvis (ideia do Hermes Agent: o agente guarda o passo a passo que deu certo).
Tudo local em data/b2.db; as mensagens continuam no mesmo banco do Jarvis (store.msgs)."""
import json
import os
from pathlib import Path
import re
import sqlite3
import time

from .store import DATA

DB = DATA / "b2.db"
SKILLS = DATA.parent / "skills"
RELATORIO = DATA / "relatorio_noturno.md"


def _con():
    c = sqlite3.connect(DB)
    c.executescript("""
        CREATE TABLE IF NOT EXISTS projetos(id INTEGER PRIMARY KEY, nome TEXT NOT NULL, instrucoes TEXT DEFAULT '', criado REAL);
        CREATE TABLE IF NOT EXISTS conversas(id INTEGER PRIMARY KEY, projeto INTEGER, titulo TEXT, criado REAL, atualizado REAL, arquivada INTEGER DEFAULT 0);
    """)
    if not c.execute("SELECT 1 FROM projetos").fetchone():
        c.execute("INSERT INTO projetos(nome, instrucoes, criado) VALUES('Geral', '', ?)", (time.time(),))
        c.commit()
    if "modulos" not in [r[1] for r in c.execute("PRAGMA table_info(conversas)")]:
        c.execute("ALTER TABLE conversas ADD COLUMN modulos TEXT")   # JSON com os agentes liberados; NULL = conversa antiga (todos)
        c.commit()
    return c


def estado():
    with _con() as c:
        p = [dict(zip(("id", "nome", "instrucoes"), r)) for r in c.execute("SELECT id, nome, instrucoes FROM projetos ORDER BY id")]
        v = [dict(zip(("id", "projeto", "titulo", "atualizado", "modulos"), r))
             for r in c.execute("SELECT id, projeto, titulo, atualizado, modulos FROM conversas WHERE arquivada=0 ORDER BY atualizado DESC LIMIT 300")]
    for x in v:
        x["modulos"] = None if x["modulos"] is None else json.loads(x["modulos"])
    from . import delegacao
    return {"projetos": p, "conversas": v, "modulos_disponiveis": sorted(delegacao.AGENTES)}


def modulos_da_conversa(conv_id):
    """Agentes liberados nesta conversa (lista) ou None = conversa antiga, sem restricao."""
    with _con() as c:
        r = c.execute("SELECT modulos FROM conversas WHERE id=?", (int(conv_id),)).fetchone()
    return None if not r or r[0] is None else json.loads(r[0])


def _texto(v, n):
    v = str(v or "").strip()
    if not v or len(v) > n:
        raise ValueError(f"texto vazio ou maior que {n} caracteres")
    return v


def acao(d):
    """Uma acao da interface. Devolve o estado novo (ou o id criado em 'novo')."""
    a = d.get("acao")
    with _con() as c:
        if a == "criar_projeto":
            cur = c.execute("INSERT INTO projetos(nome, instrucoes, criado) VALUES(?,?,?)",
                            (_texto(d.get("nome"), 80), str(d.get("instrucoes") or "")[:4000], time.time()))
            novo = cur.lastrowid
        elif a == "editar_projeto":
            c.execute("UPDATE projetos SET nome=?, instrucoes=? WHERE id=?",
                      (_texto(d.get("nome"), 80), str(d.get("instrucoes") or "")[:4000], int(d["id"])))
            novo = int(d["id"])
        elif a == "criar_conversa":
            agora = time.time()
            from . import delegacao
            mods = [m for m in (d.get("modulos") or []) if m in delegacao.AGENTES]
            cur = c.execute("INSERT INTO conversas(projeto, titulo, criado, atualizado, modulos) VALUES(?,?,?,?,?)",
                            (int(d.get("projeto") or 1), str(d.get("titulo") or "Nova conversa")[:80], agora, agora, json.dumps(mods)))
            novo = cur.lastrowid
        elif a == "modulos":   # o Dono escolhe quais agentes esta conversa pode usar
            from . import delegacao
            c.execute("UPDATE conversas SET modulos=? WHERE id=?",
                      (json.dumps([m for m in (d.get("modulos") or []) if m in delegacao.AGENTES]), int(d["id"])))
            novo = int(d["id"])
        elif a == "renomear":
            c.execute("UPDATE conversas SET titulo=? WHERE id=?", (_texto(d.get("titulo"), 80), int(d["id"])))
            novo = int(d["id"])
        elif a == "mover":
            c.execute("UPDATE conversas SET projeto=? WHERE id=?", (int(d["projeto"]), int(d["id"])))
            novo = int(d["id"])
        elif a == "arquivar":   # nada e apagado: so some da lista
            c.execute("UPDATE conversas SET arquivada=1 WHERE id=?", (int(d["id"]),))
            novo = int(d["id"])
        elif a == "aparencia":
            return {"aparencia": salvar_aparencia(d.get("nome"), d.get("cor")), **estado()}
        elif a == "abrir_conta":
            return {"ok": abrir_conta(d.get("nome")), **estado()}
        elif a == "criar_skill":
            return {"skill": criar_skill(d.get("nome"), d.get("descricao"), d.get("passos"), d.get("ferramentas", "")), **estado()}
        else:
            raise ValueError("acao desconhecida")
    return {"novo": novo, **estado()}


def contexto_da_conversa(conv_id):
    """Texto extra que vai junto com a mensagem: projeto e suas instrucoes. Atualiza a data e da titulo a conversa nova."""
    with _con() as c:
        r = c.execute("SELECT p.nome, p.instrucoes FROM conversas v JOIN projetos p ON p.id=v.projeto WHERE v.id=?", (int(conv_id),)).fetchone()
        c.execute("UPDATE conversas SET atualizado=? WHERE id=?", (time.time(), int(conv_id)))
    if not r:
        raise ValueError("conversa nao existe")
    nome, instr = r
    return f"\n\n[Projeto: {nome}." + (f" Instrucoes do projeto: {instr.strip()}" if instr.strip() else "") + "]"


def titulo_inicial(conv_id, texto):
    with _con() as c:
        c.execute("UPDATE conversas SET titulo=? WHERE id=? AND titulo='Nova conversa'", (" ".join(texto.split())[:60], int(conv_id)))


def mensagens(store, conv_id, n=200):
    rows = store.db.execute("SELECT role, content, provider, ts FROM msgs WHERE conv=? ORDER BY id DESC LIMIT ?", (f"b2:{int(conv_id)}", n)).fetchall()
    limpa = lambda t: re.sub(r"\n\n\[Projeto: [^\]]*\]$", "", t or "")   # o contexto do projeto nao aparece na tela
    return [{"role": r, "content": limpa(c), "provedor": p, "ts": t} for r, c, p, t in reversed(rows)]


def criar_skill(nome, descricao, passos, ferramentas=""):
    """Habilidade nova (formato Agent Skills). Nao sobrescreve uma que ja existe. Devolve o nome."""
    slug = re.sub(r"[^a-z0-9]+", "-", str(nome or "").lower()).strip("-")[:40]
    if not slug or not str(descricao or "").strip() or not str(passos or "").strip():
        raise ValueError("habilidade precisa de nome, descricao (quando usar) e passos")
    pasta = SKILLS / slug
    if pasta.exists():
        raise ValueError(f"ja existe uma habilidade chamada {slug}")
    ferr = " ".join(re.findall(r"[a-z_]+", str(ferramentas)))
    pasta.mkdir(parents=True)
    (pasta / "SKILL.md").write_text(
        f"---\nname: {slug}\ndescription: {' '.join(str(descricao).split())[:300]}\n" + (f"allowed-tools: {ferr}\n" if ferr else "")
        + f"metadata:\n  origem: criada pelo B.R.A.N.I.A.C 1 em {time.strftime('%d/%m/%Y')}\n---\n\n# {str(nome).strip()}\n\n{str(passos).strip()}\n",
        encoding="utf-8")
    return slug


def relatorio():
    """Devolve o texto do relatorio noturno ou 'Nada registrado ainda.' se nao existir/estiver vazio."""
    try:
        texto = RELATORIO.read_text(encoding="utf-8").strip()
        return texto if texto else "Nada registrado ainda."
    except OSError:
        return "Nada registrado ainda."


CONTAS = {"chatgpt": "https://chatgpt.com/", "gemini": "https://gemini.google.com/app", "grok": "https://grok.com/",
          "deepseek": "https://chat.deepseek.com/", "kimi": "https://www.kimi.ai/", "claude": "https://claude.ai/", "google": "https://myaccount.google.com/"}


def contas():
    """Situacao das contas no navegador do Braniac (Chrome do agente, porta 9222): aba aberta? pede login?"""
    import json as _j, urllib.request
    try:
        abas = _j.loads(urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=4).read())
    except OSError:
        return {"navegador": False, "contas": []}
    out = []
    for nome, url in CONTAS.items():
        dom = url.split("/")[2]
        aba = next((a for a in abas if a.get("type") == "page" and dom in a.get("url", "")), None)
        login = bool(aba and re.search(r"sign_?in|login|signin|auth|accounts\.google", aba["url"], re.I))
        out.append({"nome": nome, "aberta": bool(aba), "precisa_login": login, "url": aba["url"] if aba else url})
    return {"navegador": True, "contas": out}


def abrir_conta(nome):
    """Traz para a frente (ou abre) a aba da conta no navegador do Braniac, para o Dono fazer login la."""
    import json as _j, urllib.request
    url = CONTAS.get(nome)
    if not url:
        raise ValueError("conta desconhecida")
    dom = url.split("/")[2]
    abas = _j.loads(urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=4).read())
    aba = next((a for a in abas if a.get("type") == "page" and dom in a.get("url", "")), None)
    if aba:
        urllib.request.urlopen(f"http://127.0.0.1:9222/json/activate/{aba['id']}", timeout=4).read()
    else:
        urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:9222/json/new?{url}", method="PUT"), timeout=6).read()
    return f"aba de {nome} na frente do navegador do Braniac"


# ---------- ciclo de aprendizado (ideia do Hermes Agent) ----------
_APRENDIDAS = {"dia": None, "n": 0}
MAX_APRENDIDAS_DIA = 3


def procurar_conversas(store, termo, n=8):
    """Busca nas conversas antigas do Jarvis (todas as fontes) pelo termo; devolve trechos com data. Nada sai do PC."""
    termo = str(termo or "").strip()
    if len(termo) < 3:
        return "Diga pelo menos 3 letras do que procurar."
    rows = store.db.execute("SELECT ts, conv, role, content FROM msgs WHERE content LIKE ? ORDER BY id DESC LIMIT ?", (f"%{termo}%", n)).fetchall()
    if not rows:
        return f"Nao achei '{termo}' nas conversas guardadas."
    fmt = lambda c: " ".join(re.sub(r"\[Projeto: [^\]]*\]|\[Conversa recente[^\]]*\]", "", c or "").split())
    return "\n".join(f"{time.strftime('%d/%m %H:%M', time.localtime(ts))} [{conv}] {'Dono' if r == 'user' else 'Jarvis'}: {fmt(c)[:220]}"
                     for ts, conv, r, c in rows)


def aprender(router, pedido, feitos, registrar=None):
    """Depois de uma tarefa com 3+ ferramentas diferentes, uma IA gratis decide se vale guardar como habilidade; se valer, cria.
    Limite de 3 por dia. registrar(texto) anota no relatorio da manha."""
    import json as _j
    usadas = sorted({n for n, _ in feitos if n not in ("usar_skill", "criar_habilidade")})
    if len(usadas) < 3 or any(n == "criar_habilidade" for n, _ in feitos):
        return None
    hoje = time.strftime("%Y-%m-%d")
    if _APRENDIDAS["dia"] != hoje:
        _APRENDIDAS.update(dia=hoje, n=0)
    if _APRENDIDAS["n"] >= MAX_APRENDIDAS_DIA:
        return None
    passos = "\n".join(f"- {n}: {r[:160]}" for n, r in feitos[:12])
    sistema = ("Voce decide se uma tarefa resolvida por um assistente vale virar HABILIDADE reutilizavel (passo a passo). Responda SO um JSON: "
               '{"vale": true|false, "nome": "kebab-case", "descricao": "quando usar (1 frase)", "passos": "1. ...\n2. ...", "ferramentas": "nomes separados por espaco"}. '
               "vale=false se for algo unico, pessoal demais ou trivial.")
    try:
        resp = router.responder_neutro(sistema, f"Pedido: {pedido[:500]}\nFerramentas usadas e resultados:\n{passos}\nFerramentas: {' '.join(usadas)}")
        texto = resp[0] if isinstance(resp, tuple) else resp
        d = _j.loads(re.search(r"\{.*\}", texto, re.S).group(0), strict=False)   # IA costuma por quebra de linha crua dentro do texto
        if not d.get("vale"):
            return None
        nome = criar_skill(d["nome"], d["descricao"], d["passos"], d.get("ferramentas") or " ".join(usadas))
    except Exception:
        return None
    _APRENDIDAS["n"] += 1
    if registrar:
        registrar(f"O Jarvis aprendeu uma habilidade nova sozinho: '{nome}' ({d['descricao'][:120]}). Veja na aba Habilidades do B.R.A.N.I.A.C 1.")
    return nome


# ---------- janela do B.R.A.N.I.A.C 1 (app em Rust) ----------
# O app pergunta a cada 1 s se deve abrir alguma aba (/api/b2/sinal); assim o servidor sabe que ele esta aberto e pode chama-lo.
APP = DATA.parent.parent / "braniac2-app" / "target" / "release" / "braniac2.exe"
SINAL = {"aba": None, "visto": 0.0}


def ler_sinal():
    SINAL["visto"] = time.time()
    aba, SINAL["aba"] = SINAL["aba"], None
    return aba


def app_aberto():
    return time.time() - SINAL["visto"] < 4


def abrir_no_app(aba="jarvis"):
    """'Jarvis, ta acordado?' abre a aba do Jarvis DENTRO do programa (Dono, 24/10). False = app nao existe (usa o jeito antigo)."""
    if app_aberto():
        SINAL["aba"] = aba
        return True
    if APP.exists():
        import subprocess
        subprocess.Popen([str(APP), f"--{aba}"], cwd=str(DATA.parent.parent))
        return True
    return False


# ---------- aparencia (nome da IA e cor), escolhida na primeira abertura do programa ----------
APARENCIA = DATA / "aparencia.json"
CORES = {"ciano": "#2fe3ff", "azul": "#3b82f6", "verde": "#22c55e", "roxo": "#a855f7", "rosa": "#ec4899",
         "laranja": "#f97316", "vermelho": "#ef4444", "dourado": "#eab308"}


def aparencia():
    """{'nome','cor','configurado'}; padrao Jarvis/ciano enquanto ninguem escolheu."""
    import json as _j
    try:
        d = _j.loads(APARENCIA.read_text(encoding="utf-8"))
        return {"nome": d["nome"], "cor": d["cor"], "configurado": True, "cores": CORES}
    except (OSError, ValueError, KeyError):
        return {"nome": "Jarvis", "cor": CORES["ciano"], "configurado": False, "cores": CORES}


def salvar_aparencia(nome, cor):
    import json as _j
    nome = " ".join(str(nome or "").split())[:24]
    if not re.fullmatch(r"[\wÀ-ÿ .'-]{2,24}", nome, re.U):
        raise ValueError("nome precisa ter de 2 a 24 letras")
    cor = CORES.get(str(cor), str(cor)).lower()
    if not re.fullmatch(r"#[0-9a-f]{6}", cor):
        raise ValueError("cor invalida")
    APARENCIA.write_text(_j.dumps({"nome": nome, "cor": cor}, ensure_ascii=False), encoding="utf-8")
    return aparencia()



# ---- chaves de IA pela interface (24/10/2026): o Dono cola a chave na aba "Chaves" em vez de editar o .env ----
CHAVES = [   # (variavel no .env, nome, onde criar a chave gratis)
    ("GEMINI_API_KEY", "Gemini (Google)", "https://aistudio.google.com/apikey"),
    ("GEMINI_API_KEY_2", "Gemini (2ª chave)", "https://aistudio.google.com/apikey"),
    ("GROQ_API_KEY", "Groq", "https://console.groq.com/keys"),
    ("OPENROUTER_API_KEY", "OpenRouter", "https://openrouter.ai/keys"),
    ("CEREBRAS_API_KEY", "Cerebras", "https://cloud.cerebras.ai/"),
    ("MISTRAL_API_KEY", "Mistral", "https://console.mistral.ai/api-keys"),
    ("NVIDIA_API_KEY", "NVIDIA NIM", "https://build.nvidia.com/"),
    ("HUGGINGFACE_API_KEY", "HuggingFace", "https://huggingface.co/settings/tokens"),
    ("SAMBANOVA_API_KEY", "SambaNova", "https://cloud.sambanova.ai/apis"),
    ("CLOUDFLARE_API_KEY", "Cloudflare Workers AI", "https://dash.cloudflare.com/profile/api-tokens"),
]
ENV_ARQ = Path(__file__).resolve().parent / ".env"


def chaves():
    """Quais chaves estao configuradas (NUNCA devolve o valor)."""
    return [{"env": e, "nome": n, "onde": u, "ativa": bool(os.environ.get(e, "").strip())} for e, n, u in CHAVES]


def salvar_chave(env, valor, router=None, arquivo=None):
    """Grava a chave no .env (criptografada pelo Windows quando possivel), ativa na hora e coloca os modelos dela na cadeia. Nao devolve o valor."""
    if env not in {e for e, _, _ in CHAVES}:
        raise ValueError("variavel desconhecida")
    valor = (valor or "").strip().strip('"').strip("'")
    if not re.fullmatch(r"[A-Za-z0-9_\-\.:=+/]{8,400}", valor):
        raise ValueError("chave invalida: use so a chave, sem espacos nem aspas (8 a 400 caracteres)")
    from . import segredos
    p = Path(arquivo or ENV_ARQ)
    linhas = p.read_text(encoding="utf-8-sig").splitlines() if p.exists() else []
    guardado = valor
    if os.name == "nt":
        cif = segredos.proteger(valor)
        guardado = cif if segredos.revelar(cif) == valor else valor
    nova = f"{env}={guardado}"
    for i, l in enumerate(linhas):
        if l.split("=", 1)[0].strip() == env:
            linhas[i] = nova
            break
    else:
        linhas.append(nova)
    tmp = p.with_suffix(".env.tmp")
    tmp.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    tmp.replace(p)
    os.environ[env] = valor
    novos = []
    if router is not None:
        from . import gratis
        novos = gratis.estender(router.cfg)
    return {"ok": True, "env": env, "novos_modelos": novos}



# ---- anexos e audio pela interface (25/10/2026): foto no chat (lida pelo Ollama) e fala por voz (Whisper local) ----
_PARTES = {}
ANEXOS = DATA / "anexos"


def juntar_partes(d):
    """Envio em pedacos (o tunel do celular aceita ~64 KB por mensagem): {id, i, n, parte(base64)}. Devolve os bytes quando chegou tudo, senao None."""
    cid, i, n = str(d.get("id", ""))[:40], int(d.get("i", 0)), int(d.get("n", 1))
    if not cid or n < 1 or n > 400:
        raise ValueError("envio invalido")
    if len(_PARTES) > 20:
        _PARTES.clear()
    _PARTES.setdefault(cid, {})[i] = d.get("parte", "")
    if len(_PARTES[cid]) < n:
        return None
    import base64 as _b
    partes = _PARTES.pop(cid)
    txt = "".join(partes[k] for k in range(n))
    return _b.b64decode(txt)


def salvar_anexo(dados, nome="foto.jpg", descrever=None):
    """Guarda a imagem em data/anexos e le com o Ollama (local primeiro). Devolve {caminho, descricao}."""
    if len(dados) > 12_000_000:
        raise ValueError("imagem grande demais (maximo 12 MB)")
    ext = ".png" if dados[:4] == b"\x89PNG" else ".jpg"
    ANEXOS.mkdir(parents=True, exist_ok=True)
    caminho = ANEXOS / (time.strftime("%Y%m%d_%H%M%S") + ext)
    caminho.write_bytes(dados)
    from . import imagem
    try:
        desc = (descrever or imagem.descrever)(dados, imagem.PROMPT_LER, 150)
    except Exception as e:
        desc = f"(nao consegui ler a imagem agora: {str(e)[:80]})"
    return {"caminho": str(caminho), "descricao": desc}


def transcrever_audio(wav):
    import os as _os, tempfile
    from . import voz
    fd, cam = tempfile.mkstemp(suffix=".wav")
    try:
        with _os.fdopen(fd, "wb") as f:
            f.write(wav)
        return voz.transcrever(cam, rapido=True)
    finally:
        try:
            _os.unlink(cam)
        except OSError:
            pass
