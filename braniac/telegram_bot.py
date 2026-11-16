# -*- coding: utf-8 -*-
"""Jarvis no Telegram (texto e voz). So obedece ao dono (TELEGRAM_USER_ID) em conversa PRIVADA.

Configure em braniac/.env:  TELEGRAM_BOT_TOKEN (do @BotFather) e TELEGRAM_USER_ID (do @userinfobot).
Toda a logica de pedidos/duvidas fica em jarvis.py (a interface web usa o mesmo cerebro).

Seguranca: ID do dono + chat privado; ignora encaminhadas, editadas e mensagens antigas (replay);
limite de velocidade; estranhos sao registrados em data/seguranca.log e o dono e avisado.
Acoes sensiveis (enviar, chamar o Claude, atender) exigem a "Autonomia remota" armada na interface local do PC.
"""
import os, shutil, tempfile, threading, time
from collections import deque
from datetime import datetime
import requests
from . import contexto
from .jarvis import PENDENTE, processar, tratar  # noqa: F401  (cerebro unico, compartilhado com a interface web)
from .store import DATA

IDADE_MAX_S = 180        # mensagem mais velha que isso e descartada (evita reexecutar um "/sim" antigo)
LIMITE_POR_MIN = 20
ALERTADOS = {}           # id de estranho -> quando o dono foi avisado (1x por hora)


def _api(token, metodo, **kw):
    return requests.post(f"https://api.telegram.org/bot{token}/{metodo}", json=kw, timeout=60).json()


def _log_seguranca(linha):
    DATA.mkdir(exist_ok=True)
    with (DATA / "seguranca.log").open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {linha}\n")


def _baixar_audio(token, file_id):
    info = _api(token, "getFile", file_id=file_id)["result"]
    r = requests.get(f"https://api.telegram.org/file/bot{token}/{info['file_path']}", timeout=60)
    f = tempfile.NamedTemporaryFile(suffix=os.path.splitext(info["file_path"])[1] or ".ogg", delete=False)
    f.write(r.content)
    f.close()
    (DATA / "vozes").mkdir(parents=True, exist_ok=True)   # 20/10: guarda o ultimo audio do Dono p/ clonar a voz dele (Dono)
    shutil.copyfile(f.name, DATA / "vozes" / "ultimo-telegram.ogg")
    return f.name


def _enviar_voz(token, chat_id, ogg):
    requests.post(f"https://api.telegram.org/bot{token}/sendVoice", data={"chat_id": chat_id},
                  files={"voice": ("jarvis.ogg", ogg, "audio/ogg")}, timeout=120)


def avisar_dono(texto):
    """Mensagem de texto ao dono no Telegram (usado quando nao ha canal aberto para avisar). Devolve True se enviou."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    dono = os.environ.get("TELEGRAM_USER_ID", "").strip()
    if not token or not dono.isdigit():
        return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={"chat_id": int(dono), "text": texto[:4000]}, timeout=30)
        return r.status_code == 200
    except Exception:
        return False


def mandar_foto_ao_dono(caminho, legenda=""):
    """Manda uma imagem (arquivo) ao dono no Telegram. Devolve o resultado em texto."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    dono = os.environ.get("TELEGRAM_USER_ID", "").strip()
    if not token or not dono.isdigit():
        return "Telegram não configurado"
    try:
        with open(caminho, "rb") as f:
            r = requests.post(f"https://api.telegram.org/bot{token}/sendPhoto", data={"chat_id": int(dono), "caption": legenda[:900]},
                              files={"photo": (os.path.basename(str(caminho)), f)}, timeout=120)
        return "imagem enviada ao Dono no Telegram" if r.status_code == 200 else f"Telegram recusou a imagem (HTTP {r.status_code})"
    except Exception as e:
        return f"falha ao enviar a imagem: {str(e)[:120]}"


