# -*- coding: utf-8 -*-
"""CONTROLE REMOTO PELO TELEGRAM (bot da propria pessoa). Ela conversa com o assistente e manda comandos para o PC de qualquer lugar.

Travas (todas ativas):
 1. Desligado de fabrica: so existe se a pessoa criar o bot e colar o token (guardado no cofre do Windows).
 2. PAREAMENTO: um codigo de uso unico, exibido SO na tela do PC, vale 10 min; o 1o usuario do Telegram que mandar /parear <codigo> vira o DONO.
    Depois disso so o ID numerico do dono e atendido, em conversa privada. Qualquer outra pessoa e ignorada (e registrada).
 3. ARMADO: mesmo pareado, o Telegram so executa acoes no PC enquanto a pessoa mantiver o controle remoto ARMADO (arma-se SO pela tela local,
    por tempo limitado ou 'sempre'). Pelo Telegram da para DESARMAR (/parar), nunca armar.
 4. PERMISSOES: toda acao passa pelas permissoes liberadas na instalacao (pc_tools -> permissoes.exigir).
 5. CONFIRMACAO: acoes perigosas (apagar, escrever arquivo, executar comando, enviar WhatsApp) so rodam depois que o dono responde SIM <codigo> (2 min, uso unico).
 6. A IA so ESCOLHE a acao a partir da mensagem do dono; o resultado vai para o dono e NUNCA volta para a IA (nada escondido em arquivo/mensagem manda no PC).
 7. Limite de 30 comandos por minuto e registro (auditoria) de tudo em remoto.log.
Aviso mostrado na tela: textos e prints enviados passam pelos servidores do Telegram.
"""
import json, random, re, string, threading, time, urllib.parse, urllib.request
from . import cofre, llm, paths, permissoes, pc_tools

API = "https://api.telegram.org/bot{token}/{metodo}"
LIMITE_POR_MIN = 30
VALIDADE_CODIGO_S = 600
VALIDADE_CONFIRMACAO_S = 120


class RemotoErro(RuntimeError):
    pass


def _arq():
    return paths.arquivo("remoto.json")


