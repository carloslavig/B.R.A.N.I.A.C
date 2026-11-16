# -*- coding: utf-8 -*-
"""WhatsApp local do Jarvis: SO LEITURA, via Chrome de automacao (porta 9222) e local-ia/wpp_local.py.

Resumos usam o Ollama local: mensagens de contatos/hospedes nunca vao para IAs online.
Observacao: abrir uma conversa no WhatsApp Web marca as mensagens como lidas para o contato.
Enviar mensagens NAO esta exposto aqui (fica para uma fase com confirmacao).
"""
import functools, json, re, sys, threading, time, unicodedata
from pathlib import Path
from .store import DATA

# UMA pagina do WhatsApp, varios 'bracos' (vigia do Dono, atendimento, voz, comandos): so um mexe nela por vez.
# Sem isto dois processos abrem conversas diferentes ao mesmo tempo e o envio vai para o chat errado ou falha.
LOCK = threading.RLock()


def _com_pagina(f):
    @functools.wraps(f)
    def g(*a, **k):
        with LOCK:
            return f(*a, **k)
    return g


PEND_ARQ = DATA / "wpp_pendentes.json"  # conversas cuja ultima mensagem e DELES e ainda nao foi respondida/tratada


def pendentes_ler():
    try:
        return json.loads(PEND_ARQ.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _pend_gravar(lista):
    DATA.mkdir(exist_ok=True)
    PEND_ARQ.write_text(json.dumps(lista, ensure_ascii=False), encoding="utf-8")


def pendente_add(nome):
    p = pendentes_ler()
    if nome not in p:
        _pend_gravar(p + [nome])


def pendente_remover(nome):
    _pend_gravar([n for n in pendentes_ler() if n != nome])

LOCAL_IA = Path(__file__).parent.parent / "local-ia"


def _wpp():
    if str(LOCAL_IA) not in sys.path:
        sys.path.insert(0, str(LOCAL_IA))
    import wpp_local
    return wpp_local


def _norm(x):
    return "".join(c for c in unicodedata.normalize("NFD", x.lower()) if unicodedata.category(c) != "Mn").strip()


def resolver_nome(nome, nomes_visiveis):
    """Apelido (base de conhecimento) -> nome do contato; busca parcial sem acento/maiuscula. Devolve candidatos."""
    from . import contexto
    alvo = _norm(contexto.contato(nome) or nome)
    exatos = [n for n in nomes_visiveis if _norm(n) == alvo]
    if exatos or not alvo:
        return exatos
    # 14/10: casa por INICIO DE PALAVRA, nao por pedaco solto -- 'Eu' (de 'Eu') casava com 'dEUsa Parceira' e o audio foi pra pessoa errada
    q = re.findall(r"\w+", alvo)
    return [n for n in nomes_visiveis if q and all(any(t.startswith(p) for t in re.findall(r"\w+", _norm(n))) for p in q)]


@_com_pagina
def listar_nomes():
    """Nomes das conversas visiveis no WhatsApp Web (ou texto de erro)."""
    try:
        W = _wpp()
        with W.WA() as w:
            return [c["nome"] for c in json.loads(w.js(W.JS_LISTA))]
    except Exception as e:
        return _erro(e)


def _erro(e):
    msg = str(e)
    if "nao encontrada" in msg or "Connection refused" in msg or "10061" in msg:
        return "Não consegui falar com o WhatsApp: o Chrome do agente (monitor/start-chrome-debug.bat) precisa estar aberto com o WhatsApp Web logado."
    return f"Erro ao acessar o WhatsApp: {msg[:200]}"


def melhor_candidato(nome, cands):
    """Entre varios contatos parecidos, o que mais combina com TODAS as palavras ditas (tolera erro de transcricao: 'Altista' ~ 'Pereira').
    'Amigo Pereira Fresco' escolhe 'Amigo Pereira Fresco Da Silva' e nao 'Amigo Souza'. Empate: nome exato, senao o primeiro."""
    import difflib
    q = [p for p in _norm(contexto_contato(nome)).split() if len(p) > 1]
    def pontos(c):
        toks = _norm(c).split()
        total = 0.0
        for p in q:
            r = max((difflib.SequenceMatcher(None, p, t).ratio() for t in toks), default=0)
            total += r if r >= 0.75 else 0
        return total + (0.5 if _norm(c) == _norm(nome) else 0)
    return max(cands, key=pontos)


def _chave_busca(nome):
    """Parte do nome que a busca do WhatsApp entende (sem emoji/pontuacao): 'Manhinha 🏍' -> 'Manhinha'."""
    import re
    return re.split(r"[^\w\s.\-]", nome)[0].strip() or nome.strip()


@_com_pagina
def buscar_contatos(nome):
    """Procura NA BUSCA do WhatsApp (agenda inteira, nao so as ~20 conversas visiveis). Devolve lista de nomes (pode ser vazia).
    Tenta o nome todo e depois cada palavra, para 'manhinha' ou 'a Manhinha da moto' acharem 'Manhinha'."""
    import re
    base = contexto_contato(nome)
    termos = [_chave_busca(base)] + [p for p in re.findall(r"[\wÀ-ÿ]{3,}", base) if p.lower() not in ("minha", "meu", "para", "pra", "com", "dela", "dele")]
    vistos = []
    for t in dict.fromkeys(termos):
        try:
            W = _wpp()
            with W.WA() as w:
                w.js("var i=document.querySelector('#side input[aria-label^=\"Pesquisar\"]'); i&&i.focus()")
                w.cmd("Input.insertText", {"text": t})
                time.sleep(2)
                lista = json.loads(w.js(W.JS_LISTA))
                for k in ("Escape", "Escape"):
                    w.cmd("Input.dispatchKeyEvent", {"type": "keyDown", "key": k, "code": k, "windowsVirtualKeyCode": 27})
                nomes = [c["nome"] for c in lista]
        except Exception:
            continue
        achados = [n for n in nomes if _norm(t) in _norm(n)]
        if achados:
            return achados
    return vistos


def contexto_contato(nome):
    from . import contexto
    return contexto.contato(nome) or nome


@_com_pagina
def nao_lidas(max_chats=5, msgs=6):
    """Resumo das conversas com mensagens nao lidas."""
    try:
        W = _wpp()
        with W.WA() as w:
            lista = json.loads(w.js(W.JS_LISTA))
            if not lista:
                return "WhatsApp aberto, mas a lista de conversas veio vazia (talvez ainda carregando ou deslogado)."
            pend = [c for c in lista if c["nao_lidas"] > 0][:max_chats]
            if not pend:
                return "Nenhuma mensagem não lida no WhatsApp. ✅"
            saida = [f"{len(pend)} conversa(s) com não lidas:"]
            for c in pend:
                if not W.abrir(w, c["nome"]):
                    saida.append(f"• {c['nome']}: não consegui abrir")
                    continue
                time.sleep(1.5)
                d = json.loads(w.js(W.JS_MSGS % msgs))
                ms = d["msgs"]
                if ms and ms[-1]["d"] == "ELE":  # olhar marca como lida; guardamos que ainda falta responder
                    pendente_add(c["nome"])
                try:
                    resumo = W.resumir(c["nome"], ms) if ms else "(só mídia/áudio)"
                except Exception as e:
                    resumo = f"(IA local falhou: {str(e)[:80]})"
                extra = f" [{', '.join(x['t'] for x in d['midias'])}]" if d["midias"] else ""
                saida.append(f"• {c['nome']} ({c['nao_lidas']}): {resumo}{extra}")
            return "\n".join(saida)
    except Exception as e:
        return _erro(e)


@_com_pagina
def ler_conversa(nome, msgs=8):
    """Ultimas mensagens de uma conversa pelo nome (busca parcial entre as visiveis)."""
    try:
        W = _wpp()
        with W.WA() as w:
            lista = json.loads(w.js(W.JS_LISTA))
            achados = resolver_nome(nome, [c["nome"] for c in lista])
            alvo = next((c for c in lista if achados and c["nome"] == achados[0]), None)
            if not alvo:
                return f"Não achei conversa com '{nome}' entre as visíveis do WhatsApp."
            if not W.abrir(w, alvo["nome"]):
                return f"Não consegui abrir a conversa com {alvo['nome']}."
            time.sleep(1.5)
            ms = json.loads(w.js(W.JS_MSGS % msgs))["msgs"]
            if not ms:
                return f"{alvo['nome']}: sem mensagens de texto recentes."
            linhas = [f"Conversa com {alvo['nome']}:"]
            linhas += [f"{'Dono' if m['d'] == 'EU' else alvo['nome'].split()[0]}: {m['t'][:300]}" for m in ms if m["t"]]
            return "\n".join(linhas)
    except Exception as e:
        return _erro(e)


JS_TITULO_CHAT = r"""(function(){
  var h = document.querySelector('#main header');
  if (!h) return '';
  var s = h.querySelector('span[dir=auto]');
  return (s && s.innerText) || h.innerText.split('\n')[0] || '';
})()"""


def titulo_aberto(w):
    """Nome que aparece NO TOPO da conversa aberta agora (emoji vira imagem e nao entra no texto)."""
    try:
        return (w.js(JS_TITULO_CHAT) or "").strip()
    except Exception:
        return ""


def destino_confere(pedido, aberto):
    """TRAVA FINAL (14/10): a conversa aberta tem que ser a PEDIDA (apelido do dossie ou as palavras do nome). Em 07/10 (Souza) e 14/10
    (resumo para o Dono foi parar com a Parceira) a mensagem saiu para a pessoa errada porque so se conferia o que a busca escolheu."""
    if not aberto:
        return False
    if resolver_nome(pedido, [aberto]):                 # pelo apelido do dossie ('mae' -> 'mainha') ou pelo nome
        return True
    q = re.findall(r"\w+", _norm(pedido))              # ou as palavras ditas ('parceira' -> 'Parceira Lima', mesmo com o dossie desatualizado)
    return bool(q) and all(any(t.startswith(p) for t in re.findall(r"\w+", _norm(aberto))) for p in q)


def trava_destino(w, pedido):
    """None se pode enviar; senao o texto do bloqueio (nada e enviado)."""
    aberto = titulo_aberto(w)
    if destino_confere(pedido, aberto):
        return None
    return (f"🔒 Não enviei: abri a conversa '{aberto or '?'}', mas o pedido era para '{pedido}'. "
            "Nada foi enviado; diga o nome do contato como aparece no WhatsApp.")


# 16/11: gravacao de audio que ficou presa (Braniac caiu no meio) esconde a caixa de texto e trava todo envio. Cancela (nada e enviado).
JS_CANCELA_GRAVACAO = """(function(){var f=document.querySelector('footer'); if(!f||!f.querySelector('[aria-label="Pausar gravação"],[aria-label="Retomar gravação"]')) return false;
  var c=f.querySelector('[aria-label="Cancelar"]'); if(!c) return false; var r=c.getBoundingClientRect(); return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2})})()"""


def cancelar_gravacao_presa(w):
    try:
        pos = w.js(JS_CANCELA_GRAVACAO)
        if pos:
            p = json.loads(pos)   # clique de mouse de verdade: o .click() do JS o WhatsApp ignora
            for tipo in ("mousePressed", "mouseReleased"):
                w.cmd("Input.dispatchMouseEvent", {"type": tipo, "x": p["x"], "y": p["y"], "button": "left", "clickCount": 1})
            time.sleep(1.0)
            from .store import DATA
            with (DATA / "voz.log").open("a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | gravacao de audio presa cancelada (nada enviado)\n")
            return True
    except Exception:
        pass
    return False


def _digitar_e_enviar(w, texto):
    cancelar_gravacao_presa(w)
    if not w.js("(function(){var b=document.querySelector('footer [contenteditable=\"true\"], [contenteditable=\"true\"][data-tab=\"10\"]'); if(!b) return false; b.focus(); return true})()"):
        return False
    w.cmd("Input.insertText", {"text": texto})
    time.sleep(0.4)
    for tipo in ("keyDown", "keyUp"):
        w.cmd("Input.dispatchKeyEvent", {"type": tipo, "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13,
                                          "nativeVirtualKeyCode": 13, "text": "\r" if tipo == "keyDown" else ""})
    time.sleep(0.8)
    return True




def _arq_env():
    from .store import DATA
    return DATA / "enviados_recentes.json"


def _chave(t, n=60):
    return re.sub(r"\W+", "", (t or "").lower())[:n]


ECO_MIN = 25    # trecho minimo para casar no meio de um envio: 'ok', 'sim', 'pode fazer' do Dono nunca viram eco


def _lembrar_envio(texto):
    """06/11: o chat do Dono e o chat dele consigo mesmo: o que NOS enviamos la volta como se fosse fala dele. Guarda o inicio dos envios para o dono.py ignorar o eco."""
    try:
        a = _arq_env()
        try:
            lista = json.loads(a.read_text(encoding="utf-8"))
        except Exception:
            lista = []
        lista = (lista + [_chave(texto, 1500)])[-60:]     # 16/11: texto inteiro (ate 1500), para achar o eco de um trecho dele
        a.write_text(json.dumps(lista), encoding="utf-8")
    except Exception:
        pass


def foi_nosso(texto):
    """16/11: o resumo do funil ("📋 Resumo do Jarvis\\n\\n• ⚠️ A porta...") volta do chat lido a partir do 1o aviso; comparar so o inicio
    deixava passar e o Jarvis respondia ao proprio aviso. Agora: comeco igual, ou trecho de ECO_MIN+ letras dentro de algo que enviamos."""
    k = _chave(texto)
    try:
        lista = json.loads(_arq_env().read_text(encoding="utf-8"))
    except Exception:
        return False
    return bool(k) and any(s[:60] == k or (len(k) >= ECO_MIN and k in s) for s in lista)


_LIXO = re.compile(r'^(?:|<?none>?|null|undefined|n/?a|\{\s*"(?:tool|name)".*|n[aã]o consegui concluir isso agora\.?.*)$', re.I | re.S)


@_com_pagina
def enviar(nome, texto):
    """Envia texto a uma conversa EXISTENTE do WhatsApp (busca parcial pelo nome), conferindo o nome no topo do chat antes de enviar."""
    if _LIXO.match((texto or "").strip()):    # 06/11: nunca manda "<NONE>", vazio, JSON de ferramenta nem erro generico (o Dono recebeu "<NONE>" varias vezes)
        return "⛔ Mensagem barrada: resposta vazia ou defeituosa."
    if any(x in (nome or "").lower() for x in ("munzes", "munzés", "pai")):   # pai do Dono: so audio, nunca texto (10/11)
        return "⛔ Texto barrado: o pai do Dono só recebe áudio."
    _lembrar_envio(texto)
    from . import tratamento
    texto = tratamento.corrigir(texto)   # a Parceira e SEMPRE 'Parceira', em qualquer mensagem
    try:
        from . import wpp_direto                 # 27/10: sem Chrome quando o QR ja foi pareado e o nome e conhecido
        jid = wpp_direto.jid_de(nome)
        if jid and wpp_direto.conectado() and wpp_direto.enviar(jid, texto).get("ok"):
            return f"✅ Mensagem enviada para {nome}."
    except Exception:
        pass
    try:
        W = _wpp()
        with W.WA() as w:
            lista = json.loads(w.js(W.JS_LISTA))
            alvos = resolver_nome(nome, [c["nome"] for c in lista])
            if len(alvos) > 1:
                alvos = [melhor_candidato(nome, alvos)]      # nao pergunta: o que mais combina com o que foi dito
            if alvos:
                if not W.abrir(w, alvos[0]):
                    return f"Falhou ao abrir a conversa com {alvos[0]}. Nada foi enviado."
                time.sleep(1.0)
                bloqueio = trava_destino(w, nome)
                if bloqueio:
                    return bloqueio
                if not _digitar_e_enviar(w, texto):
                    return f"Não achei a caixa de mensagem da conversa com {alvos[0]}. Nada foi enviado."
                return f"✅ Mensagem enviada para {alvos[0]}."
        from . import wpp_arquivo                  # fora das conversas visiveis: acha pela busca do WhatsApp
        return wpp_arquivo.enviar_texto(_chave_busca(nome), texto, pedido=nome)
    except Exception as e:
        return _erro(e)



def reabrir_aba():
    """25/10: a aba do WhatsApp do Chrome do agente as vezes TRAVA (o CDP conecta mas nenhum comando responde, por horas). Fechar e abrir de novo cura
    e a sessao continua logada (fica no perfil). Devolve True se a aba nova respondeu."""
    import http.client, json as _j, time as _t, websocket
    try:
        c = http.client.HTTPConnection("127.0.0.1", 9222, timeout=5)
        c.request("GET", "/json")
        abas = [a for a in _j.loads(c.getresponse().read()) if a.get("type") == "page" and "web.whatsapp.com" in a.get("url", "")]
        c.close()
        for a in abas:
            c = http.client.HTTPConnection("127.0.0.1", 9222, timeout=5)
            c.request("GET", "/json/close/" + a["id"])
            c.getresponse().read()
            c.close()
        _t.sleep(2)
        c = http.client.HTTPConnection("127.0.0.1", 9222, timeout=10)
        c.request("PUT", "/json/new?https://web.whatsapp.com/")
        nova = _j.loads(c.getresponse().read())
        c.close()
        _t.sleep(15)
        ws = websocket.create_connection(nova["webSocketDebuggerUrl"], timeout=15, suppress_origin=True)
        ws.send(_j.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": "!!document.querySelector('#pane-side')", "returnByValue": True}}))
        ok = _j.loads(ws.recv()).get("result", {}).get("result", {}).get("value") is True
        ws.close()
        return ok
    except Exception:
        return False


_ULT_CURA = [0.0]


def curar_se_travada(erro, log=None):
    """Chamado pelas threads do vigia/dono quando o WhatsApp dá erro: se foi 'timed out' (aba travada), reabre a aba (no maximo 1x por 10 min)."""
    import time as _t
    if "timed out" not in repr(erro).lower() or _t.time() - _ULT_CURA[0] < 600:
        return False
    _ULT_CURA[0] = _t.time()
    ok = reabrir_aba()
    if log:
        log("aba do WhatsApp travada: reabrindo -> " + ("OK" if ok else "nao respondeu"))
    return ok
