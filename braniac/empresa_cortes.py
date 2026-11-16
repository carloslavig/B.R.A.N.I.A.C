# -*- coding: utf-8 -*-
"""LINHA DE CORTES DE VÍDEO "Claquete" (03/11/2026, pedido do Dono): 5o andar do Braniac, separado da Fornalha (que fica só com marketing de clientes).
Fluxo por PEDIDO: novo -> transcrito (Mina, Whisper local) -> cortado (Mina escolhe o trecho) -> montado (Tesoura, 9:16: fala em cima, gameplay embaixo)
-> legendado (Rótulo, SRT queimado + crédito da fonte) -> revisado (Lupa) -> aguardando_ok. Quem publica é o time da Fornalha (Pasta), pela regra de ritmo
guardada em equipe.json; aqui só se agenda depois do OK do Dono.
TRAVAS: nada é publicado sem aprovar() (OK do Dono) e aprovar() exige `direitos_ok` e `gameplay_ok` em equipe.json (decisão dele, ainda em aberto);
trecho curto com a fonte citada; sem segredo no pedido; tetos por dia próprios (passos_dia, pedidos_dia). A rotina antiga da Twitch (braniac/cortes) fica pausada."""
import json
import re
import subprocess
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from .store import DATA

PASTA = DATA / "empresa_cortes"
SAIDA = PASTA / "saida"
EQUIPE_JSON = PASTA / "equipe.json"
PEDIDOS_JSON = PASTA / "pedidos.json"
FILA_JSON = PASTA / "fila_publicacao.json"
_lock = threading.RLock()
SEGREDO = re.compile(r"(?i)\bsenha\b|\bcvv\b|\bcpf\b|api[_ -]?key|secret|\btoken\b|cart[aã]o|\bpix\b")
SEM_JANELA = 0x08000000   # CREATE_NO_WINDOW
PASSOS = ("novo", "transcrito", "cortado", "montado", "legendado", "revisado")


def _ler(p, padrao):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return padrao


def _gravar(p, dado):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(dado, ensure_ascii=False, indent=1), encoding="utf-8")
    for _ in range(10):      # Windows: leitor segura o arquivo por instantes
        try:
            tmp.replace(p)
            return
        except PermissionError:
            time.sleep(0.5)
    p.write_text(tmp.read_text(encoding="utf-8"), encoding="utf-8")


def config():
    return _ler(EQUIPE_JSON, {"empresa": "Claquete", "agentes": [], "limites": {}})


# 11/11/2026: o Estudio 3D (video explicativo ilustrado, braniac/estudio3d.py) mora no andar de video. Sempre presentes, mesmo em instalacao nova.
AGENTES_ESTUDIO = [
    {"nome": "Pena", "papel": "Roteiro do estúdio 3D", "sala": "Estúdio",
     "instrucao": "Você é a Pena: escreve a narração curta e as cenas do vídeo explicativo. Só conceitos conhecidos; nunca inventa número, data ou fonte."},
    {"nome": "Eco", "papel": "Voz e sincronia", "sala": "Estúdio",
     "instrucao": "Você é o Eco: gera a narração com a voz do Braniac e sincroniza a legenda com o Whisper local."},
    {"nome": "Prisma", "papel": "Cenas 3D e render", "sala": "Estúdio",
     "instrucao": "Você é o Prisma: monta as cenas 3D (barras, globo, pilha) nos tempos da fala e renderiza o vídeo vertical 1080x1920."},
]


def agentes():
    base = config().get("agentes", [])
    tem = {a["nome"] for a in base}
    return base + [a for a in AGENTES_ESTUDIO if a["nome"] not in tem]


def nomes():
    return [a["nome"] for a in agentes()]


def limite(chave, padrao):
    try:
        return max(0, int(config().get("limites", {}).get(chave, padrao)))
    except (TypeError, ValueError):
        return padrao


def _hoje():
    return datetime.now().strftime("%Y-%m-%d")


def _uso(chave, somar=False):
    d = _ler(PASTA / "uso.json", {})
    v = d.get(_hoje(), {})
    if somar:
        v[chave] = v.get(chave, 0) + 1
        _gravar(PASTA / "uso.json", {_hoje(): v})
    return v.get(chave, 0)


def _pedidos():
    return _ler(PEDIDOS_JSON, [])