def mandar_audio_ao_dono(texto):
    """Fala `texto` com a voz do Jarvis e manda como mensagem de voz ao dono no Telegram. Devolve o resultado em texto."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    dono = os.environ.get("TELEGRAM_USER_ID", "").strip()
    if not token or not dono.isdigit() or not texto.strip():
        return "não consegui: Telegram não configurado ou texto vazio"
    try:
        from . import voz
        _enviar_voz(token, int(dono), voz.falar_ogg(texto[:1500]))
        return "áudio enviado ao Dono no Telegram"
    except Exception as e:
        return f"falha ao gerar/enviar o áudio: {str(e)[:120]}"


def classificar(m, dono, agora=None):
    """Decide o que fazer com uma mensagem recebida. Funcao pura (testavel).
    -> 'ok' | 'estranho' | 'ignorar' | 'encaminhada' | 'antiga'"""
    agora = agora or time.time()
    de = (m.get("from") or {}).get("id")
    chat = m.get("chat") or {}
    if de != dono or chat.get("type") != "private" or chat.get("id") != dono:
        return "estranho"
    if any(k in m for k in ("forward_origin", "forward_from", "forward_from_chat", "forward_date", "forward_sender_name")):
        return "encaminhada"
    if agora - m.get("date", 0) > IDADE_MAX_S:
        return "antiga"
    return "ok"


def _responder_audio(token, router, chat_id, file_id):
    """Ouve (Whisper local), pensa (Braniac) e responde em audio com a voz masculina."""
    from . import voz
    caminho = _baixar_audio(token, file_id)
    try:
        texto = voz.transcrever(caminho)
    finally:
        os.unlink(caminho)
    if not texto:
        return _api(token, "sendMessage", chat_id=chat_id, text="Não consegui entender o áudio, pode repetir?")
    if router.cfg.get("eco_transcricao", False):  # decisao do Dono: nao repetir o que ele falou (padrao desligado)
        _api(token, "sendMessage", chat_id=chat_id, text=f"🎙 Entendi: {texto}")
    contexto.atualizar_preferencia("telegram", texto)
    resp, da_ia = processar(router, texto, "telegram", lambda x: _api(token, "sendMessage", chat_id=chat_id, text=x[:4000]),
                            origem="telegram")
    _api(token, "sendMessage", chat_id=chat_id, text=resp[:4000])
    if da_ia and contexto.deve_falar("telegram", resp):  # conversa sai falada; status/confirmacoes/links so em texto
        try:
            _enviar_voz(token, chat_id, voz.falar_ogg(resp))
        except Exception:
            pass


def iniciar(router):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    dono = os.environ.get("TELEGRAM_USER_ID", "").strip()
    if not token or not dono.isdigit():
        return None
    dono = int(dono)

    def avisar(txt):
        try:
            _api(token, "sendMessage", chat_id=dono, text=txt[:4000])
        except Exception:
            pass

    def tratar_msg(m):
        veredito = classificar(m, dono)
        if veredito == "estranho":
            quem = m.get("from") or {}
            _log_seguranca(f"ESTRANHO id={quem.get('id')} user=@{quem.get('username')} chat={(m.get('chat') or {}).get('type')} "
                           f"texto={str(m.get('text', ''))[:40]!r}")
            if time.time() - ALERTADOS.get(quem.get("id"), 0) > 3600:
                ALERTADOS[quem.get("id")] = time.time()
                avisar(f"⚠️ Segurança: o ID {quem.get('id')} (@{quem.get('username')}) tentou falar com o Jarvis. Foi ignorado.")
            return
        if veredito == "antiga":
            _log_seguranca("antiga-descartada")
            return
        if veredito == "encaminhada":
            _log_seguranca("encaminhada-recusada")
            avisar("Por segurança não executo mensagens encaminhadas. Escreva o pedido você mesmo.")
            return
        chat_id = m["chat"]["id"]
        audio = m.get("voice") or m.get("audio")
        try:
            _api(token, "sendChatAction", chat_id=chat_id, action="typing")
            if audio:
                _responder_audio(token, router, chat_id, audio["file_id"])
            elif m.get("text"):
                contexto.atualizar_preferencia("telegram", m["text"])  # "por escrito" -> so texto; "pode mandar audio" -> volta a falar
                resp, da_ia = processar(router, m["text"], "telegram", lambda x, c=chat_id: _api(token, "sendMessage", chat_id=c, text=x[:4000]),
                                        origem="telegram")
                resp = (resp or "").strip() or "Recebi, mas não tenho o que responder agora. Tente reformular."
                _api(token, "sendMessage", chat_id=chat_id, text=resp[:4000])
                if da_ia and contexto.deve_falar("telegram", resp):  # PADRAO: tambem fala (voz masculina)
                    from . import voz
                    try:
                        _enviar_voz(token, chat_id, voz.falar_ogg(resp))
                    except Exception:
                        pass
        except Exception as e:  # o dono NUNCA fica sem resposta: se algo quebrar, ele fica sabendo
            _log_seguranca(f"ERRO ao tratar mensagem: {e!r}")
            avisar(f"Tive um problema ao processar isso ({type(e).__name__}). Já registrei; tente de novo ou me diga de outro jeito.")

    def loop():
        offset = 0
        recentes = deque(maxlen=LIMITE_POR_MIN)
        while True:
            try:
                r = _api(token, "getUpdates", offset=offset, timeout=50, allowed_updates=["message"])
                for u in r.get("result", []):
                    offset = u["update_id"] + 1
                    m = u.get("message")
                    if not m:
                        continue
                    agora = time.time()
                    recentes.append(agora)
                    if len(recentes) == LIMITE_POR_MIN and agora - recentes[0] < 60:
                        _log_seguranca("limite-de-velocidade")
                        continue
                    # cada mensagem em sua propria thread: uma resposta lenta (IA, Claude) nao trava as outras
                    threading.Thread(target=tratar_msg, args=(m,), daemon=True, name="braniac-tg-msg").start()
            except Exception:
                time.sleep(10)
    t = threading.Thread(target=loop, daemon=True, name="braniac-telegram")
    t.start()
    return t