def _estado():
    try:
        return json.loads(_arq().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _salvar(e):
    _arq().write_text(json.dumps(e, ensure_ascii=False), encoding="utf-8")


def _log(txt):
    with paths.arquivo("remoto.log").open("a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {txt}\n")


# ---------- configuracao (tela local) ----------

def _http(metodo, token, dados=None, timeout=35):
    corpo = urllib.parse.urlencode(dados or {}).encode()
    with urllib.request.urlopen(urllib.request.Request(API.format(token=token, metodo=metodo), corpo), timeout=timeout) as r:
        return json.loads(r.read())


def cadastrar_token(token, http=None):
    """Valida o token (getMe) e so entao guarda no cofre. Devolve o @ do bot."""
    token = (token or "").strip()
    if not re.fullmatch(r"\d{6,12}:[A-Za-z0-9_-]{30,}", token):
        raise RemotoErro("esse token não parece certo; copie ele inteiro da conversa com o @BotFather")
    try:
        r = (http or _http)("getMe", token)
    except Exception:
        raise RemotoErro("o Telegram recusou esse token (ou sem internet)")
    if not r.get("ok"):
        raise RemotoErro("o Telegram recusou esse token")
    cofre.guardar("telegram", token)
    e = _estado()
    e.update(bot=r["result"].get("username"), ativo=True)
    _salvar(e)
    return e["bot"]


def novo_codigo(reparear=False):
    """Codigo de pareamento: aparece SO na tela do PC. reparear=True esquece o dono atual (trocar de celular/conta)."""
    cod = "".join(random.SystemRandom().choice(string.ascii_uppercase + string.digits) for _ in range(6))
    e = _estado()
    if reparear:
        e.pop("dono_id", None)
        e["armado_ate"] = None
    e["pareamento"] = {"codigo": cod, "ate": time.time() + VALIDADE_CODIGO_S}
    _salvar(e)
    return cod


def armar(minutos=None):
    """SO pela tela local. minutos=None => 'sempre armado' ate desarmar."""
    e = _estado()
    if not e.get("dono_id"):
        raise RemotoErro("pareie o Telegram antes de armar o controle remoto")
    e["armado_ate"] = (time.time() + minutos * 60) if minutos else "sempre"
    _salvar(e)
    _log(f"ARMADO ({'sempre' if not minutos else f'{minutos} min'})")


def desarmar():
    e = _estado()
    e["armado_ate"] = None
    e.pop("pendente", None)
    _salvar(e)
    _log("DESARMADO")


def armado():
    a = _estado().get("armado_ate")
    return a == "sempre" or (isinstance(a, (int, float)) and time.time() < a)


def resumo():
    e = _estado()
    a = e.get("armado_ate")
    return {"bot": e.get("bot"), "ativo": bool(e.get("ativo")), "pareado": bool(e.get("dono_id")), "armado": armado(),
            "armado_ate": a if a == "sempre" else (int(a) if isinstance(a, (int, float)) and armado() else None),
            "codigo": (e.get("pareamento") or {}).get("codigo") if (e.get("pareamento") or {}).get("ate", 0) > time.time() else None}


def desligar_tudo():
    """Remove token, dono e arma: o bot para de responder."""
    try:
        cofre.remover("telegram")
    except cofre.CofreErro:
        pass
    _salvar({})
    _log("REMOTO REMOVIDO")


# ---------- planejamento (a IA so escolhe a acao) ----------

def _planejar_padrao(texto):
    cat = pc_tools.catalogo_para_ia()
    sistema = ("Você é o assistente pessoal do dono deste PC. Converta o pedido dele em UMA ação. Responda SOMENTE um JSON: "
               '{"acao": "<nome da ferramenta ou nenhuma>", "args": {...}, "resposta": "frase curta para o dono"}. '
               "Use 'nenhuma' para conversa comum (e coloque a resposta em 'resposta'). Ferramentas disponíveis:\n" + (cat or "(nenhuma liberada)"))
    bruto, _ = llm.responder(texto, sistema=sistema)
    m = re.search(r"\{.*\}", bruto, re.S)
    if not m:
        return {"acao": "nenhuma", "args": {}, "resposta": bruto.strip()[:1500]}
    try:
        d = json.loads(m.group(0))
    except ValueError:
        return {"acao": "nenhuma", "args": {}, "resposta": bruto.strip()[:1500]}
    return {"acao": d.get("acao", "nenhuma"), "args": d.get("args") or {}, "resposta": str(d.get("resposta") or "")[:1500]}


def _conversar_padrao(texto):
    return llm.responder(texto, sistema="Você é o assistente pessoal do dono, conversando pelo Telegram. Responda curto, em português. "
                                        "O controle remoto do PC está desarmado agora, então não execute nem prometa ações no PC.")[0]


# ---------- tratamento de mensagens ----------

class Bot:
    def __init__(self, token=None, http=None, planejar=None, conversar=None):
        self.token, self.http = token, http or _http
        self.planejar, self.conversar = planejar or _planejar_padrao, conversar or _conversar_padrao
        self.parar_flag = threading.Event()
        self.enviados = []     # testes
        self.recentes = []

    # --- envio ---
    def dizer(self, chat, texto):
        self.enviados.append(("texto", chat, texto))
        if self.token:
            self.http("sendMessage", self.token, {"chat_id": chat, "text": texto[:4000]})

    def foto(self, chat, png, legenda=""):
        self.enviados.append(("foto", chat, legenda))
        if not self.token:
            return
        lim = "----braniac" + "".join(random.choice(string.ascii_letters) for _ in range(12))
        corpo = (f'--{lim}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{chat}\r\n'
                 f'--{lim}\r\nContent-Disposition: form-data; name="caption"\r\n\r\n{legenda}\r\n'
                 f'--{lim}\r\nContent-Disposition: form-data; name="photo"; filename="tela.png"\r\nContent-Type: image/png\r\n\r\n').encode() + png + f"\r\n--{lim}--\r\n".encode()
        req = urllib.request.Request(API.format(token=self.token, metodo="sendPhoto"), corpo, {"Content-Type": f"multipart/form-data; boundary={lim}"})
        urllib.request.urlopen(req, timeout=60).read()

    # --- regras ---
    def _limite(self):
        agora = time.time()
        self.recentes = [t for t in self.recentes if agora - t < 60]
        if len(self.recentes) >= LIMITE_POR_MIN:
            return False
        self.recentes.append(agora)
        return True

    def tratar(self, upd):
        msg = upd.get("message") or {}
        texto = (msg.get("text") or "").strip()
        de, chat = (msg.get("from") or {}).get("id"), (msg.get("chat") or {})
        if not texto or de is None:
            return
        if chat.get("type") != "private":
            return _log(f"ignorado: mensagem de grupo/canal ({chat.get('type')})")
        e = _estado()
        m = re.match(r"^/parear\s+([A-Za-z0-9]{6})\s*$", texto)
        if not e.get("dono_id"):
            p = e.get("pareamento") or {}
            if m and p.get("ate", 0) > time.time() and m.group(1).upper() == p.get("codigo"):
                e.update(dono_id=de, pareamento=None)
                _salvar(e)
                _log(f"PAREADO com o usuario {de}")
                return self.dizer(chat["id"], "Pareado! ✅ Agora só você fala comigo por aqui. Por segurança, o controle do PC começa DESARMADO: "
                                              "arme na tela do BRANIAC no computador. Mande /ajuda para ver os comandos.")
            return _log(f"ignorado: {de} tentou falar sem pareamento válido")
        if de != e["dono_id"]:
            return _log(f"ignorado: usuário {de} não é o dono")
        if not self._limite():
            return self.dizer(chat["id"], "Muitos comandos seguidos. Espere um minuto.")
        _log(f"dono: {texto[:200]}")
        cmd = texto.lower().split()[0]
        if cmd in ("/parar", "/desarmar", "/stop"):
            desarmar()
            return self.dizer(chat["id"], "⛔ Controle remoto DESARMADO. Nada mais será executado no PC até você armar de novo pela tela do computador.")
        if cmd in ("/ajuda", "/start", "/help"):
            return self.dizer(chat["id"], "Fale normalmente. Exemplos: «abre a calculadora», «lista a pasta Documentos», «tira um print da tela», "
                                          "«o que chegou no WhatsApp?». Ações perigosas pedem confirmação (SIM <código>).\n"
                                          "/status – estado · /parar – desarma tudo na hora")
        if cmd == "/status":
            return self.dizer(chat["id"], f"Controle remoto: {'ARMADO' if armado() else 'desarmado'}. Permissões liberadas: {len(permissoes.liberadas())}.")
        conf = re.match(r"^(sim|s|confirmo)\s+(\d{4})\s*$", texto, re.I)
        pend = e.get("pendente")
        if conf and pend:
            if time.time() > pend["ate"] or conf.group(2) != pend["codigo"] or not armado():
                e.pop("pendente", None)
                _salvar(e)
                return self.dizer(chat["id"], "Esse código expirou, está errado ou o controle foi desarmado. Peça de novo.")
            e.pop("pendente", None)
            _salvar(e)
            return self._executar(chat["id"], pend["acao"], pend["args"])
        if re.match(r"^(n[aã]o|cancela\w*|nao)\b", texto, re.I) and pend:
            e.pop("pendente", None)
            _salvar(e)
            return self.dizer(chat["id"], "Cancelado. Nada foi feito.")
        if not armado():
            try:
                return self.dizer(chat["id"], self.conversar(texto) + "\n\n(🔒 Controle do PC desarmado: arme na tela do BRANIAC para eu agir no computador.)")
            except Exception:
                return self.dizer(chat["id"], "Estou sem nenhuma IA disponível agora. 🔒 O controle do PC está desarmado.")
        try:
            plano = self.planejar(texto)
        except Exception as ex:
            return self.dizer(chat["id"], f"Não consegui interpretar agora ({str(ex)[:80]}).")
        acao, args = plano.get("acao"), plano.get("args") or {}
        if acao in (None, "", "nenhuma") or acao not in pc_tools.FERRAMENTAS:
            return self.dizer(chat["id"], plano.get("resposta") or "Não entendi o que fazer. Pode explicar de outro jeito?")
        try:
            permissoes.exigir(pc_tools.FERRAMENTAS[acao][2])
        except permissoes.PermissaoNegada as ex:
            _log(f"negado: {acao} ({ex})")
            return self.dizer(chat["id"], f"🚫 {ex} Libere na tela do BRANIAC (Acesso ao PC) se quiser.")
        if pc_tools.precisa_confirmar(acao):
            cod = "".join(random.SystemRandom().choice(string.digits) for _ in range(4))
            e["pendente"] = {"acao": acao, "args": args, "codigo": cod, "ate": time.time() + VALIDADE_CONFIRMACAO_S}
            _salvar(e)
            return self.dizer(chat["id"], f"⚠️ Vou executar: {pc_tools.descrever(acao, args)}\nPara confirmar responda: SIM {cod}  (vale 2 min). Para cancelar: NÃO.")
        return self._executar(chat["id"], acao, args)

    def _executar(self, chat_id, acao, args):
        try:
            texto, imagem = pc_tools.executar_ferramenta(acao, args)
            _log(f"executou: {pc_tools.descrever(acao, args)}")
            if imagem:
                return self.foto(chat_id, imagem, texto)
            return self.dizer(chat_id, texto[:3900])
        except (permissoes.PermissaoNegada, pc_tools.FerramentaErro) as ex:
            _log(f"falhou: {acao} ({ex})")
            return self.dizer(chat_id, f"🚫 {ex}")
        except Exception as ex:
            _log(f"erro: {acao} ({ex!r})")
            return self.dizer(chat_id, f"Deu erro ao executar: {str(ex)[:200]}")

    # --- laco de recebimento (long polling) ---
    def loop(self):
        offset = _estado().get("offset", 0)
        while not self.parar_flag.is_set():
            try:
                r = self.http("getUpdates", self.token, {"offset": offset, "timeout": 25, "allowed_updates": json.dumps(["message"])}, timeout=40)
                for u in r.get("result", []):
                    offset = u["update_id"] + 1
                    try:
                        self.tratar(u)
                    except Exception as ex:
                        _log(f"erro tratando mensagem: {ex!r}")
                e = _estado()
                e["offset"] = offset
                _salvar(e)
            except Exception as ex:
                _log(f"polling: {str(ex)[:100]}")
                self.parar_flag.wait(8)


_bot = None


def iniciar():
    """Sobe o bot em segundo plano se houver token e dono. Chamado pelo backend ao iniciar e depois do pareamento."""
    global _bot
    if _bot and not _bot.parar_flag.is_set():
        return True
    try:
        token = cofre.ler("telegram")
    except cofre.CofreErro:
        token = None
    if not token or not _estado().get("ativo"):
        return False
    _bot = Bot(token)
    threading.Thread(target=_bot.loop, daemon=True, name="telegram-remoto").start()
    return True


def parar():
    global _bot
    if _bot:
        _bot.parar_flag.set()
        _bot = None
