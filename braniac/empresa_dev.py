# -*- coding: utf-8 -*-
"""EMPRESA DE DESENVOLVIMENTO (29/10/2026, pedido do Dono): o "2o andar" do Braniac. Uma software house de agentes (front, back, APIs, juniores, QA...),
cada um com persona e modelo proprio, que trabalham varios projetos em paralelo por TICKETS. Equipe, nome da empresa e fluxo vieram do conselho de IAs
(data/conselho_dev.txt) e ficam em data/empresa_dev/equipe.json. O SENIOR e o Claude (CLI, assinatura do Dono): so entra em ticket critico ou depois de
2 reprovacoes, com teto diario. Os demais usam o roteador gratuito (router.responder_neutro).
Fluxo: novo -> desenvolvimento -> revisao (lider) -> qa -> pronto. Travas: agente SO escreve em data/empresa_dev/projetos/<projeto>/ (texto/codigo
proposto, nunca executa nem faz push nem deploy); entrega final so com o OK do Dono; nada de segredo/dado pessoal em ticket; teto de tickets por dia."""
import json
from pathlib import Path
import re
import threading
import time
import unicodedata
from datetime import datetime

from .store import DATA

PASTA = DATA / "empresa_dev"
PROJETOS = PASTA / "projetos"
EQUIPE_JSON = PASTA / "equipe.json"
TICKETS_JSON = PASTA / "tickets.json"
_lock = threading.RLock()
MAX_TICKETS_DIA = 6          # tickets trabalhados por dia (gratis; protege os provedores)
MAX_CLAUDE_DIA = 3           # revisoes do senior (Claude) por dia
MAX_TENTATIVAS = 3           # ciclos desenvolver->revisar antes de escalar ao senior/Dono
ESTADOS = ("novo", "desenvolvimento", "revisao", "qa", "pronto", "bloqueado", "entregue")
SEGREDO = re.compile(r"(?i)\bsenha\b|\bcvv\b|\bcpf\b|api[_ -]?key|secret|\btoken\b|cart[aã]o|\bpix\b")
PADRAO = {   # usado so se o conselho/Dono ainda nao definiu a equipe (equipe.json manda)
    "empresa": "Software House Braniac",
    "agentes": [
        {"nome": "Lia", "papel": "Product Owner / Gerente", "area": "gestao", "nivel": "gestao", "modelo": "gratis",
         "instrucao": "Você é a gerente de produto. Quebra pedidos em tickets pequenos, define critério de aceite e escolhe quem faz."},
        {"nome": "Nina", "papel": "Dev Front End", "area": "front", "nivel": "pleno", "modelo": "gratis",
         "instrucao": "Você é dev front end (HTML, CSS, JS, React). Entrega código completo, acessível e responsivo."},
        {"nome": "Beto", "papel": "Dev Back End", "area": "back", "nivel": "pleno", "modelo": "gratis",
         "instrucao": "Você é dev back end (Python, Node, bancos). Código simples, validado nas bordas, com tratamento de erro."},
        {"nome": "Ravi", "papel": "Dev de APIs", "area": "api", "nivel": "pleno", "modelo": "gratis",
         "instrucao": "Você desenha e implementa APIs REST: contrato primeiro, erros claros, versionamento, exemplos de chamada."},
        {"nome": "Juca", "papel": "Dev Júnior", "area": "junior", "nivel": "junior", "modelo": "gratis",
         "instrucao": "Você é dev júnior: faz tarefas pequenas e bem definidas, pergunta quando há dúvida e nunca inventa requisito."},
        {"nome": "Dora", "papel": "QA / Testes", "area": "qa", "nivel": "pleno", "modelo": "gratis",
         "instrucao": "Você é QA: escreve casos de teste, procura falhas e só aprova com evidência."},
        {"nome": "Sênior", "papel": "Arquiteto Sênior (Claude)", "area": "senior", "nivel": "senior", "modelo": "claude",
         "instrucao": "Você é o arquiteto sênior: revisa o que os outros entregaram, decide arquitetura e desempata."},
    ],
}


