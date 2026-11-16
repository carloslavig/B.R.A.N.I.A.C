# -*- coding: utf-8 -*-
"""ESTUDIO 3D no Braniac (11/11/2026): o Jarvis faz sozinho um RASCUNHO de video curto explicativo em 3D (vertical 1080x1920) no Estudio3D do Dono.
IA gratis escreve narracao + cenas; narrar/transcrever/render rodam localmente (sem gastar o Claude). Nao publica nada: avisa o Dono com o caminho do arquivo.
Limites: 3 videos por dia, um por vez, so conceitos gerais (sem estatistica inventada); fatos de politica/saude/financas exigem a skill estudio-3d com o Claude e fonte."""
import json
import os
import re
import subprocess
import sys
import threading
import time
import unicodedata
from pathlib import Path

from .store import DATA

PASTA = Path(os.environ.get("ESTUDIO3D", r"C:\Users\usuario\Projetos\Estudio3D"))
PECAS = ("barras", "globo", "pilha", "mapa", "numero", "linha", "moedas", "maquete")
MAX_DIA = 3
ARQ_USO = DATA / "estudio3d_uso.json"
OUTBOX = DATA / "outbox_dono.txt"
SEGREDO = re.compile(r"senha|token|cpf|cart[aã]o|pix|chave de acesso|c[oó]digo de verifica", re.I)
SENSIVEL = re.compile(r"elei[cç][aã]o|pol[ií]tic|partido|vacina|doen[cç]a|rem[eé]dio|sa[uú]de|invest|a[cç][aã]o da bolsa|criptomoeda|bitcoin|imposto", re.I)
_trava = threading.Lock()

PROMPT = ("Voce escreve roteiros de video curto explicativo (vertical, 25 a 40 segundos) com cenas 3D simples. Responda SO um JSON, sem texto fora dele: "
          '{"titulo": "...", "narracao": "frases curtas, 70 a 110 palavras, gancho na 1a frase", "cenas": [{"titulo": "ate 4 palavras", "peca": "barras|globo|pilha", '
          '"dados": {"valores": [numeros] ou "itens": 1 a 12}}]}. 4 a 6 cenas na ordem da narracao. Pecas: barras = comparar/crescer (dados.valores com 3 a 6 numeros so ilustrativos), '
          "globo = mundo/rede/dados, pilha = acumular (dados.itens). NAO invente estatistica, data, nome ou fonte; explique so conceitos gerais e bem conhecidos. Portugues do Brasil.")


def _norm(t):
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()


def slug(titulo):
    return re.sub(r"[^a-z0-9]+", "-", _norm(titulo)).strip("-")[:40] or "video"


def proximo_numero():
    nums = [int(m.group(1)) for p in (PASTA / "projetos").glob("[0-9][0-9][0-9]-*") if (m := re.match(r"(\d{3})-", p.name))]
    return f"{(max(nums) + 1) if nums else 1:03d}"