def _salvar(ps, p, texto=None):
    if texto:
        p.setdefault("historico", []).append({"ts": time.time(), "texto": texto[:300]})
    _gravar(PEDIDOS_JSON, ps)


# ---------- ferramentas (testes trocam por falsas) ----------
def _ia(sistema, prompt):
    from .empresa_mkt import _ia as ia
    return ia(sistema, prompt)


def _segmentos(video):
    """Whisper local com tempos: [{ini, fim, texto}]."""
    from . import voz
    with voz._lock:
        if voz._whisper is None:
            voz._whisper = voz._carregar_whisper()
        segs, _ = voz._whisper.transcribe(str(video), language="pt", vad_filter=True, beam_size=1, condition_on_previous_text=False)
        return [{"ini": round(s.start, 2), "fim": round(s.end, 2), "texto": s.text.strip()} for s in segs if s.text.strip()]


def _ffmpeg(args, cwd):
    r = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], cwd=str(cwd), capture_output=True, text=True, creationflags=SEM_JANELA, timeout=900)
    if r.returncode:
        raise RuntimeError("ffmpeg: " + r.stderr[-300:])


def _sonda(arq):
    """{duracao, largura, altura, audio, volume_db} de um vídeo."""
    r = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(arq)], capture_output=True, text=True, creationflags=SEM_JANELA, timeout=60)
    d = json.loads(r.stdout or "{}")
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), {})
    a = any(s.get("codec_type") == "audio" for s in d.get("streams", []))
    vol = None
    if a:
        m = subprocess.run(["ffmpeg", "-i", str(arq), "-af", "volumedetect", "-vn", "-f", "null", "-"], capture_output=True, text=True, creationflags=SEM_JANELA, timeout=300)
        g = re.search(r"mean_volume: (-?[\d.]+) dB", m.stderr)
        vol = float(g.group(1)) if g else None
    return {"duracao": float(d.get("format", {}).get("duration", 0) or 0), "largura": v.get("width"), "altura": v.get("height"), "audio": a, "volume_db": vol}


def _baixar(url, destino):
    """yt-dlp (só se a fonte for URL). Falha clara se não estiver instalado."""
    r = subprocess.run(["yt-dlp", "-f", "bv*[height<=720]+ba/b[height<=720]", "--merge-output-format", "mp4", "-o", str(destino), url], capture_output=True, text=True, creationflags=SEM_JANELA, timeout=1800)
    if r.returncode or not Path(destino).exists():
        raise RuntimeError("yt-dlp: " + (r.stderr or "falhou")[-200:])
    return str(destino)


def _montar_fn(fala, gameplay, ini, dur, destino):
    """9:16 (1080x1920): fala em cima, gameplay embaixo, áudio da fala. ffmpeg direto (headless); o FilmCraft fica para acabamento manual."""
    f = "scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960"
    _ffmpeg(["-ss", str(ini), "-t", str(dur), "-i", str(fala), "-stream_loop", "-1", "-t", str(dur), "-i", str(gameplay),
             "-filter_complex", f"[0:v]{f}[a];[1:v]{f}[b];[a][b]vstack=inputs=2[v]", "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-preset", "veryfast",
             "-crf", "23", "-c:a", "aac", "-shortest", Path(destino).name], Path(destino).parent)


def _queimar_fn(base, srt, destino):
    est = "FontSize=9,Alignment=2,MarginV=150,Outline=2,Bold=1"   # SRT usa tela virtual de 288 px de altura
    _ffmpeg(["-i", Path(base).name, "-vf", f"subtitles={Path(srt).name}:force_style='{est}'", "-c:a", "copy", Path(destino).name], Path(destino).parent)


# ---------- pedido ----------
def abrir(fonte, autor, titulo_fonte="", gameplay="", prova=False):
    """fonte = caminho local ou URL do vídeo longo; autor/título são citados na legenda. gameplay = vídeo de fundo (precisa ser local)."""
    if SEGREDO.search(f"{fonte} {autor} {titulo_fonte}"):
        return None, "Pedido recusado: tem palavra de segredo/dado pessoal."
    if not autor.strip():
        return None, "Sem autor não abro: o corte sempre cita a fonte."
    gameplay = gameplay or config().get("gameplay_padrao", "")
    if not gameplay or not Path(gameplay).exists():
        return None, "Falta o vídeo de gameplay (arquivo local). Origem e permissão ainda estão em aberto com o Dono."
    if not (fonte.startswith(("http://", "https://")) or Path(fonte).exists()):
        return None, "Fonte não encontrada (passe um arquivo local ou URL)."
    if _uso("pedidos") >= limite("pedidos_dia", 3):
        return None, "Teto de pedidos de hoje atingido."
    with _lock:
        ps = _pedidos()
        p = {"id": f"V{len(ps) + 1:03d}", "fonte": fonte, "autor": autor.strip()[:80], "titulo_fonte": titulo_fonte[:120], "gameplay": gameplay, "prova": bool(prova),
             "estado": "novo", "historico": [], "criado": time.time()}
        ps.append(p)
        _salvar(ps, p, "pedido aberto")
        _uso("pedidos", True)
    return p, f"{p['id']} aberto (fonte: {autor})."


