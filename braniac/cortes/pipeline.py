# -*- coding: utf-8 -*-
"""Orquestra um corte do inicio ao fim e a publicacao dos aprovados."""
import os, re, threading, time
from pathlib import Path
import requests
from . import captura, config, deteccao, fila, legenda, render, tiktok, titulos, youtube

_LOTE = threading.Lock()  # um lote pesado (Whisper + NVENC) por vez


def _log(txt):
    linha = time.strftime("%d/%m %H:%M:%S ") + txt
    print(linha, flush=True)
    try:
        with open(config.PASTA / "cortes.log", "a", encoding="utf-8") as f:
            f.write(linha + "\n")
    except OSError:
        pass


def _slug(t):
    return re.sub(r"[^a-z0-9]+", "_", (t or "").lower()).strip("_")[:40] or "corte"


def processar_corte(video, inicio, fim, canal, origem, fonte, score=0.0, motivo="", jogo="", cfg=None, titulo_base=""):
    """Corta [inicio, fim] de `video`, legenda, renderiza 9:16, gera titulo e coloca na fila. Devolve o id."""
    cfg = cfg or config.carregar()
    carimbo = time.strftime("%Y%m%d_%H%M%S")
    tmp = config.sub("tmp") / f"{carimbo}_{int(inicio)}"
    tmp.mkdir(parents=True, exist_ok=True)
    palavras, texto, ass = [], "", None
    if cfg.get("legenda", True):
        try:
            wav = legenda.extrair_wav(video, inicio, fim, tmp / "audio.wav")
            palavras, texto = legenda.transcrever(wav, cfg.get("idioma", "pt"))
            if palavras:
                ass = legenda.gerar_ass(palavras, tmp / "legenda.ass", margem_v=470 if cfg.get("enquadramento") != "centro" else 380)
        except Exception as e:
            _log(f"legenda falhou ({e}); segue sem legenda")
    nome = cfg.get("nome") or canal
    t = titulos.gerar(canal, texto, jogo, cfg.get("ollama_modelo", "qwen2.5:3b"), cfg.get("titulos_ollama", True), titulo_base,
                      cfg.get("idioma", "pt"), nome)
    t["hashtags"] = list(dict.fromkeys(cfg.get("hashtags_fixas", []) + t["hashtags"]))[:8]
    perfil = cfg.get("perfil", "")
    saida = config.sub("saida" + (f"/{perfil}" if perfil else "")) / f"{canal}_{carimbo}_{_slug(t['titulo'])}.mp4"
    render.renderizar(video, inicio, fim, saida, ass, cfg.get("enquadramento", "desfocado"))
    desc = descricao(cfg, canal, nome, t["titulo"], t["hashtags"], fonte)
    id_ = fila.adicionar(canal=canal, origem=origem, fonte=str(fonte), inicio=inicio, fim=fim, score=score, motivo=motivo,
                         arquivo=str(saida), transcricao=texto[:4000], titulo=t["titulo"], descricao=desc, hashtags=" ".join(t["hashtags"]),
                         status="renderizado" if cfg.get("aprovacao_manual", True) else "aprovado", perfil=perfil)
    _log(f"corte #{id_} pronto: {saida.name} ({fim - inicio:.0f}s, {motivo}; whisper {legenda.MOTOR or '-'})")
    return id_


def descricao(cfg, canal, nome, titulo, hashtags, fonte=""):
    """Descricao do video: modelo do perfil (canal gringo: ingles, com credito ao streamer e link do clipe original)."""
    modelo = cfg.get("descricao_modelo")
    if not modelo:
        return f"{titulo}\n\nCorte da live de twitch.tv/{canal}\n\n" + " ".join(hashtags)
    link = f"\U0001F3AC Original clip: {fonte}\n" if str(fonte).startswith("http") else ""
    return modelo.format(titulo=titulo, nome=nome, canal=canal, link_original=link, hashtags=" ".join(hashtags))


def _cfg_canal(canal, cfg):
    return cfg or config.para_canal(config.canal_por_login(canal))


def processar_arquivo(video, chat=None, canal="canal", origem="live", jogo="", cfg=None):
    """Video local (gravacao da live ou arquivo do OBS): detecta os picos e gera os cortes."""
    cfg = _cfg_canal(canal, cfg)
    with _LOTE:
        _log(f"analisando {Path(video).name} (chat: {'sim' if chat and Path(chat).exists() else 'nao'})")
        janelas = deteccao.detectar(video, chat if chat and Path(chat).exists() else None, cfg)
        _log(f"{len(janelas)} momento(s) acima do limiar")
        ids = []
        for j in janelas:
            try:
                ids.append(processar_corte(video, j["inicio"], j["fim"], canal, origem, video, j["score"], j["motivo"], jogo, cfg))
            except Exception as e:
                _log(f"falha no corte {j['inicio']:.0f}s: {e}")
        legenda.liberar()
    avisar_novos(ids)
    return ids