def _usos_hoje():
    try:
        d = json.loads(ARQ_USO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    return d if d.get("dia") == time.strftime("%Y-%m-%d") else {"dia": time.strftime("%Y-%m-%d"), "n": 0}


def validar(dados):
    """Dicionario do rascunho -> (titulo, narracao, cenas validas) ou levanta ValueError."""
    narr = re.sub(r"\s+", " ", str(dados.get("narracao") or "")).strip()
    if len(narr.split()) < 25:
        raise ValueError("narracao curta demais")
    if SEGREDO.search(narr):
        raise ValueError("narracao com palavra de segredo")
    return str(dados.get("titulo") or "Video explicativo")[:80], narr, validar_cenas(dados.get("cenas"))


def _limpo(v, prof=0):
    """So DADOS simples (texto curto, numero, lista, dicionario) para os enfeites do padrao Parceiro (folha PDF, plaquinhas, faixa, destaques).
    Nada vira codigo: o estudio so escreve isso como texto."""
    if isinstance(v, bool) or isinstance(v, (int, float)) and abs(v) < 1e13:
        return v
    if isinstance(v, str):
        return v[:120]
    if prof < 4 and isinstance(v, list):
        return [x for x in (_limpo(i, prof + 1) for i in v[:40]) if x is not None]
    if prof < 4 and isinstance(v, dict):
        return {str(k)[:30]: x for k, x in ((k, _limpo(i, prof + 1)) for k, i in list(v.items())[:20]) if x is not None}
    return None


EXTRAS = {"mapa": ("plaquinhas", "faixa", "etiqueta"), "maquete": ("folha_receita", "destaques", "saldo", "gastou", "arrecadou"), "barras": ("barras",)}


def validar_cenas(lista, maximo=6):
    """Lista de cenas (de IA ou de um par) -> cenas limpas, com so as pecas que o estudio tem. inicio/fim, se vierem em segundos validos, sao mantidos."""
    cenas = []
    for c in (lista or [])[:maximo]:
        if not isinstance(c, dict):
            continue
        if c.get("peca") == "fim_selo":     # fecho do padrao Parceiro: visao geral da mesa com TODAS as casinhas do ultimo ano (+ selo grande nos ultimos 3,5 s)
            maqs = [x for x in cenas if x["peca"] == "maquete"]
            if maqs and all(isinstance(c.get(k), (int, float)) for k in ("inicio", "fim")) and c["fim"] > c["inicio"]:
                ult = maqs[-1]["dados"]
                todos = {}
                for x in maqs:
                    if x["dados"].get("ano") == ult.get("ano"):
                        for s in x["dados"]["setores"]:
                            todos[s["nome"]] = {**s, "t": 0.0}
                cenas.append({"titulo": "", "peca": "maquete", "dados": {**{k: v for k, v in ult.items() if k in ("ano", "cor", "pilha_mi")}, "setores": list(todos.values())[:12], "visao_geral": True},
                              "inicio": float(c["inicio"]), "fim": float(c["fim"])})
            elif cenas and isinstance(c.get("fim"), (int, float)) and "fim" in cenas[-1] and c["fim"] > cenas[-1]["fim"]:
                cenas[-1]["fim"] = float(c["fim"])
            continue
        peca = c.get("peca") if c.get("peca") in PECAS else "barras"
        d = c.get("dados") if isinstance(c.get("dados"), dict) else {}
        if peca == "barras":
            v = [float(x) for x in (d.get("valores") or []) if isinstance(x, (int, float))][:6]
            cores = [x for x in (d.get("cores") or []) if isinstance(x, str) and re.fullmatch(r"(?:dourado|verde|rosa)(?: claro)?|azul|prata|vermelho|#[0-9a-fA-F]{6}", x)][:6]
            d = {"valores": v if len(v) >= 2 else [1, 2, 3, 4], **({"rotulos": [str(x)[:60] for x in d["rotulos"]][:6]} if isinstance(d.get("rotulos"), list) else {}),
                 **({"cores": cores} if cores else {}), **({"titulo": str(d["titulo"])[:60]} if d.get("titulo") else {})}
        elif peca == "pilha":
            d = {"itens": int(d.get("itens")) if isinstance(d.get("itens"), (int, float)) else 6}
        elif peca == "mapa":
            uf, mun = str(d.get("uf") or "").strip().upper(), str(d.get("municipio") or "").strip()[:60]
            if not re.fullmatch(r"[A-Z]{2}", uf) or not mun:
                raise ValueError("cena mapa precisa de dados.uf (2 letras) e dados.municipio")
            pinos = [{"nome": str(p.get("nome", ""))[:30], "lat": float(p["lat"]), "lon": float(p["lon"])} for p in (d.get("pinos") or [])[:8]
                     if isinstance(p, dict) and isinstance(p.get("lat"), (int, float)) and isinstance(p.get("lon"), (int, float)) and -90 <= p["lat"] <= 90 and -180 <= p["lon"] <= 180]
            d = {"uf": uf, "municipio": mun, **({"zoom_final": "estado"} if d.get("zoom_final") == "estado" else {}), **({"pinos": pinos} if pinos else {})}
        elif peca == "numero":
            v = d.get("valor")
            if not (isinstance(v, (int, float)) and not isinstance(v, bool)) and not (isinstance(v, str) and 0 < len(v) <= 30):
                raise ValueError("cena numero precisa de dados.valor (numero ou texto curto)")
            d = {"valor": v, **{k: str(d[k])[:60] for k in ("prefixo", "sufixo", "rotulo", "detalhe") if d.get(k)}}
            if isinstance(c.get("dados", {}).get("casas"), int) and 0 <= c["dados"]["casas"] <= 3:
                d["casas"] = c["dados"]["casas"]
        elif peca == "moedas":
            ps = []
            for p in (d.get("pilhas") or [])[:5]:
                if not isinstance(p, dict):
                    continue
                q = {"ano": str(p.get("ano") or "")[:8], "rotulo": str(p.get("rotulo") or "")[:24]}
                if isinstance(p.get("valor"), (int, float)) and not isinstance(p["valor"], bool) and p["valor"] > 0:
                    q["valor"] = float(p["valor"])
                if isinstance(p.get("itens"), int) and 1 <= p["itens"] <= 40:
                    q["itens"] = p["itens"]
                if isinstance(p.get("cor"), str) and re.fullmatch(r"dourado|verde|rosa|azul|prata|vermelho|#[0-9a-fA-F]{6}", p["cor"]):
                    q["cor"] = p["cor"]
                ps.append(q)
            if not ps:
                raise ValueError("cena moedas precisa de dados.pilhas (ate 5, com ano e valor/itens)")
            d = {"pilhas": ps}
        elif peca == "maquete":
            ss = []
            for q in (d.get("setores") or [])[:12]:
                if not isinstance(q, dict) or not str(q.get("nome") or "").strip():
                    continue
                it = {"nome": str(q["nome"])[:30], "rotulo": str(q.get("rotulo") or "")[:24]}
                if isinstance(q.get("valor"), (int, float)) and not isinstance(q["valor"], bool) and q["valor"] >= 0:
                    it["valor"] = float(q["valor"])
                if q.get("tipo") in ("escola", "hospital", "predio", "rua", "campo", "casa"):
                    it["tipo"] = q["tipo"]
                if q.get("zerado") is True:
                    it["zerado"] = True
                if isinstance(q.get("t"), (int, float)) and not isinstance(q["t"], bool) and 0 <= q["t"] < 600:
                    it["t"] = float(q["t"])
                ant = [{"ano": str(a.get("ano") or "")[:8], "rotulo": str(a.get("rotulo") or "")[:24], **({"cor": a["cor"]} if isinstance(a.get("cor"), str) and re.fullmatch(r"dourado|verde|rosa|azul|prata|vermelho|#[0-9a-fA-F]{6}", a["cor"]) else {})}
                       for a in (q.get("anteriores") or [])[:2] if isinstance(a, dict)]
                if ant:
                    it["anteriores"] = ant
                if isinstance(q.get("folha"), dict):
                    it["folha"] = _limpo(q["folha"])
                ss.append(it)
            if not ss:
                raise ValueError("cena maquete precisa de dados.setores (ate 12, com nome e valor)")
            nd = {"setores": ss, "ano": str(d.get("ano") or "")[:8]}
            if isinstance(d.get("cor"), str) and re.fullmatch(r"dourado|verde|rosa|azul|prata|vermelho|#[0-9a-fA-F]{6}", d["cor"]):
                nd["cor"] = d["cor"]
            if isinstance(d.get("pilha_mi"), (int, float)) and not isinstance(d["pilha_mi"], bool) and d["pilha_mi"] > 0:
                nd["pilha_mi"] = float(d["pilha_mi"])
            if d.get("titulo"):
                nd["titulo"] = str(d["titulo"])[:60]
            d = nd
        elif peca == "linha":
            v = [float(x) for x in (d.get("valores") or []) if isinstance(x, (int, float)) and not isinstance(x, bool)][:48]
            if len(v) < 2:
                raise ValueError("cena linha precisa de dados.valores com 2 ou mais numeros")
            nd = {"valores": v}
            if isinstance(d.get("rotulos"), list):
                nd["rotulos"] = [str(x)[:12] for x in d["rotulos"]][:48]
            for k in ("rotulo", "prefixo", "sufixo"):
                if d.get(k):
                    nd[k] = str(d[k])[:60]
            if isinstance(d.get("casas"), int) and 0 <= d["casas"] <= 3:
                nd["casas"] = d["casas"]
            if isinstance(d.get("final"), (int, float)) and not isinstance(d["final"], bool):
                nd["final"] = float(d["final"])
            d = nd
        else:
            d = {}
        orig = c.get("dados") if isinstance(c.get("dados"), dict) else {}
        for k in EXTRAS.get(peca, ()):
            if k in orig and _limpo(orig[k]) is not None:
                d[k] = _limpo(orig[k])
        cena = {"titulo": str(c.get("titulo") or "")[:40], "peca": peca, "dados": d}
        if all(isinstance(c.get(k), (int, float)) and 0 <= c[k] < 3600 for k in ("inicio", "fim")) and c["fim"] > c["inicio"]:
            cena["inicio"], cena["fim"] = float(c["inicio"]), float(c["fim"])
        cenas.append(cena)
    if len(cenas) < 2:
        raise ValueError("poucas cenas")
    return cenas


def ajustar_cenas(cenas, falas):
    """Reparte as cenas igualmente na duracao da fala, encostando cada corte no inicio da legenda mais proxima."""
    fim = max([f["fim"] for f in falas] + [3.0])
    inicios = [f["inicio"] for f in falas]
    n = len(cenas)
    cortes = [0.0]
    for i in range(1, n):
        alvo = fim * i / n
        cortes.append(min(inicios, key=lambda t: abs(t - alvo)) if inicios else alvo)
    cortes.append(fim + 0.5)
    for i, c in enumerate(cenas):
        c["inicio"], c["fim"] = round(cortes[i], 2), round(max(cortes[i + 1], cortes[i] + 1.0), 2)
    return cenas


def _py(*args, timeout=900):
    env = dict(os.environ, BRANIAC_RAIZ=str(Path(__file__).resolve().parent.parent), PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable.replace("pythonw.exe", "python.exe"), *args], cwd=str(PASTA), capture_output=True, text=True, timeout=timeout,
                          env=env, creationflags=0x08000000 if os.name == "nt" else 0)