def _srt(segs, ini, fim, credito):
    def t(x):
        h, r = divmod(max(x, 0), 3600)
        m, s = divmod(r, 60)
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(round((s % 1) * 1000)):03d}"
    linhas, n = [], 0
    for s in segs:
        if s["fim"] <= ini or s["ini"] >= fim:
            continue
        n += 1
        linhas.append(f"{n}\n{t(max(s['ini'], ini) - ini)} --> {t(min(s['fim'], fim) - ini)}\n{s['texto']}\n")
    dur = fim - ini
    linhas.append(f"{n + 1}\n{t(max(dur - 3, 0))} --> {t(dur)}\n{credito}\n")
    return "\n".join(linhas)


def _escolher(segs):
    """Mina: a IA aponta o trecho; sem IA válida, a janela mais densa em palavras dentro dos limites."""
    lo, hi = limite("duracao_min_s", 20), limite("duracao_max_s", 45)
    texto = "\n".join(f"{i}|{s['ini']}-{s['fim']}|{s['texto']}" for i, s in enumerate(segs))[:6000]
    try:
        r = _ia("Você escolhe o trecho mais marcante e autossuficiente de uma fala para um corte vertical curto. Responda só JSON: {\"ini\": segundos, \"fim\": segundos}.",
                f"Duração entre {lo} e {hi} segundos. Segmentos (índice|início-fim|texto):\n{texto}")
        d = json.loads(re.search(r"\{.*\}", r, re.S).group(0))
        ini, fim = float(d["ini"]), float(d["fim"])
        if lo <= fim - ini <= hi and any(s["ini"] <= ini < s["fim"] + 1 for s in segs):
            return ini, fim
    except Exception:
        pass
    melhor = None
    for i, a in enumerate(segs):
        fim, pal = a["ini"], 0
        for b in segs[i:]:
            if b["fim"] - a["ini"] > hi:
                break
            fim, pal = b["fim"], pal + len(b["texto"].split())
        if fim - a["ini"] >= lo and (melhor is None or pal > melhor[0]):
            melhor = (pal, a["ini"], fim)
    return (melhor[1], melhor[2]) if melhor else None


EVITAR_PADRAO = ["resposta", "reação", "reacao", "react", "destrói", "destroi", "humilha", "cortes", "melhores momentos",
                 "perdeu a paciência", "perdeu a paciencia", "perde a paciência", "briga", "bate-boca", "bate boca", "discute", "detona", "desmonta", "expõe", "expoe", " vs ", "versus"]


def buscar_fontes(qtd=3):
    """Filtro de busca: vídeos longos em que o Streamer Manoel aparece (lives, podcasts, entrevistas) no YouTube, ainda não usados.
    Fora: respostas/reações de adversários (edição hostil), vídeos curtos demais ou longos demais para o Whisper local."""
    c = config()
    busca = c.get("busca", {})
    usados = {p["fonte"] for p in _pedidos()} | set(_ler(PASTA / "fontes_vistas.json", []))
    achados = []
    for q in busca.get("consultas", ["Streamer Manoel entrevista", "Streamer Manoel podcast", "Streamer Manoel live", "Streamer Manoel debate"]):
        for linha in _buscar_fn(q):
            vid, titulo, dur, canal = (linha.split("|") + ["", "", "", ""])[:4]
            url = f"https://www.youtube.com/watch?v={vid}"
            try:
                dur = float(dur)
            except ValueError:
                continue
            ruim = any(w in titulo.lower() for w in busca.get("evitar", EVITAR_PADRAO))
            # 11/11: o V003 veio do canal Mamae Falei (briga editada, nao a voz dele). Agora o CANAL tem de ser o do proprio Streamer ou um canal aprovado pelo Dono em busca.canais_ok.
            canal_ok = "streamer manoel" in canal.lower() or any(c.lower() in canal.lower() for c in busca.get("canais_ok", []))
            if (not ruim and canal_ok and url not in usados and "streamer manoel" in f"{titulo} {canal}".lower()
                    and busca.get("min_s", 600) <= dur <= busca.get("max_s", 14400) and url not in [a[0] for a in achados]):
                achados.append((url, titulo, canal, dur))
    return achados[:qtd]