def _norm(x):
    return unicodedata.normalize("NFKD", x or "").encode("ascii", "ignore").decode().lower()


def _ler(p, padrao):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return padrao


def _gravar(p, dado):
    PASTA.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(dado, ensure_ascii=False, indent=1), encoding="utf-8")
    for i in range(10):                      # Windows: antivirus/leitor segurando o arquivo da WinError 5 por instantes
        try:
            tmp.replace(p)
            return
        except PermissionError:
            if i == 9:
                raise
            time.sleep(0.5)


def config():
    return _ler(EQUIPE_JSON, PADRAO)


def limite(chave):
    """Tetos diarios: equipe.json pode trazer {"limites": {"passos_dia": 12, "claude_dia": 5}}; senao valem as constantes."""
    padrao = {"passos_dia": MAX_TICKETS_DIA, "claude_dia": MAX_CLAUDE_DIA}[chave]
    try:
        return max(0, int(config().get("limites", {}).get(chave, padrao)))
    except (TypeError, ValueError):
        return padrao


def agentes():
    return config().get("agentes", [])


def nomes():
    return [a["nome"] for a in agentes()]


def sala_de(a):
    """Sala do agente no 2o andar do escritorio (Sauraki): equipe.json pode trazer 'sala'; senao deduz do papel."""
    return {"gestao": "Produto", "front": "Desenvolvimento", "back": "Desenvolvimento", "api": "Desenvolvimento", "junior": "Júniors",
            "qa": "Qualidade", "senior": "Arquitetura"}.get(a["area"], "Desenvolvimento")


def _por_nome(nome):
    return next((a for a in agentes() if a["nome"] == nome), None)


def _tickets():
    return _ler(TICKETS_JSON, [])


def _gravar_tickets(ts):
    _gravar(TICKETS_JSON, ts)


def _hoje():
    return datetime.now().strftime("%Y-%m-%d")


def _contagem(chave):
    d = _ler(PASTA / "uso.json", {})
    return d.get(_hoje(), {}).get(chave, 0)


def _somar(chave):
    d = _ler(PASTA / "uso.json", {})
    d = {_hoje(): d.get(_hoje(), {})}                   # guarda so o dia de hoje
    d[_hoje()][chave] = d[_hoje()].get(chave, 0) + 1
    _gravar(PASTA / "uso.json", d)


def escolher(area):
    """Quem pega o ticket: dev da area; area desconhecida ou 'pequeno' vai ao junior; sem ninguem, ao primeiro pleno."""
    ag = agentes()
    for a in ag:
        if a["area"] == area and a["modelo"] != "claude" and a["area"] != "gestao":
            return a
    irmao = next((a for a in ag if a["nivel"] == "junior"), None)
    return irmao or next((a for a in ag if a["nivel"] == "pleno"), None)


def abrir(projeto, titulo, descricao="", area="", critico=False):
    """Novo ticket. Recusa segredo/dado pessoal no texto (os agentes usam IAs online gratuitas)."""
    if SEGREDO.search(f"{titulo} {descricao}"):
        return None, "Ticket recusado: tem palavra de segredo/dado pessoal (senha, token, CPF, cartão, Pix). Tire e abra de novo."
    if len(titulo.strip()) < 5:
        return None, "Ticket sem título."
    proj = re.sub(r"[^a-z0-9]+", "-", _norm(projeto)).strip("-")[:40] or "geral"
    with _lock:
        ts = _tickets()
        t = {"id": f"T{len(ts) + 1:03d}", "projeto": proj, "titulo": titulo.strip()[:140], "descricao": descricao.strip()[:2000],
             "area": area or _inferir_area(f"{titulo} {descricao}"), "critico": bool(critico), "estado": "novo", "responsavel": None,
             "tentativas": 0, "historico": [], "criado": time.time()}
        ag = escolher(t["area"])
        t["responsavel"] = ag["nome"] if ag else None
        ts.append(t)
        _gravar_tickets(ts)
    return t, f"{t['id']} aberto em {proj}: {t['titulo']} → {t['responsavel']}"