ARQ_ATIVIDADE = DATA / "empresa_cortes" / "estudio.json"


def _etapa(agente, texto):
    """Mostra no andar de video (Claquete) o que o estudio esta fazendo: atualiza o arquivo de atividade e posta no barramento. Nunca derruba o video."""
    try:
        ARQ_ATIVIDADE.parent.mkdir(parents=True, exist_ok=True)
        ARQ_ATIVIDADE.write_text(json.dumps({"agente": agente, "texto": texto, "ts": time.time()}, ensure_ascii=False), encoding="utf-8")
        from . import barramento
        barramento.enviar(agente, "Jarvis", "status", texto)
    except Exception:
        pass


def produzir(titulo, narracao, cenas):
    """Cria o projeto, narra, sincroniza, ajusta cenas e renderiza. Devolve o caminho do video (ou levanta RuntimeError)."""
    _etapa("Pena", f"roteiro pronto: «{titulo[:50]}» ({len(cenas)} cenas)")
    nome = f"{proximo_numero()}-{slug(titulo)}"
    pj = PASTA / "projetos" / nome
    pj.mkdir(parents=True, exist_ok=True)
    (pj / "narracao.txt").write_text(narracao + "\n", encoding="utf-8")
    (pj / "fontes.md").write_text("Rascunho gerado pelo Jarvis (IA gratis), conceitos gerais; sem fonte primaria. Conferir antes de publicar.\n", encoding="utf-8")
    roteiro_arq = pj / "roteiro.json"
    roteiro_arq.write_text(json.dumps({"titulo": titulo, "estilo": "padrao", "legenda": [], "cenas": [dict(c, inicio=0, fim=3) for c in cenas]}, ensure_ascii=False, indent=2), encoding="utf-8")
    for etapa in (("tools/narrar.py", nome), ("tools/transcrever.py", nome)):
        _etapa("Eco", "gerando a narração" if "narrar" in etapa[0] else "sincronizando a legenda com o Whisper")
        r = _py(*etapa)
        if r.returncode:
            raise RuntimeError(f"{etapa[0]} falhou: {(r.stderr or r.stdout)[-200:]}")
    ro = json.loads(roteiro_arq.read_text(encoding="utf-8"))
    ro["cenas"] = ajustar_cenas(ro["cenas"], ro["legenda"])
    roteiro_arq.write_text(json.dumps(ro, ensure_ascii=False, indent=2), encoding="utf-8")
    _etapa("Prisma", f"renderizando {len(cenas)} cenas 3D em vídeo vertical")
    saida, motor = renderizar(nome, timeout=1500)
    _etapa("Prisma", f"vídeo pronto: {nome} ({motor})")
    return str(saida)