def _buscar_fn(consulta):
    r = subprocess.run(["yt-dlp", "--flat-playlist", "--print", "%(id)s|%(title)s|%(duration)s|%(channel)s", f"ytsearch10:{consulta}"],
                       capture_output=True, text=True, creationflags=SEM_JANELA, timeout=120)
    return [x for x in r.stdout.splitlines() if x.count("|") >= 3]


def abrir_da_busca():
    """Abre o próximo pedido com a melhor fonte nova (a de duração mais curta, que o Whisper local processa antes)."""
    fontes = sorted(buscar_fontes(5), key=lambda a: a[3])
    if not fontes:
        return None, "Nenhuma fonte nova na busca."
    url, titulo, canal, _ = fontes[0]
    vistas = _ler(PASTA / "fontes_vistas.json", [])
    _gravar(PASTA / "fontes_vistas.json", vistas + [url])
    return abrir(url, "Streamer Manoel", f"{titulo} ({canal})")


def _passo(ps, p):
    """Avança um pedido um estado. Devolve o texto do que aconteceu."""
    pasta = SAIDA / p["id"]
    pasta.mkdir(parents=True, exist_ok=True)
    e = p["estado"]
    if e == "novo":
        fala = p["fonte"]
        if fala.startswith("http"):
            fala = _baixar(fala, pasta / "fonte.mp4")
        p["fala"] = fala
        p["segmentos"] = _segmentos(fala)
        if not p["segmentos"]:
            raise RuntimeError("sem fala reconhecida na fonte")
        p["estado"] = "transcrito"
    elif e == "transcrito":
        t = _escolher(p["segmentos"])
        if not t:
            raise RuntimeError("nenhum trecho dentro dos limites de duração")
        p["trecho"] = {"ini": t[0], "fim": t[1], "texto": " ".join(s["texto"] for s in p["segmentos"] if t[0] <= s["ini"] < t[1])[:400]}
        p["estado"] = "cortado"
    elif e == "cortado":
        t = p["trecho"]
        _montar_fn(p["fala"], p["gameplay"], t["ini"], round(t["fim"] - t["ini"], 2), pasta / "base.mp4")
        p["arquivo"] = str(pasta / "base.mp4")
        p["estado"] = "montado"
    elif e == "montado":
        t = p["trecho"]
        cred = f"Fonte: {p['autor']}" + (f" - {p['titulo_fonte']}" if p["titulo_fonte"] else "")
        (pasta / "leg.srt").write_text(_srt(p["segmentos"], t["ini"], t["fim"], cred), encoding="utf-8")
        _queimar_fn(pasta / "base.mp4", pasta / "leg.srt", pasta / "final.mp4")
        p["arquivo"], p["estado"] = str(pasta / "final.mp4"), "legendado"
    elif e == "legendado":
        s = _sonda(p["arquivo"])
        erros = []
        if not (limite("duracao_min_s", 20) - 1 <= s["duracao"] <= limite("duracao_max_s", 45) + 1):
            erros.append(f"duração {s['duracao']:.0f}s fora do limite")
        if (s["largura"], s["altura"]) != (1080, 1920):
            erros.append(f"formato {s['largura']}x{s['altura']} (esperado 1080x1920)")
        if not s["audio"] or (s["volume_db"] is not None and s["volume_db"] < -50):
            erros.append("sem áudio audível")
        if erros:
            p["estado"] = "reprovado"
            return f"{p['id']} reprovado pela Lupa: " + "; ".join(erros)
        p["estado"] = "revisado"
    elif e == "revisado":
        p["estado"] = "aguardando_ok"
        return f"{p['id']} pronto em {p['arquivo']}, aguardando o OK do Dono (confira se a voz é de {p['autor']})."
    return f"{p['id']} → {p['estado']}"