def _inferir_area(texto):
    t = _norm(texto)
    for area, pal in (("api", "api endpoint rest webhook rota swagger openapi"), ("front", "tela pagina site css html botao layout react interface visual responsivo"),
                      ("back", "banco dados sql servidor python node regra fila cron script"), ("qa", "teste testes bug falha"), ("devops", "deploy dependencia docker seguranca ci")):
        if any(p in t.split() or p in t for p in pal.split()):
            return area
    return "junior"


def _historico(t, quem, txt):
    t["historico"].append({"ts": time.time(), "quem": quem, "txt": txt[:400]})
    del t["historico"][:-12]


def _chamar_ia(sistema, prompt):
    from .router import Router
    global _router
    if _router is None:
        _router = Router()
    with _lock_ia:                                      # um pedido por vez ao roteador (dois ao mesmo tempo davam erro de None/float)
        return _router.responder_neutro(sistema, prompt)[0]


_router = None
_lock_ia = threading.Lock()
MAX_TENTATIVAS_TOTAL = 6     # depois disso o ticket para e pede o Dono (nada de laco infinito)
_ia = _chamar_ia       # testes trocam por uma funcao falsa


def _git(d, *args):
    """git no repo do projeto; devolve (ok, saida). Nunca levanta: sem git a empresa segue so com arquivos."""
    import subprocess
    if args[0] != "init" and not (d / ".git").exists():     # nunca usar o repo de uma pasta-pai (a pasta do usuario e um repo)
        return False, "sem repositório do projeto"
    try:
        r = subprocess.run(["git", "-c", "user.name=NexoDev", "-c", "user.email=nexodev@braniac.local", "-C", str(d), *args],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        return r.returncode == 0, (r.stdout or r.stderr)
    except Exception as e:
        return False, str(e)


EXT_OK = {".rs", ".c", ".h", ".cpp", ".hpp", ".cc", ".go", ".mod", ".lock", ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".json", ".md", ".txt", ".sql", ".yml", ".yaml", ".toml", ".sh", ".java", ".xml"}
_BLOCO = re.compile(r"(?:^|\n)([^\n`]{0,120})\n?```[\w+-]*[ \t]*\n(.*?)```", re.S)
_MARCA = re.compile(r"=== *ARQUIVO: *([^ \n=]+) *===[ \t]*\n(.*?)\n?=== *FIM *===", re.S)
_NOME = re.compile(r"([\w.-]+(?:/[\w.-]+)*\.[A-Za-z]{1,5})")


_ROTULO = re.compile(r"(?i)^(?:java|xml|rust|toml|c|cpp|c++|go|python|py|json|html|css|js|javascript|ts|typescript|text|txt|bash|sh|yaml|yml|sql|markdown|md|copiar( c[oó]digo)?|copy( code)?|editar|edit|baixar|download|executar|run)$")


def _limpa_rotulo(corpo):
    """O texto das IAs web traz o rotulo da cerca (ex.: 'rust') e o botao 'Copiar codigo' como linhas soltas no comeco: tira."""
    linhas = corpo.split(chr(10))
    while linhas and (_ROTULO.match(linhas[0].strip()) or not linhas[0].strip()):
        linhas.pop(0)
    return chr(10).join(linhas)


def extrair_arquivos(texto):
    """{caminho: conteudo} dos blocos de codigo cujo NOME aparece na linha logo antes do bloco ou no 1o comentario dele.
    Caminho so relativo, sem '..', extensao da lista: nada de escrever fora da pasta do projeto nem arquivo executavel."""
    out = {}
    texto = (texto or "").replace(chr(13) + chr(10), chr(10))
    for nome, corpo in _MARCA.findall(texto):          # formato pedido aos agentes: sobrevive ao texto puro das IAs web
        nome = nome.strip().lstrip("/")
        if ".." not in nome and not nome.startswith(".") and nome.rsplit("/", 1)[-1] != "build.rs" and "." + nome.rsplit(".", 1)[-1].lower() in EXT_OK:
            out.setdefault(nome, _limpa_rotulo(corpo))
    for ant, corpo in _BLOCO.findall(texto or ""):
        primeira = corpo.split(chr(10), 1)[0]
        m = _NOME.search(ant) or (_NOME.search(primeira) if re.match(r"\s*(#|//|<!--|/\*)", primeira) else None)
        if not m:
            continue
        nome = m.group(1).lstrip("/")
        if ".." in nome or nome.startswith(".") or "." + nome.rsplit(".", 1)[-1].lower() not in EXT_OK:
            continue
        out.setdefault(nome, corpo)
    return out


def _repo(d):
    d.mkdir(parents=True, exist_ok=True)
    if not (d / ".git").exists():
        _git(d, "init", "-b", "main")
        _git(d, "commit", "--allow-empty", "-m", "início do projeto")


def _commit_na_branch(t, arq, conteudo, quem):
    """Entrega vai para a branch do ticket (tNNN) num worktree temporario; a main so recebe no aprovar()."""
    d = PROJETOS / t["projeto"]
    _repo(d)
    br = t["id"].lower()
    wt = d.parent / f".wt-{t['projeto']}-{br}"
    ok, _ = _git(d, "worktree", "add", "-f", str(wt), "-B", br, br if _git(d, "rev-parse", "--verify", br)[0] else "main")
    if not ok:
        return False
    try:
        _, rastreados = _git(d, "ls-tree", "-r", "--name-only", "main")
        da_main = set((rastreados or "").split(chr(10)))
        for velho in list(wt.rglob("*")):                       # cada tentativa substitui os arquivos da anterior; o que ja esta na main fica
            rel = velho.relative_to(wt).as_posix()
            if velho.is_file() and ".git" not in velho.parts and not re.match(r"T\d+-", velho.name) and rel not in da_main:
                velho.unlink()
        (wt / arq).write_text(conteudo, encoding="utf-8")
        for nome, corpo in extrair_arquivos(conteudo).items():
            alvo = (wt / nome).resolve()
            if wt.resolve() in alvo.parents:                    # trava extra contra caminho fora do worktree
                alvo.parent.mkdir(parents=True, exist_ok=True)
                alvo.write_text(corpo, encoding="utf-8")
        _git(wt, "add", "-A")
        _git(wt, "commit", "-m", f"{t['id']} {quem}: {t['titulo'][:60]}")
    finally:
        _git(d, "worktree", "remove", "--force", str(wt))
    return True


def _salvar_entrega(t, quem, texto):
    d = PROJETOS / t["projeto"]
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{t['id']}-{_norm(quem)}-{t['tentativas']}.md"
    conteudo = (f"# {t['id']} {t['titulo']}\nAgente: {quem}\n\n{texto}\n")
    f.write_text(conteudo, encoding="utf-8")                # copia de leitura para o pipeline
    _commit_na_branch(t, f.name, conteudo, quem)
    return f.name


POLITICA = ("PÁGINAS WEB E TELAS: HTML, CSS e JS puros, leves, em um arquivo ou poucos, SEM Cargo.toml e sem framework. LINGUAGEM do resto: prioridade total para RUST (leve, rápido, sem runtime pesado). Use C, C++ ou Go só quando fizer mais sentido que Rust. "
            "Python SÓ para automação que realmente não tem jeito de fazer em Rust. Projeto novo = Cargo.toml + src/main.rs (ou lib). Sem dependências à toa.")
GPT_PROJETO = "https://chatgpt.com/g/g-p-seu_projeto-nexodev/project"


def _codar_web(sistema, prompt):
    """Gera codigo pelo PROJETO NexoDev do ChatGPT (so os agentes da empresa usam); acabou o limite/erro -> DeepSeek; senao None (cai no roteador gratis).
    Poupa as APIs gratuitas. So o texto do ticket vai (abrir() ja recusa segredo)."""
    from . import ia_web
    texto = sistema + chr(10) + chr(10) + prompt
    for site, url in (("chatgpt", config().get("gpt_projeto", GPT_PROJETO)), ("deepseek", None)):
        try:
            r = ia_web.perguntar(site, texto, timeout_s=300, projeto_url=url)
            if r and len(r.strip()) > 40:
                return r
        except Exception:
            continue
    return None


def _gerar(sistema, prompt):
    r = None
    try:
        r = _codar_web(sistema, prompt)
    except Exception:
        pass
    return r or _ia(sistema, prompt)


def _contexto_repo(t, limite=40000):
    """Arquivos que ja estao na main do projeto (o agente nao ve o repo): lista + conteudo ate `limite` caracteres."""
    d = PROJETOS / t["projeto"]
    if not (d / ".git").exists():
        return ""
    ok, lista = _git(d, "ls-tree", "-r", "--name-only", "main")
    nomes = [n for n in (lista or "").split(chr(10)) if n and not re.match(r"T\d+-", n.rsplit("/", 1)[-1])]
    if not ok or not nomes:
        return ""
    out, usado = [chr(10) + "JA EXISTE NA MAIN (nao apague; se mudar um arquivo, entregue ele COMPLETO):"], 0
    for n in nomes:
        ok2, corpo = _git(d, "show", "main:" + n)
        if not ok2 or usado + len(corpo) > limite:
            out.append("- " + n)
            continue
        usado += len(corpo)
        out.append("=== " + n + " ===" + chr(10) + corpo)
    return chr(10).join(out) + chr(10)



def desenvolver(t):
    a = _por_nome(t["responsavel"]) or escolher(t["area"])
    ultimo = next((h["txt"] for h in reversed(t["historico"]) if h["quem"] == "revisao"), "")
    prompt = (f"PROJETO: {t['projeto']}\nTICKET {t['id']}: {t['titulo']}\n{t['descricao']}\n{_contexto_repo(t)}"
              + (f"\nA revisão reprovou da última vez: {ultimo}\nCorrija.\n" if ultimo else "")
              + "\nEntregue: 1) resumo de 2 linhas do que fez; 2) o código/arquivos completos em blocos; 3) como testar. Não invente requisito; dúvida = liste no fim.")
    texto = _gerar(a["instrucao"] + " " + POLITICA + " Responda em português do Brasil. Entregue CADA arquivo EXATAMENTE neste formato, sem cercas de markdown: uma linha '=== ARQUIVO: src/main.rs ===', depois o código DENTRO de um bloco de código markdown (três crases + linguagem), depois uma linha '=== FIM ==='. Nunca escreva código fora de bloco de código. Você só propõe código em texto; não executa nada.", prompt)
    arq = _salvar_entrega(t, a["nome"], texto)
    t["tentativas"] += 1
    t["estado"] = "revisao"
    _historico(t, a["nome"], f"entregou {arq}")
    return texto


def _lider(t):
    ag = agentes()
    return next((a for a in ag if a["nivel"] == "pleno" and a["area"] == t["area"] and a["nome"] != t["responsavel"]), None) or \
        next((a for a in ag if a["nivel"] in ("pleno", "gestao") and a["nome"] != t["responsavel"]), None)


def revisar(t, entrega):
    """Revisao por colega pleno (gratis). Devolve (aprovado, comentario). Resposta precisa comecar com APROVADO ou REPROVADO."""
    r = _lider(t)
    sistema = (r["instrucao"] if r else "Você é revisor de código.") + " Revise com rigor. Responda começando EXATAMENTE com APROVADO ou REPROVADO, depois até 4 linhas de motivo."
    txt = _ia(sistema, f"TICKET {t['id']}: {t['titulo']}\n{t['descricao']}\n\nENTREGA:\n{entrega[:15000]}")
    ok = _norm(txt.strip()).startswith("aprovado")
    _historico(t, "revisao", ("APROVADO" if ok else "REPROVADO") + ": " + txt.strip()[:300])
    return ok, txt.strip()


def verificar_build(t):
    """Evidencia real para o QA: tira a branch do ticket numa pasta temporaria e roda cargo build+test (Rust) ou go build (Go).
    Devolve (ok|None, texto); None = nada compilavel (ex.: so texto/HTML). build.rs e barrado na extracao (nao roda codigo gerado no build)."""
    import shutil
    import subprocess
    import tempfile
    d = PROJETOS / t["projeto"]
    if not (d / ".git").exists():
        return None, "sem repositório"
    tmp = tempfile.mkdtemp(prefix="nexodev-")
    try:
        tar = subprocess.run(["git", "-C", str(d), "archive", t["id"].lower()], capture_output=True, timeout=30)
        if tar.returncode != 0:
            return None, "sem branch do ticket"
        subprocess.run(["tar", "-x", "-C", tmp], input=tar.stdout, timeout=30)
        raiz = Path(tmp)
        cmds = []
        if (raiz / "Cargo.toml").exists():
            cmds = [["cargo", "build", "--quiet"], ["cargo", "test", "--quiet"]]
        elif (raiz / "go.mod").exists():
            cmds = [["go", "build", "./..."]]
        if not cmds:
            return None, "nada para compilar"
        log = ""
        for c in cmds:
            try:
                r = subprocess.run(c, cwd=tmp, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
            except FileNotFoundError:
                return None, f"{c[0]} não instalado"
            except subprocess.TimeoutExpired:
                return False, f"{' '.join(c)}: passou de 5 min"
            log += f"$ {' '.join(c)} -> {r.returncode}{chr(10)}{(r.stdout + r.stderr)[-600:]}{chr(10)}"
            if r.returncode != 0:
                return False, log
        return True, log
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def qa(t, entrega):
    a = next((x for x in agentes() if x["area"] == "qa"), None)
    ok_b, log_b = verificar_build(t)
    if ok_b is False:                                    # nao compila / teste falha: reprova sem gastar IA
        _historico(t, "qa", "REPROVADO (build): " + log_b[-300:])
        _historico(t, "revisao", "REPROVADO: o build falhou. " + log_b[-500:])
        return False, log_b
    if not a:
        return True, "sem QA na equipe"
    txt = _ia(a["instrucao"] + " Responda começando EXATAMENTE com APROVADO ou REPROVADO, depois casos de teste curtos (até 6 linhas).",
              f"TICKET {t['id']}: {t['titulo']}\n{t['descricao']}\n\nENTREGA:\n{entrega[:15000]}")
    ok = _norm(txt.strip()).startswith("aprovado")
    _historico(t, "qa", ("APROVADO" if ok else "REPROVADO") + ": " + txt.strip()[:300])
    return ok, txt.strip()


def senior_precisa(t):
    return t["critico"] or t["tentativas"] >= MAX_TENTATIVAS


def senior_revisa(t, entrega, ao_terminar=None):
    """O Claude (senior) revisa; roda em segundo plano pelo mesmo mecanismo do monitor. Teto diario MAX_CLAUDE_DIA. Devolve False se estourou o teto."""
    if _contagem("claude") >= limite("claude_dia"):
        return False
    _somar("claude")
    from . import claude_agent
    tarefa = (f"REVISAO SENIOR do ticket {t['id']} do projeto {t['projeto']} ({t['titulo']}). Leia os arquivos em braniac/data/empresa_dev/projetos/{t['projeto']}/ "
              f"(entregas dos devs), aponte falhas de arquitetura, segurança e testes e diga se pode ir para a entrega. NÃO altere nada fora dessa pasta, não faça push nem deploy. "
              f"Responda em até 8 linhas começando com APROVADO ou REPROVADO.")
    claude_agent.executar_em_segundo_plano(tarefa, ao_terminar or (lambda r: _senior_resposta(t["id"], r)))
    return True


def _senior_resposta(id_, texto):
    with _lock:
        ts = _tickets()
        for t in ts:
            if t["id"] == id_:
                ok = _norm(texto.strip()).startswith("aprovado")
                _historico(t, "senior", ("APROVADO" if ok else "REPROVADO") + ": " + texto.strip()[:300])
                t["estado"] = "qa" if ok else "desenvolvimento"
                if not ok:
                    t["tentativas"] = 0                        # senior reprovou: devs recomecam o ciclo com o parecer
        _gravar_tickets(ts)


def avancar(t):
    """Da UM passo no ticket (uma chamada de IA por passo). Devolve texto curto do que aconteceu."""
    est = t["estado"]
    if est in ("novo", "desenvolvimento", "revisao", "qa") and t["tentativas"] >= MAX_TENTATIVAS_TOTAL:
        t["estado"] = "bloqueado"
        _historico(t, "sistema", f"parou após {t['tentativas']} tentativas: precisa do Dono")
        try:
            from . import barramento
            g = next((a["nome"] for a in agentes() if a["nivel"] == "gestao"), None)
            if g:
                barramento.enviar(g, "Jarvis", "alerta", f"{t['id']} ({t['titulo'][:60]}) travou após {t['tentativas']} tentativas e precisa de você.")
        except Exception:
            pass
        return f"{t['id']} travou: precisa do Dono"
    if est in ("novo", "desenvolvimento"):
        t["estado"] = "desenvolvimento"
        desenvolver(t)
        return f"{t['id']} {t['responsavel']} entregou (tentativa {t['tentativas']})"
    d = PROJETOS / t["projeto"]
    arqs = sorted(d.glob(f"{t['id']}-*.md"), key=lambda p: p.stat().st_mtime)
    entrega = arqs[-1].read_text(encoding="utf-8") if arqs else ""
    if est == "revisao":
        if (senior_precisa(t) or config().get("revisao_senior", False)) and t["estado"] != "bloqueado":
            if senior_revisa(t, entrega):
                t["estado"] = "bloqueado"                       # espera o parecer do Claude (chega em _senior_resposta)
                _historico(t, "senior", "pedido de revisão enviado ao Claude")
                return f"{t['id']} foi para o sênior (Claude)"
        ok, _ = revisar(t, entrega)
        if ok:
            t["estado"] = "qa"
            return f"{t['id']} aprovado na revisão"
        t["estado"] = "desenvolvimento"
        return f"{t['id']} reprovado na revisão, volta ao dev"
    if est == "qa":
        ok, _ = qa(t, entrega)
        t["estado"] = "pronto" if ok else "desenvolvimento"
        return f"{t['id']} " + ("passou no QA: PRONTO para o OK do Dono" if ok else "reprovou no QA, volta ao dev")
    return f"{t['id']} {est}"


def _passo(t):
    try:
        return avancar(t)
    except Exception as e:
        import traceback
        _historico(t, "sistema", "erro: " + str(e)[:120] + " | " + traceback.format_exc()[-260:].replace(chr(10), " "))
        t["estado"] = "bloqueado"
        return f"{t['id']} erro: {str(e)[:80]}"


def trabalhar(maximo=None, paralelo=3, ignorar_teto=False):
    """Um ciclo: avanca ate `paralelo` tickets de PROJETOS DIFERENTES ao mesmo tempo (no mesmo projeto, um por vez), respeitando o teto diario.
    Devolve a lista do que foi feito."""
    import concurrent.futures as cf
    trava = PASTA / ".trabalhando"                      # trava entre processos (servidor e scripts): so um ciclo por vez
    try:
        if trava.exists() and time.time() - trava.stat().st_mtime < 900:
            return []
        PASTA.mkdir(parents=True, exist_ok=True)
        trava.write_text(str(time.time()))
    except OSError:
        pass
    try:
        return _trabalhar(maximo, paralelo, ignorar_teto)
    finally:
        try:
            trava.unlink()
        except OSError:
            pass


def _trabalhar(maximo, paralelo, ignorar_teto):
    import concurrent.futures as cf
    feitos = []
    falta = (maximo or 50) if ignorar_teto else limite("passos_dia") - _contagem("passos")
    restante = min(falta, maximo or limite("passos_dia"))
    while restante > 0:
        with _lock:
            vistos, lote = set(), []
            for x in _tickets():
                if x["estado"] in ("novo", "desenvolvimento", "revisao", "qa") and x["projeto"] not in vistos and len(lote) < min(paralelo, restante):
                    vistos.add(x["projeto"])
                    lote.append(x)
        if not lote:
            break
        with cf.ThreadPoolExecutor(len(lote)) as ex:
            res = list(ex.map(_passo, lote))
        with _lock:
            atuais = _tickets()
            for novo_t in lote:
                for k, velho in enumerate(atuais):
                    if velho["id"] == novo_t["id"]:
                        atuais[k] = novo_t
            _gravar_tickets(atuais)
        feitos += res
        for _ in res:
            _somar("passos")
        restante -= len(res)
    return feitos


def aprovar(id_):
    """OK do Dono: ticket 'pronto' vira 'entregue' (so marca; deploy/publicacao continuam manuais)."""
    with _lock:
        ts = _tickets()
        t = next((x for x in ts if x["id"].lower() == (id_ or "").strip().lower()), None)
        if not t:
            return "Ticket não encontrado."
        if t["estado"] != "pronto":
            return f"{t['id']} está em {t['estado']}, ainda não está pronto."
        t["estado"] = "entregue"
        _historico(t, "dono", "OK de entrega")
        _gravar_tickets(ts)
        d = PROJETOS / t["projeto"]
        if (d / ".git").exists():
            for f in d.glob(f"{t['id']}-*.md"):             # copias de leitura: o merge traz os arquivos de volta
                f.unlink()
        merge = _git(d, "merge", "--no-ff", "-m", f"{t['id']} entregue (OK do Dono)", t["id"].lower())[0] if (d / ".git").exists() else False
    return f"{t['id']} entregue" + (" e mesclado na main." if merge else ".") + f" Os arquivos estão em data/empresa_dev/projetos/{t['projeto']}/."


def quadro():
    ts = _tickets()
    if not ts:
        return f"{config().get('empresa')}: nenhum ticket ainda."
    return f"{config().get('empresa')} ({_contagem('passos')}/{limite("passos_dia")} passos hoje):" + chr(10) + chr(10).join(
        f"• {t['id']} [{t['estado']}] {t['projeto']}: {t['titulo']} → {t['responsavel']}" for t in ts[-15:])


def situacao():
    ts = _tickets()
    por = {e: sum(1 for t in ts if t["estado"] == e) for e in ESTADOS}
    return {"empresa": config().get("empresa"), "agentes": len(agentes()), "tickets": por, "claude_hoje": _contagem("claude"), "passos_hoje": _contagem("passos")}


def daily(agora=None):
    """Daily curta (uma vez por dia util): resume o quadro e posta no barramento da Lia (ou do 1o agente de gestao)."""
    agora = agora or datetime.now()
    s = situacao()
    g = next((a["nome"] for a in agentes() if a["nivel"] == "gestao"), None)
    txt = f"Daily {config().get('empresa')}: " + ", ".join(f"{k} {v}" for k, v in s["tickets"].items() if v) or "sem tickets"
    try:
        from . import barramento
        if g:
            barramento.enviar(g, "Jarvis", "status", txt[:200])
    except Exception:
        pass
    return txt


def tick(agora=None, enviar=None):
    """Ligado ao laco da rotina (~10 min): daily 1x/dia entre 9h e 18h em dia util, e trabalha um passo por ciclo."""
    agora = agora or datetime.now()
    if not (9 <= agora.hour < 18) or agora.weekday() >= 5:
        return []
    if _ler(PASTA / "daily.json", {}).get("dia") != _hoje():
        _gravar(PASTA / "daily.json", {"dia": _hoje()})
        r = daily(agora)
        if enviar:
            enviar(r)
    return trabalhar(maximo=1)


if __name__ == "__main__":
    import sys
    print(json.dumps(situacao(), ensure_ascii=False, indent=1))
    if len(sys.argv) > 1 and sys.argv[1] == "trabalhar":
        print("\n".join(trabalhar()))
