# -*- coding: utf-8 -*-
"""Comandos dos cortes em texto: usados pela linha de comando e pela ferramenta 'cortes' do Jarvis."""
import re, threading
from pathlib import Path
from . import config, fila, pipeline, twitch, vigia, youtube


def status():
    cfg = config.carregar()
    canais = [c["login"] + (f" ({c['perfil']})" if c.get("perfil") else "") for c in cfg["canais"] if c.get("autorizado")]
    r = fila.resumo()
    linhas = [f"Vigia dos cortes: {'LIGADO' if vigia.rodando() else 'desligado'}",
              f"Canais autorizados: {', '.join(canais) or 'nenhum (editar ' + str(config.ARQ) + ')'}",
              f"Twitch API: {'sim' if twitch.tem_api() else 'nao (usando streamlink/yt-dlp)'} · YouTube: {'configurado' if youtube.configurado() else 'falta login'}"
              + "".join(f" · YouTube {p}: {'configurado' if youtube.configurado(v.get('youtube_conta', p)) else 'falta login'}"
                        for p, v in cfg.get("perfis", {}).items()),
              "Fila: " + (", ".join(f"{k} {v}" for k, v in r.items()) or "vazia")]
    if cfg.get("youtube_horarios"):
        import time
        hoje = time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, -1))
        ag = fila.agenda("", hoje)
        linhas.append(f"Meta: {len(cfg['youtube_horarios'])} video(s)/dia as {', '.join(cfg['youtube_horarios'])} · estoque {fila.estoque()} · "
                      "agenda: " + ("; ".join(f"{time.strftime('%d/%m %H:%M', time.localtime(c['agendado']))} #{c['id']}" for c in ag) or "vazia"))
    pend = fila.listar("renderizado", 10)
    if pend:
        linhas.append("Esperando aprovacao: " + "; ".join(f"#{c['id']} {c['titulo'][:50]}" for c in pend))
    return "\n".join(linhas)


def listar(status=None):
    cs = fila.listar(status or None, 15)
    if not cs:
        return "nenhum corte" + (f" com status {status}" if status else "")
    return "\n".join(f"#{c['id']} [{c['status']}] {c['canal']} · {c['fim'] - c['inicio']:.0f}s · {c['titulo'][:60]} ({c['motivo'] or ''})"
                     + (f" · yt {c['youtube_id']}" if c.get("youtube_id") else "") for c in cs)


def _ids(alvo):
    if str(alvo).strip().lower() in ("todos", "tudo", "all"):
        return [c["id"] for c in fila.listar("renderizado", 100)]
    return [int(x) for x in re.findall(r"\d+", str(alvo))]


def aprovar(alvo):
    ok = pipeline.aprovar(_ids(alvo))
    if not ok:
        return "nenhum corte aprovado (confira os numeros com 'listar')"
    return f"aprovado(s): {', '.join('#' + str(i) for i in ok)}. Sobem no proximo ciclo do vigia (ou rode 'publicar')."


def rejeitar(alvo):
    ok = pipeline.rejeitar(_ids(alvo))
    return f"rejeitado(s): {', '.join('#' + str(i) for i in ok)}" if ok else "nenhum corte rejeitado"


def processar(alvo, chat=None, canal=None, em_segundo_plano=False):
    """Arquivo local, link de VOD ou link de clipe da Twitch."""
    alvo = alvo.strip()
    m = re.search(r"twitch\.tv/(\w+)", alvo)
    canal = canal or (m.group(1) if m and m.group(1) not in ("videos",) else None) or "canal"

    def tarefa():
        if Path(alvo).exists():
            return pipeline.processar_arquivo(alvo, chat, canal, "arquivo")
        if "clip" in alvo:
            return [pipeline.processar_clipe({"id": alvo, "url": alvo, "views": 0, "titulo": ""}, canal)]
        if alvo.startswith("http"):
            return pipeline.processar_vod(alvo, canal)
        raise ValueError(f"nao achei o arquivo nem e um link: {alvo}")

    if em_segundo_plano:
        threading.Thread(target=lambda: _seguro(tarefa), daemon=True).start()
        return "processando em segundo plano; os cortes chegam no Telegram quando ficarem prontos"
    ids = tarefa()
    return f"{len(ids)} corte(s) gerado(s): {', '.join('#' + str(i) for i in ids)}" if ids else "nenhum momento forte encontrado"


def _seguro(f):
    try:
        f()
    except Exception as e:
        pipeline._log(f"processamento falhou: {e}")
        pipeline._telegram("sendMessage", data={"text": f"🎬 Corte falhou: {str(e)[:300]}"})


def publicar():
    return "\n".join(pipeline.publicar_aprovados()) or "nada aprovado esperando publicacao"


def executar(acao, alvo=""):
    """Entrada unica para o Jarvis."""
    acao = (acao or "status").lower()
    if acao == "status":
        return status()
    if acao == "listar":
        return listar(alvo or None)
    if acao == "aprovar":
        return aprovar(alvo)
    if acao == "rejeitar":
        return rejeitar(alvo)
    if acao == "processar":
        return processar(alvo, em_segundo_plano=True) if alvo else "diga o arquivo ou link"
    if acao == "publicar":
        return publicar()
    if acao == "ligar":
        return vigia.ligar_em_segundo_plano()
    if acao == "desligar":
        return vigia.desligar()
    return f"acao desconhecida: {acao}"