def processar_vod(url, canal, chave=None, cfg=None):
    """VOD da Twitch: baixa SO o audio para achar os picos e depois so os trechos de video escolhidos (economiza disco e banda)."""
    cfg = _cfg_canal(canal, cfg)
    chave = chave or url
    tmp = config.sub("tmp") / f"vod_{_slug(chave)}"
    with _LOTE:
        _log(f"VOD {url}: baixando o audio para a analise")
        audio = captura.baixar(url, tmp / "audio", so_audio=True)
        janelas = deteccao.detectar(audio, None, cfg)
        _log(f"{len(janelas)} momento(s) no VOD")
        ids = []
        for n, j in enumerate(janelas):
            try:
                trecho = captura.baixar(url, tmp / f"trecho{n}", trecho=(j["inicio"], j["fim"]))
                dur = render.duracao(trecho) or (j["fim"] - j["inicio"])
                ids.append(processar_corte(trecho, 0, dur, canal, "vod", f"{url}@{j['inicio']:.0f}", j["score"], j["motivo"], cfg=cfg))
            except Exception as e:
                _log(f"falha no trecho {j['inicio']:.0f}s do VOD: {e}")
        legenda.liberar()
    fila.marcar_visto(f"vod:{chave}")
    avisar_novos(ids)
    return ids


def processar_clipe(clipe, canal, cfg=None):
    """Clipe ja escolhido pela comunidade (os mais vistos): so vira vertical com legenda."""
    cfg = _cfg_canal(canal, cfg)
    with _LOTE:
        arq = captura.baixar(clipe["url"], config.sub("tmp") / f"clipe_{_slug(str(clipe['id']))}")
        dur = min(render.duracao(arq) or 30, cfg.get("duracao_max_s", 58))
        id_ = processar_corte(arq, 0, dur, canal, "clipe", clipe["url"], float(clipe.get("views", 0)),
                              f"clipe da Twitch com {clipe.get('views', 0)} views: {clipe.get('titulo', '')[:60]}", cfg=cfg,
                              titulo_base=clipe.get("titulo", ""))
    fila.marcar_visto(f"clipe:{clipe['id']}")
    if not cfg.get("aprovacao_manual", True):
        avisar_novos([id_])  # modo automatico: o Dono ve o video no Telegram e ainda pode "rejeitar corte N" antes de subir
    return id_


# ---------- aviso ao Dono (Telegram do Jarvis) ----------

def _telegram(metodo, **kw):
    token, dono = config.env("TELEGRAM_BOT_TOKEN"), config.env("TELEGRAM_USER_ID")
    if not token or not dono.isdigit():
        return None
    kw.setdefault("data", {})["chat_id"] = int(dono)
    try:
        return requests.post(f"https://api.telegram.org/bot{token}/{metodo}", timeout=300, **kw)
    except requests.RequestException:
        return None


def avisar_novos(ids):
    if not ids or not config.carregar().get("avisar_telegram", True):
        return
    _telegram("sendMessage", data={"text": f"🎬 {len(ids)} corte(s) novo(s) pronto(s). Assista e diga ao Jarvis "
                                           f"\"aprovar corte N\" ou \"rejeitar corte N\" (ou \"aprovar todos os cortes\")."})
    for id_ in ids:
        c = fila.pegar(id_)
        leg = f"#{id_} · {c['titulo']}\n{c['motivo']}"
        if os.path.getsize(c["arquivo"]) < 49 * 1024 * 1024:  # limite de video do bot do Telegram
            with open(c["arquivo"], "rb") as f:
                _telegram("sendVideo", data={"caption": leg[:1000], "supports_streaming": "true"}, files={"video": (Path(c["arquivo"]).name, f)})
        else:
            _telegram("sendMessage", data={"text": leg + f"\n(arquivo grande: {c['arquivo']})"})


# ---------- aprovacao e publicacao ----------

def aprovar(ids):
    feitos = []
    for i in ids:
        c = fila.pegar(i)
        if c and c["status"] in ("renderizado", "rejeitado", "erro_youtube"):
            fila.atualizar(i, status="aprovado")
            feitos.append(i)
    return feitos


def rejeitar(ids):
    feitos = []
    for i in ids:
        c = fila.pegar(i)
        if c and c["status"] in ("renderizado", "aprovado"):
            fila.atualizar(i, status="rejeitado")
            feitos.append(i)
    return feitos