# motor-rs (13/11/2026): motor proprio em Rust, ~5x mais rapido, mesmo roteiro.json. Ele so aceita o roteiro se fizer TODAS as
# pecas (--estrito, codigo 3); recusou ou falhou, o Remotion faz como sempre. ESTUDIO_MOTOR=remotion desliga o motor-rs.
MOTOR_RS = PASTA / "motor-rs" / "target" / "release" / ("motor-rs.exe" if os.name == "nt" else "motor-rs")
_SEM_JANELA = 0x08000000 if os.name == "nt" else 0


def _motor_rs(args, timeout):
    if os.environ.get("ESTUDIO_MOTOR") == "remotion" or not MOTOR_RS.is_file():
        return None
    try:
        return subprocess.run([str(MOTOR_RS), *args, "--estrito"], cwd=str(PASTA), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, creationflags=_SEM_JANELA)
    except (OSError, subprocess.TimeoutExpired) as e:
        return subprocess.CompletedProcess(args, 1, "", str(e))


def renderizar(nome, timeout=7200):
    """edicoes/<nome>/video.mp4 pelo motor-rs; se ele recusar ou falhar, pelo Remotion. Devolve (caminho, motor)."""
    saida = PASTA / "edicoes" / nome / "video.mp4"
    r = _motor_rs([nome, f"--saida={saida}"], timeout)
    if r is not None:
        if r.returncode == 0 and saida.is_file():
            return saida, "motor-rs"
        _etapa("Prisma", "motor-rs não fez este vídeo (" + (r.stderr or r.stdout).strip()[-120:] + "); seguindo no Remotion")
    n = subprocess.run(["node", "scripts/render.mjs", nome], cwd=str(PASTA), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, creationflags=_SEM_JANELA)
    if n.returncode or not saida.is_file():
        raise RuntimeError("render falhou: " + (n.stderr or n.stdout)[-200:])
    return saida, "remotion"