def trabalhar(n=1, ignorar_teto=False):
    feitos = []
    with _lock:
        ps = _pedidos()
        for p in ps:
            if len(feitos) >= n:
                break
            if p["estado"] not in PASSOS:
                continue
            if not ignorar_teto and _uso("passos") >= limite("passos_dia", 12):
                feitos.append("Teto de passos de hoje atingido.")
                break
            try:
                txt = _passo(ps, p)
            except Exception as ex:
                p["estado"] = "falhou"
                txt = f"{p['id']} erro: {str(ex)[:160]}"
            _uso("passos", True)
            _salvar(ps, p, txt)
            feitos.append(txt)
    return feitos


def aprovar(id_):
    """OK do Dono: agenda TikTok (manhã/noite, 2 por dia) e deixa uma cópia na pasta do Kwai. YouTube só quando o conselho propuser o ritmo e o Dono aprovar."""
    cfg = config()
    if not (cfg.get("direitos_ok") and cfg.get("gameplay_ok")):
        return "Ainda não: faltam o OK dos direitos dos trechos e a origem/permissão da gameplay (equipe.json: direitos_ok, gameplay_ok)."
    with _lock:
        ps = _pedidos()
        p = next((x for x in ps if x["id"] == id_.upper()), None)
        if not p or p["estado"] != "aguardando_ok":
            return "Pedido não encontrado ou não está aguardando OK."
        if not p.get("locutor_ok"):
            return f"{p['id']}: confirme antes que a fala é mesmo de {p['autor']} (o Whisper não identifica quem fala; debates têm outras pessoas). Use confirmar_locutor."
        fila = _ler(FILA_JSON, [])
        horarios = cfg.get("tiktok_horarios", ["09:00", "20:00"])
        ocupados = {f["quando"] for f in fila if f["plataforma"] == "tiktok"}
        dia = datetime.now()
        quando = None
        while not quando:
            for h in horarios:
                c = f"{dia:%Y-%m-%d} {h}"
                if c not in ocupados and c > f"{datetime.now():%Y-%m-%d %H:%M}":
                    quando = c
                    break
            dia += timedelta(days=1)
        fila.append({"id": p["id"], "plataforma": "tiktok", "quando": quando, "arquivo": p["arquivo"], "estado": "agendado"})
        if cfg.get("youtube_ritmo"):
            fila.append({"id": p["id"], "plataforma": "youtube", "quando": None, "arquivo": p["arquivo"], "estado": "ritmo " + str(cfg["youtube_ritmo"])})
        (SAIDA / "kwai").mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy(p["arquivo"], SAIDA / "kwai" / f"{p['id']}.mp4")
        p["estado"] = "aprovado"
        _gravar(FILA_JSON, fila)
        _salvar(ps, p, "aprovado pelo Dono; TikTok " + quando)
    return f"{p['id']} aprovado: TikTok em {quando}; cópia na pasta do Kwai (você sobe). YouTube: {'agendado pelo ritmo' if cfg.get('youtube_ritmo') else 'espera o ritmo do conselho'}."


def confirmar_locutor(id_):
    """O Dono assistiu ao corte e confirma que a voz é do autor citado."""
    with _lock:
        ps = _pedidos()
        p = next((x for x in ps if x["id"] == id_.upper()), None)
        if not p:
            return "Pedido não encontrado."
        p["locutor_ok"] = True
        _salvar(ps, p, "locutor confirmado pelo Dono")
    return f"{p['id']}: locutor confirmado."


def rejeitar(id_):
    with _lock:
        ps = _pedidos()
        p = next((x for x in ps if x["id"] == id_.upper() and x["estado"] in ("aguardando_ok", "reprovado", "falhou")), None)
        if not p:
            return "Pedido não encontrado."
        p["estado"] = "rejeitado"
        _salvar(ps, p, "rejeitado")
    return f"{p['id']} rejeitado."