def proximo_horario(cfg, ocupados, agora=None):
    """Proximo horario livre da grade (youtube_horarios, hora local) dentro de youtube_agendar_dias. Horario de HOJE que ja
    passou e ficou vazio conta tambem (sobe na hora, para a meta do dia nao furar). None = agenda cheia."""
    agora = agora or time.time()
    hoje = time.localtime(agora)
    for d in range(int(cfg.get("youtube_agendar_dias", 2)) + 1):
        for h in sorted(cfg.get("youtube_horarios") or []):
            hh, mm = (int(x) for x in h.split(":"))
            ts = time.mktime((hoje.tm_year, hoje.tm_mon, hoje.tm_mday + d, hh, mm, 0, 0, 0, -1))
            if ts not in ocupados and (d == 0 or ts > agora):
                return ts
    return None


def publicar_aprovados():
    """Aprovados -> pasta do TikTok (sempre) + YouTube (se configurado e dentro do limite diario). Devolve relatorio."""
    rel, cheios, sem_login = [], set(), set()
    for c in reversed(fila.listar("aprovado", 50)):
        perfil = c.get("perfil") or ""
        cfg = config.do_perfil(perfil)
        conta = cfg.get("youtube_conta", "")
        if not c.get("tiktok"):
            try:
                destino = tiktok.preparar(c, perfil)
                estado = "pasta"
                if cfg.get("tiktok_rascunho_api"):
                    estado = "rascunho:" + tiktok.enviar_rascunho(destino)
                fila.atualizar(c["id"], tiktok=estado)
                rel.append(f"#{c['id']} TikTok: {'rascunho enviado ao app' if estado != 'pasta' else 'pronto em ' + str(destino.parent.name)}")
            except Exception as e:
                fila.atualizar(c["id"], erro=f"tiktok: {e}"[:300])
                rel.append(f"#{c['id']} TikTok falhou: {str(e)[:100]}")
        if not youtube.configurado(conta):
            sem_login.add(conta)
            continue
        # grade de horarios (ex. 12:00 e 19:00): cada video ganha um horario e o YouTube publica sozinho. So para perfil publico
        # (perfil privado, como o gringo, nunca vira publico por agendamento)
        grade = cfg.get("youtube_horarios") and cfg.get("youtube_privacidade") == "public"
        quando = None
        if grade:
            quando = None if perfil in cheios else proximo_horario(cfg, fila.horarios_ocupados(perfil))
            if quando is None:
                if perfil not in cheios:
                    rel.append(f"agenda do YouTube{' (' + perfil + ')' if perfil else ''} cheia pelos proximos "
                               f"{cfg.get('youtube_agendar_dias', 2)} dia(s); o resto espera na fila")
                cheios.add(perfil)
                continue
        elif perfil in cheios or fila.publicados_hoje(perfil) >= cfg.get("youtube_max_por_dia", 5):
            if perfil not in cheios:
                rel.append(f"limite diario do YouTube{' (' + perfil + ')' if perfil else ''} atingido; o resto sobe amanha")
            cheios.add(perfil)
            continue
        try:
            futuro = quando if quando and quando > time.time() + 600 else None  # horario de hoje que ja passou: publica na hora
            vid = youtube.enviar(c["arquivo"], c["titulo"], c["descricao"], (c["hashtags"] or "").split(),
                                 cfg.get("youtube_privacidade", "private"), cfg.get("youtube_categoria", "20"), conta, futuro)
            fila.atualizar(c["id"], status="publicado", youtube_id=vid, erro=None, agendado=quando)
            modo = f"agendado p/ {time.strftime('%d/%m %H:%M', time.localtime(futuro))}" if futuro else cfg.get("youtube_privacidade")
            rel.append(f"#{c['id']} YouTube ({modo}): https://youtube.com/shorts/{vid}")
        except Exception as e:
            # sai da fila automatica (senao o vigia tentaria e avisaria a cada ciclo); "aprovar N" tenta de novo
            fila.atualizar(c["id"], status="erro_youtube", erro=f"youtube: {e}"[:300])
            rel.append(f"#{c['id']} YouTube falhou: {str(e)[:120]} (diga 'aprovar corte {c['id']}' para tentar de novo)")
    if rel and sem_login:
        rel += [f"YouTube{' ' + c if c else ''} ainda nao configurado (python -m braniac.cortes youtube-login{' --perfil ' + c if c else ''}); "
                "os aprovados ficam esperando" for c in sorted(sem_login)]
    return rel
