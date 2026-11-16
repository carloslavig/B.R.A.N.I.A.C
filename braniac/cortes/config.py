# -*- coding: utf-8 -*-
"""Configuracao dos cortes: braniac/data/cortes/cortes.json (criado com valores padrao na 1a execucao)."""
import json, os
from pathlib import Path

PASTA = Path(__file__).resolve().parent.parent / "data" / "cortes"
ARQ = PASTA / "cortes.json"

PADRAO = {
    # Canais vigiados. So entram canais com "autorizado": true (canal do Dono, ou streamer com politica de cortes
    # permissiva / que autorizou). Em "politica" anote a prova (link/print da regra do streamer). Cortar conteudo alheio
    # sem permissao gera strike de direito autoral no YouTube/TikTok. A lista e preenchida pelo Dono.
    "canais": [
        {"login": "exemplo_canal", "autorizado": False, "politica": "", "live": True, "vods": False, "clipes": True}
    ],
    "intervalo_min": 2,             # checagem de live
    "clipes_cada_h": 6,             # busca de clipes populares
    "clipes_janela_h": 48,
    "clipes_max": 5,                # clipes mais vistos por busca
    "clipes_min_views": 20,
    "clipes_ignorar_titulos": ["replay", "rerun", "reprise"],
    "cortes_por_live": 6,
    "duracao_min_s": 25,
    "duracao_max_s": 58,            # <= 60 s vira Short
    "antes_do_pico_s": 22,          # o "setup" do momento vem antes do pico
    "depois_do_pico_s": 10,
    "atraso_chat_s": 6,             # o chat reage alguns segundos depois do lance
    "peso_audio": 1.0,
    "peso_chat": 1.4,
    "score_minimo": 2.0,            # z-score combinado minimo para virar corte
    "idioma": "pt",
    "whisper_modelo": "",           # vazio = braniac/modelos/whisper-small
    "enquadramento": "desfocado",   # desfocado (video inteiro + fundo borrado) | centro (recorte central)
    "legenda": True,
    "titulos_ollama": True,         # titulo/hashtags pela IA LOCAL (Ollama); nunca IA paga
    "ollama_modelo": "qwen2.5:3b",
    "aprovacao_manual": True,       # nada e publicado sem /aprovar do Dono
    "youtube_privacidade": "private",  # private | unlisted | public
    "youtube_categoria": "20",      # 20 = Games
    "youtube_max_por_dia": 5,
    "youtube_horarios": [],         # ex. ["12:00", "19:00"]: 1 video por horario (agendado no YouTube); vazio = sobe na hora
    "youtube_agendar_dias": 2,      # agenda no maximo ate N dias a frente (o resto espera na fila)
    "tiktok_rascunho_api": False,   # True so depois do app do TikTok aprovado (TIKTOK_ACCESS_TOKEN no .env)
    "manter_gravacoes_dias": 3,
    "pausar_no_modo_jogo": True,    # Braniac em modo jogo: grava a live, mas so processa depois
    "avisar_telegram": True,
    # Perfis: cada um e um canal de YouTube/TikTok separado. Canal da Twitch com "perfil": "gringo" usa estes valores por cima
    # dos gerais (idioma da legenda/titulo, login do YouTube, filtros de clipe). Sem "perfil" = canal PT de sempre.
    "perfis": {
        "gringo": {
            "idioma": "en",
            "youtube_conta": "gringo",          # token proprio: youtube_token_gringo.json (outro canal do YouTube)
            "youtube_privacidade": "private",   # sobe privado ate o Dono conferir o canal; depois "public"
            "aprovacao_manual": True,
            "clipes_janela_h": 168,             # clipes virais dos ultimos 7 dias
            "clipes_cada_h": 6,
            "clipes_max": 5,
            "clipes_min_views": 2000,           # streamer grande: so o que realmente viralizou
            "titulos_ollama": True,
            "hashtags_fixas": ["#shorts", "#twitch", "#twitchclips", "#streamer"],
            "descricao_modelo": ("{titulo}\n\n"
                                 "🎮 Streamer: {nome} — watch the full streams live at https://twitch.tv/{canal}\n"
                                 "{link_original}"
                                 "\nAll credit goes to {nome}. We share short highlights so more people discover the stream. "
                                 "If you are the creator and want this removed, comment or contact us and it will be taken down.\n\n"
                                 "🔔 Subscribe for the best Twitch moments every day.\n\n{hashtags}"),
        },
    },
}


def carregar():
    PASTA.mkdir(parents=True, exist_ok=True)
    if not ARQ.exists():
        ARQ.write_text(json.dumps(PADRAO, ensure_ascii=False, indent=2), encoding="utf-8")
        return dict(PADRAO)
    try:
        cfg = json.loads(ARQ.read_text(encoding="utf-8-sig"))
    except ValueError:
        cfg = {}
    return {**PADRAO, **cfg}


def para_canal(canal, cfg=None):
    """Config efetiva de um canal da Twitch: gerais + perfil + ajustes do proprio canal. Inclui 'perfil', 'canal' e 'nome'."""
    cfg = cfg or carregar()
    perfil = (canal or {}).get("perfil", "") if isinstance(canal, dict) else ""
    efetiva = {**cfg, **cfg.get("perfis", {}).get(perfil, {}), **((canal or {}).get("ajustes") or {}), "perfil": perfil}
    if isinstance(canal, dict):
        efetiva["canal"] = canal.get("login", "")
        efetiva["nome"] = canal.get("nome") or canal.get("login", "")
        if canal.get("idioma"):
            efetiva["idioma"] = canal["idioma"]
    return efetiva


def do_perfil(perfil):
    cfg = carregar()
    return {**cfg, **cfg.get("perfis", {}).get(perfil or "", {}), "perfil": perfil or ""}


def canal_por_login(login):
    for c in carregar().get("canais", []):
        if c.get("login", "").lower() == (login or "").lower():
            return c
    return {"login": login}


def sub(nome):
    p = PASTA / nome
    p.mkdir(parents=True, exist_ok=True)
    return p


def env(chave, padrao=""):
    if chave not in os.environ:
        from ..router import carregar_env
        carregar_env()
    return os.environ.get(chave, padrao).strip()