def quadro(nome, segundo):
    """Um quadro avulso (PNG) para conferir: motor-rs (instantaneo) ou Remotion. Devolve o caminho."""
    s = f"{segundo:g}"
    r = _motor_rs([nome, f"--quadro={s}"], 120)
    q = PASTA / "edicoes" / nome / f"quadro-rs-{s}.png"
    if r is not None and r.returncode == 0 and q.is_file():
        return q
    subprocess.run(["node", "scripts/render.mjs", "--quadro", nome, f"--segundo={s}"], cwd=str(PASTA), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600, creationflags=_SEM_JANELA)
    return PASTA / "edicoes" / nome / f"quadro-{s}.png"


def _avisar(texto):
    try:
        with OUTBOX.open("a", encoding="utf-8") as f:
            f.write("\n---\n" + texto)
    except OSError:
        pass


def criar(tema, router, produzir_fn=None, avisar_fn=None):
    """Inicia o video em segundo plano. Devolve a resposta imediata ao Dono."""
    tema = (tema or "").strip()
    if len(tema) < 8:
        return "Qual o tema do vídeo? Me passa uma frase."
    if SEGREDO.search(tema):
        return "Tema recusado: tem palavra de segredo/dado pessoal."
    if SENSIVEL.search(tema):
        return "Esse tema (política, saúde ou finanças) precisa de fonte primária. Peça pela skill estudio-3d com o Claude, que pesquisa e cita as fontes."
    if not PASTA.exists():
        return f"Não achei o Estúdio 3D em {PASTA}."
    uso = _usos_hoje()
    if uso["n"] >= MAX_DIA:
        return f"Já fiz {MAX_DIA} vídeos hoje (teto do dia)."
    if not _trava.acquire(blocking=False):
        return "Já estou fazendo um vídeo; um por vez."
    uso["n"] += 1
    ARQ_USO.write_text(json.dumps(uso), encoding="utf-8")
    avisar_fn = avisar_fn or _avisar
    produzir_fn = produzir_fn or produzir

    def rodar():
        try:
            resp = router.responder_neutro(PROMPT, f"Tema: {tema}")
            texto = resp[0] if isinstance(resp, tuple) else resp
            dados = json.loads(re.search(r"\{.*\}", texto, re.S).group(0), strict=False)
            titulo, narr, cenas = validar(dados)
            caminho = produzir_fn(titulo, narr, cenas)
            avisar_fn(f"O vídeo «{titulo}» ficou pronto (rascunho, conferir antes de publicar): {caminho}")
        except Exception as e:
            avisar_fn(f"Não consegui fazer o vídeo sobre «{tema[:50]}»: {str(e)[:150]}")
        finally:
            _trava.release()

    threading.Thread(target=rodar, daemon=True, name="estudio3d").start()
    return f"Começando o vídeo sobre «{tema[:60]}». Leva alguns minutos; te aviso quando estiver pronto."