def _enviar_tiktok(arquivo, legenda):
    """Sobe o vídeo pelo Chrome do Braniac (porta 9222, já logado). Devolve '' se publicou, ou o motivo do erro."""
    import time
    from braniac import ia_web
    with ia_web._Aba({"dominio": "tiktok.com/tiktokstudio/upload", "url": "https://www.tiktok.com/tiktokstudio/upload", "fechar": True}) as a:
        a.cmd("Page.bringToFront")
        a.cmd("DOM.enable")
        for _ in range(30):
            doc = a.cmd("DOM.getDocument", {"depth": -1})
            n = a.cmd("DOM.querySelector", {"nodeId": doc["root"]["nodeId"], "selector": "input[type=file]"})
            if n.get("nodeId"):
                break
            time.sleep(1.5)
        else:
            return "tela de upload não abriu (sessão caiu?)"
        a.cmd("DOM.setFileInputFiles", {"nodeId": n["nodeId"], "files": [str(arquivo).replace("\\", "/")]})
        for _ in range(60):  # espera o processamento do vídeo
            if a.js("!!document.querySelector('[contenteditable=true]')"):
                break
            time.sleep(2)
        a.js("(function(t){var e=document.querySelector('[contenteditable=true]');e.focus();document.execCommand('selectAll');document.execCommand('insertText',false,t)})(%s)" % json.dumps(legenda))
        for _ in range(60):  # botão só habilita quando o upload termina
            r = a.js("(function(){var b=[...document.querySelectorAll('button')].filter(x=>/^(Publicar|Post)$/.test(x.innerText.trim())&&!x.disabled).pop();if(b){b.click();return 'ok'}return ''})()")
            if r == "ok":
                time.sleep(8)
                return ""
            time.sleep(3)
    return "botão Publicar não habilitou"


def publicar_vencidos(agora=None, enviar=None, subir=None):
    """Publica no TikTok os itens agendados cujo horário chegou (só os já aprovados pelo Dono entram na fila). Um por vez."""
    agora = agora or datetime.now()
    subir = subir or _enviar_tiktok
    with _lock:
        fila = _ler(FILA_JSON, [])
        item = next((f for f in fila if f["plataforma"] == "tiktok" and f["estado"] == "agendado" and f["quando"] <= f"{agora:%Y-%m-%d %H:%M}"), None)
        if not item:
            return None
        p = next((x for x in _pedidos() if x["id"] == item["id"]), {})
        legenda = f"Fonte: {p.get('autor', '')}" + (f" - {p['titulo_fonte']}" if p.get("titulo_fonte") else "") + " #cortes #naooficial"
        item["estado"] = "enviando"  # evita repetir se o envio travar no meio
        _gravar(FILA_JSON, fila)
    try:
        erro = subir(item["arquivo"], legenda[:300])
    except Exception as e:
        erro = str(e)[:120]
    with _lock:
        fila = _ler(FILA_JSON, [])
        for f in fila:
            if f["id"] == item["id"] and f["plataforma"] == "tiktok" and f["estado"] == "enviando":
                f["estado"] = "erro: " + erro if erro else "publicado"
        _gravar(FILA_JSON, fila)
    msg = f"Claquete: {item['id']} " + (f"NÃO subiu no TikTok ({erro})" if erro else "publicado no TikTok")
    if enviar:
        enviar(msg)
    return msg


def tick(agora=None, enviar=None):
    agora = agora or datetime.now()
    if agora.hour < 7 or agora.hour >= 21:
        return []
    if config().get("tiktok_auto"):
        publicar_vencidos(agora, enviar)
    if not any(p["estado"] in PASSOS for p in _pedidos()) and config().get("busca_automatica") and _uso("pedidos") < limite("pedidos_dia", 3):
        p, m = abrir_da_busca()
        if p and enviar:
            enviar("Claquete: nova fonte na fila - " + p["titulo_fonte"][:100])
    feitos = trabalhar(1)
    for f in feitos:
        if enviar and ("aguardando o OK" in f or "erro" in f or "reprovado" in f):
            enviar("Claquete: " + f)
    return feitos


def situacao():
    ps = _pedidos()
    c = config()
    return {"empresa": c.get("empresa"), "agentes": len(agentes()), "pedidos": len(ps), "aguardando_ok": sum(1 for p in ps if p["estado"] == "aguardando_ok"),
            "em_andamento": sum(1 for p in ps if p["estado"] in PASSOS), "liberado": bool(c.get("direitos_ok") and c.get("gameplay_ok"))}


def quadro():
    ps = _pedidos()
    s = situacao()
    cab = f"Claquete: {s['pedidos']} pedido(s), {s['em_andamento']} em andamento, {s['aguardando_ok']} aguardando OK" + ("" if s["liberado"] else " (publicação travada: faltam direitos/gameplay)") + "."
    return "\n".join([cab] + [f"{p['id']} [{p['estado']}] {p['autor']}" for p in ps[-10:]])
