# -*- coding: utf-8 -*-
"""AIRBNB (anfitriao) pelo Chrome do agente (CDP, porta 9222): LER as conversas e RESPONDER hospedes.

Regras (CLAUDE.md, secao 0 e 3), valem para TUDO aqui:
- usa SO a aba do Airbnb que ja esta LOGADA; nunca faz login, nunca resolve captcha, nunca mexe em configuracao de conta;
- o anuncio "Apartamento completo - Perto da praia e de tudo" (Arleo AP, do Amiga) NUNCA e alterado: so se responde hospede e se tira duvida;
- PRE-APROVAR consulta / ACEITAR pedido so por AB.decidir_reserva, chamado pelo airbnb_vigia dentro das regras (ou a pedido do Dono/Mae/Parceira);
  recusar, valor, reembolso e qualquer decisao de dinheiro NAO sao feitos aqui: viram aviso/consulta ao Dono.
Uma aba por janela fica 'visivel': o acesso e feito sob whatsapp.LOCK (o mesmo do WhatsApp) e a aba do WhatsApp volta para a frente no fim.
"""
import itertools
import json
import re
import time
import http.client
import websocket

from . import whatsapp

HOST, PORTA = "127.0.0.1", 9222
URL_INBOX = "https://www.airbnb.com.br/hosting/messages"
ANUNCIO_PROTEGIDO = re.compile(r"apartamento\s+completo\s*-\s*perto\s+da\s+praia\s+e\s+de\s+tudo|arleo", re.I)
_ids = itertools.count(1)


class AirbnbIndisponivel(RuntimeError):
    pass


# ---------------------------------------------------------------- leitura (funcoes puras, testaveis sem navegador)

_LINHA = re.compile(r"^(?P<head>.*?)\.\s*A [uú]ltima mensagem (?P<quando>.+?) enviada [eé]:\s*(?P<prev>.*)$", re.S)


def _norm(t):
    return re.sub(r"\s+", " ", t or "").strip()


def parse_linha(thread_id, texto):
    """Texto de uma linha da caixa de entrada -> dict (ou None se nao der para entender).
    Ex.: 'Lidas. Consulta. 8 – 9 de out.. Quarto B · casa com piscina. Fabio. A última mensagem 22:48 enviada é: Você: Bem vindo'"""
    t = _norm(texto)
    m = _LINHA.match(t)
    if not m:
        return None
    partes = [p.strip() for p in re.split(r"\.\s+", m.group("head")) if p.strip()]
    if len(partes) < 3:
        return None
    status, meta, anuncio, hospede = partes[0], partes[1:-2], partes[-2], partes[-1]
    if re.search(r"atendimento ao cliente airbnb", partes[-1], re.I):      # conversa com o SUPORTE do Airbnb: o nome vem antes do rotulo
        anuncio, hospede = partes[-1], partes[-2]
        meta = partes[1:-2]
    prev = m.group("prev").strip().rstrip(".")
    if prev.startswith("Você:"):
        de, texto_prev = "voce", prev[5:].strip()
    else:
        mm = re.match(r"^([^:]{1,40}):\s*(.*)$", prev)
        if mm and _norm(mm.group(1)).split(" ")[0].lower() == hospede.split(" ")[0].lower():
            de, texto_prev = "hospede", mm.group(2)
        elif mm:
            de, texto_prev = "outro", mm.group(2)
        else:
            de, texto_prev = "outro", prev
    suporte = bool(re.search(r"atendimento ao cliente airbnb|airbnb\s+suporte", anuncio, re.I))
    return {"id": str(thread_id), "nao_lida": not status.lower().startswith("lida"), "meta": ". ".join(meta), "anuncio": anuncio,
            "hospede": hospede, "quando": m.group("quando").strip(), "ultima_de": de, "previa": texto_prev,
            "suporte_airbnb": suporte, "protegido": bool(ANUNCIO_PROTEGIDO.search(anuncio))}


_CAB = re.compile(r"^(?P<nome>[^·]{1,60}?)\s*·\s*(?P<papel>Anfitri[ãa]\(o\)|Coanfitri[ãa]\(o\)|Respons[áa]vel pela reserva|H[óo]spede[^\d]*?|Convidad[oa]|Co-?anfitri[ãa]\(o\))\s*(?P<resto>.*)$", re.S)
_HORA = re.compile(r"^(?P<h>\d{1,2}:\d{2})\s*(?P<resto>.*)$", re.S)
_LIDA = re.compile(r"\s*(?:Lida por [^\n]{1,40}|Entregue|Enviada)\s*$", re.I)


def limpar_texto(t):
    t = _norm(t)
    t = re.sub(r"^Respondendo a (?:você|[^ ]+)\s+", "", t)
    return _LIDA.sub("", t).strip()


SISTEMA = re.compile(r"^(Consulta de reserva|Pedido (?:de reserva|recusado|aceito|expirado|cancelado)|Reserva (?:confirmada|cancelada|alterada|solicitada|pendente)|Confirmado\b|Cancelad[oa]\b|Solicita[cç][ãa]o|Convite|Pr[eé]-aprova|Voc[eê] pr[eé]-aprovou|Altera[cç][ãa]o|Aviso)", re.I)


def parse_mensagens(itens):
    """itens = [{'txt': str, 'escuro': bool, 'y': int}] (y = posicao vertical; sem y, a ordem dada e a cronologica). Devolve em ordem cronologica:
    [{'de': 'hospede'|'anfitriao'|'voce'|'sistema', 'nome', 'hora', 'texto'}].
    Bolha ESCURA = enviada pela conta logada ('voce'); bolha clara = do outro lado. O cabecalho 'Nome · Papel HH:MM' vem na 1a mensagem de cada
    sequencia e define se o outro lado e o hospede ou o anfitriao (ex.: a Mae); as demais bolhas claras herdam o ultimo cabecalho."""
    out, papel, nome = [], None, ""
    if itens and all("y" in i for i in itens):
        itens = sorted(itens, key=lambda i: i["y"])        # ordem VISUAL (de cima para baixo) = cronologica, em qualquer conversa
    for it in itens:
        txt = _norm(it.get("txt", ""))
        if not txt:
            continue
        hora = ""
        m = _CAB.match(txt)
        if m:
            nome, papel = m.group("nome").strip(), m.group("papel").strip()
            resto = m.group("resto")
            mh = _HORA.match(resto)
            hora, resto = (mh.group("h"), mh.group("resto")) if mh else ("", resto)
        else:
            mh = _HORA.match(txt)
            hora, resto = (mh.group("h"), mh.group("resto")) if mh else ("", txt)
        if SISTEMA.match(txt if not m else _norm(resto)):
            de = "sistema"
        elif it.get("escuro"):
            de = "voce"
        elif papel and re.match(r"(Co)?anfitri", papel, re.I):
            de = "anfitriao"
        else:
            de = "hospede"
        texto = limpar_texto(resto if de != "sistema" else txt)
        if texto:
            out.append({"de": de, "nome": "Você" if de == "voce" else (nome if de != "sistema" else "Airbnb"), "hora": hora, "texto": texto})
    return out


def eh_do_hospede(msg):
    return msg["de"] == "hospede"


def pendente_de_resposta(linha):
    """A conversa espera resposta NOSSA? (ultima mensagem e do hospede, nao e suporte do Airbnb)."""
    return bool(linha) and linha["ultima_de"] == "hospede" and not linha["suporte_airbnb"]


# ---------------------------------------------------------------- navegador

JS_LINHAS = r"""JSON.stringify([...document.querySelectorAll('[data-testid^=inbox_list_]')].slice(0,%d).map(r=>({id:r.getAttribute('data-testid').slice(11),t:(r.innerText||'')})))"""
JS_MSGS = r"""(()=>{const l=document.querySelector('[data-testid=message-list]'); if(!l) return null;
 const its=[...l.querySelectorAll('[data-testid^=MessageOuter]')].slice(0,%d).map(e=>{
   const bub=[...e.querySelectorAll('div')].find(d=>getComputedStyle(d).backgroundColor!=='rgba(0, 0, 0, 0)'&&d.getBoundingClientRect().width>20);
   let escuro=false; if(bub){const m=(getComputedStyle(bub).backgroundColor.match(/\d+/g)||[255,255,255]).map(Number); escuro=(m[0]*0.299+m[1]*0.587+m[2]*0.114)<110;}
   return {txt:e.innerText||'',escuro:escuro,y:Math.round(e.getBoundingClientRect().top)};});
 const h=document.querySelector('[data-testid=thread-header-title]');
 return JSON.stringify({header:(h&&h.innerText||'').trim(),itens:its});})()"""
JS_ENVIAR_FOCO = r"""(()=>{const e=document.querySelector('#message_input')||document.querySelector('[data-testid=messaging-composebar] [role=textbox]'); if(!e) return false; e.focus(); return true})()"""
JS_CONTA = r"""document.querySelectorAll('[data-testid=message-list] [data-testid^=MessageOuter]').length"""
JS_CAMPO_TEXTO = r"""(()=>{const e=document.querySelector('#message_input')||document.querySelector('[data-testid=messaging-composebar] [role=textbox]'); return e?(e.innerText||'').trim():null})()"""
JS_CLICAR_ENVIAR = r"""(()=>{const b=document.querySelector('[data-testid=messaging_compose_bar_send_button]'); if(!b||b.disabled) return false; b.click(); return true})()"""
JS_LOGADO = r"""JSON.stringify({u:location.href,login:!!document.querySelector('input[type=password],[data-testid=auth-modal],form[action*=login]')||/\/login|\/signup/.test(location.pathname),vis:document.visibilityState})"""


class AB:
    """Sessao CDP na aba do Airbnb. Use: with AB() as ab: ab.conversas() / ab.ler(id) / ab.enviar(id, texto)."""

    def __init__(self, porta=PORTA, host=HOST):
        self.porta, self.host = porta, host
        self.ws = None

    # --- conexao
    def _abas(self):
        try:
            c = http.client.HTTPConnection(self.host, self.porta, timeout=5)
            c.request("GET", "/json")
            r = json.loads(c.getresponse().read())
            c.close()
            return r
        except OSError as e:
            raise AirbnbIndisponivel("Chrome do agente fechado (porta 9222)") from e

    def __enter__(self):
        whatsapp.LOCK.acquire()
        try:
            abas = [a for a in self._abas() if a.get("type") == "page"]
            aba = next((a for a in abas if "airbnb.com" in a.get("url", "")), None)
            if not aba:
                raise AirbnbIndisponivel("Nao ha aba do Airbnb aberta no Chrome do agente (abra airbnb.com.br/hosting e entre uma vez)")
            self.aba_id = aba["id"]
            self.wpp_id = next((a["id"] for a in abas if "web.whatsapp.com" in a.get("url", "")), None)
            self.ws = websocket.create_connection(aba["webSocketDebuggerUrl"], timeout=30, suppress_origin=True, max_size=32 * 1024 * 1024)
            self._frente()
            lg = json.loads(self.js(JS_LOGADO) or "{}")
            if lg.get("login"):
                raise AirbnbIndisponivel("O Airbnb nao esta logado no Chrome do agente (entre manualmente uma vez; o Braniac nunca faz login)")
            return self
        except BaseException:
            self._fechar()
            whatsapp.LOCK.release()
            raise

    def __exit__(self, *a):
        self._fechar()
        whatsapp.LOCK.release()

    def _fechar(self):
        try:
            if self.ws and getattr(self, "wpp_id", None):   # devolve a frente ao WhatsApp (senao o Jarvis para de atender)
                self.cmd("Target.activateTarget", {"targetId": self.wpp_id})
        except Exception:
            pass
        try:
            if self.ws:
                self.ws.close()
        except Exception:
            pass
        self.ws = None

    def cmd(self, metodo, params=None):
        mid = next(_ids)
        self.ws.send(json.dumps({"id": mid, "method": metodo, "params": params or {}}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == mid:
                if "error" in m:
                    raise RuntimeError(f"{metodo}: {m['error']}")
                return m.get("result", {})

    def js(self, expr):
        r = self.cmd("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True})
        if r.get("exceptionDetails"):
            raise RuntimeError(str(r["exceptionDetails"])[:300])
        return r.get("result", {}).get("value")

    def _frente(self):
        try:
            self.cmd("Target.activateTarget", {"targetId": self.aba_id})
            self.cmd("Page.bringToFront")
            j = self.cmd("Browser.getWindowForTarget")
            if (j.get("bounds") or {}).get("windowState") == "minimized":
                self.cmd("Browser.setWindowBounds", {"windowId": j["windowId"], "bounds": {"windowState": "normal"}})
                self.cmd("Browser.setWindowBounds", {"windowId": j["windowId"], "bounds": {"left": -2600, "top": 40, "width": 1280, "height": 900}})
        except Exception:
            pass
        for _ in range(12):                      # espera a pagina ficar visivel e desenhar
            if self.js("document.visibilityState") == "visible":
                break
            time.sleep(0.4)
        time.sleep(0.8)

    def _esperar(self, expr, tempo=12):
        for _ in range(int(tempo / 0.5)):
            try:
                if self.js(expr):
                    return True
            except RuntimeError:
                pass
            time.sleep(0.5)
        return False

    def ir(self, url):
        self.cmd("Page.navigate", {"url": url})
        time.sleep(1.2)
        self._esperar("document.readyState==='complete'", 15)
        self._frente()

    # --- operacoes
    def conversas(self, max_n=20):
        """Linhas da caixa de entrada (mais recentes primeiro), ja interpretadas."""
        if "/hosting/messages" not in (self.js("location.pathname") or ""):
            self.ir(URL_INBOX)
        self._esperar("!!document.querySelector('[data-testid^=inbox_list_]')", 15)
        brutas = json.loads(self.js(JS_LINHAS % max_n) or "[]")
        return [l for l in (parse_linha(b["id"], b["t"]) for b in brutas) if l]

    def abrir(self, thread_id):
        thread_id = re.sub(r"\D", "", str(thread_id))
        if not thread_id:
            raise ValueError("id de conversa invalido")
        if not (self.js("location.pathname") or "").rstrip("/").endswith("/" + thread_id):
            self.ir(f"{URL_INBOX}/{thread_id}")
        return self._esperar("!!document.querySelector('[data-testid=message-list] [data-testid^=MessageOuter]')", 15)

    def ler(self, thread_id, max_msgs=25):
        """Mensagens da conversa em ordem cronologica: {'hospede', 'mensagens': [{'de','nome','hora','texto'}]}. Tenta de novo se a pagina ainda nao desenhou."""
        d = {}
        for tentativa in range(3):
            if not self.abrir(thread_id):
                time.sleep(1.5)
                continue
            self._frente()
            d = json.loads(self.js(JS_MSGS % max_msgs) or "{}")
            if d.get("itens"):
                break
            time.sleep(1.5)
        return {"hospede": _norm(d.get("header", "")).split(" ")[0] if d.get("header") else "", "mensagens": parse_mensagens(d.get("itens", []))}

    def enviar(self, thread_id, texto):
        """Escreve e envia `texto` na conversa. Devolve (ok, motivo). Nao envia vazio, longo demais nem para conversa fora da lista."""
        texto = _norm(texto)
        if not texto:
            return False, "texto vazio"
        if len(texto) > 900:
            return False, "texto longo demais (>900)"
        if not self.abrir(thread_id):
            return False, "conversa nao abriu"
        antes = int(self.js(JS_CONTA) or 0)
        if not self.js(JS_ENVIAR_FOCO):
            return False, "caixa de mensagem nao encontrada"
        self.cmd("Input.insertText", {"text": texto})
        time.sleep(0.6)
        digitado = self.js(JS_CAMPO_TEXTO) or ""
        if _norm(digitado)[:30] != texto[:30]:
            self.js("(()=>{const e=document.querySelector('#message_input'); if(e){e.focus(); document.execCommand('selectAll'); document.execCommand('delete')}})()")
            return False, "o texto nao entrou na caixa (nada foi enviado)"
        if not self.js(JS_CLICAR_ENVIAR):
            return False, "botao Enviar indisponivel"
        for _ in range(16):
            time.sleep(0.5)
            if int(self.js(JS_CONTA) or 0) > antes:
                return True, ""
        return False, "a mensagem nao apareceu na conversa (confira no Airbnb)"


# ---------------------------------------------------------------- reservas e respostas rapidas (funcoes puras)

QUARTO = re.compile(r"^\s*(quarto|su[ií]te)\b", re.I)          # Quarto A, Quarto B, Suite Suite C (casa com quartos)
_MES = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6, "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12}


def eh_quarto(anuncio):
    return bool(QUARTO.match(anuncio or ""))


def parse_noites(meta, ano=2026):
    """'8 – 9 de out.' -> 1 ; '31 de dez. de 2026 – 3 de jan. de 2027' -> 3 ; nao entendeu -> None."""
    from datetime import date
    m = re.search(r"(\d{1,2})(?:\s+de\s+([a-zç]{3})\.?)?(?:\s+de\s+(\d{4}))?\s*[–-]\s*(\d{1,2})\s+de\s+([a-zç]{3})\.?(?:\s+de\s+(\d{4}))?", (meta or "").lower())
    if not m:
        return None
    d1, m1, a1, d2, m2, a2 = m.groups()
    m2n = _MES.get(m2)
    m1n = _MES.get(m1) if m1 else m2n
    if not m2n or not m1n:
        return None
    try:
        fim = date(int(a2 or ano), m2n, int(d2))
        ini = date(int(a1 or (int(a2) if a2 else ano) - (1 if m1n > m2n else 0)), m1n, int(d1))
    except ValueError:
        return None
    n = (fim - ini).days
    return n if n > 0 else None


def parse_hospedes(texto):
    m = re.search(r"(\d+)\s+h[oó]spedes?", texto or "")
    return int(m.group(1)) if m else None


_RESOLVIDO = re.compile(r"recusad|aceit|expirad|cancelad|confirmad|convite enviado|pr[eé]-aprovad", re.I)


def estado_reserva(cartoes):
    """Olha o ULTIMO cartao de status da conversa -> 'consulta' (pode pre-aprovar), 'pedido' (pode aceitar) ou None (nada pendente)."""
    ultimo = None
    for c in cartoes:
        t = _norm(c)
        if re.match(r"(Consulta de reserva|Pedido de reserva|Reserva pendente|Convite enviado|Pedido recusado|Pedido aceito|Pedido cancelado|Confirmado|Alteração solicitada|Reserva cancelada)", t):
            ultimo = t
    if not ultimo or "%{" in ultimo:
        return None
    if re.match(r"Consulta de reserva", ultimo) and re.search(r"Você tem até", ultimo):
        return "consulta"
    if re.match(r"(Pedido de reserva|Reserva pendente)", ultimo) and re.search(r"Você tem até", ultimo):
        return "pedido"
    return None


def prazo_vencido(cartao, agora=None):
    """'Você tem até 8 de out. 21:46 AMT para responder' -> True se esse prazo ja passou (o cartao fica na conversa depois de expirar)."""
    from datetime import datetime
    agora = agora or datetime.now()
    m = re.search(r"tem até (\d{1,2}) de ([a-zç]{3})\.?(?:\s+(\d{1,2}):(\d{2}))?", cartao or "", re.I)
    if not m or not _MES.get(m.group(2).lower()):
        return False
    try:
        fim = datetime(agora.year, _MES[m.group(2).lower()], int(m.group(1)), int(m.group(3) or 23), int(m.group(4) or 59))
    except ValueError:
        return False
    return fim < agora


JS_CLICAR_TEXTO = r"""((rot,sel)=>{const els=[...document.querySelectorAll(sel)].filter(e=>e.offsetParent!==null||true);
  const e=els.find(x=>new RegExp(rot,'i').test((x.innerText||'').trim())); if(!e) return false; e.click(); return true})(%s,%s)"""
JS_DIALOGO = r"""(()=>{const d=[...document.querySelectorAll('[role=dialog]')].pop(); return d?d.innerText:''})()"""
JS_RESPOSTAS_RAPIDAS = r"""(()=>{const d=[...document.querySelectorAll('[role=dialog]')].find(x=>/Respostas rápidas/.test(x.innerText)); return d?d.innerText:null})()"""


def parse_respostas_rapidas(texto):
    """Texto do painel 'Respostas rapidas' (titulo e corpo em linhas alternadas) -> {titulo: corpo}."""
    linhas = [l.strip() for l in (texto or "").split(chr(10)) if l.strip()]
    if linhas and linhas[0].lower().startswith("respostas r"):
        linhas = linhas[1:]
    out = {}
    i = 0
    while i + 1 < len(linhas):
        if linhas[i].lower().startswith("obtenha mais respostas"):
            break
        out[linhas[i].lower()] = linhas[i + 1]
        i += 2
    return out


def _ab_modelos(self, thread_id):
    """{titulo_minusculo: texto} das respostas rapidas salvas no Airbnb, ja com o nome do hospede DESTA conversa."""
    if not self.abrir(thread_id):
        return {}
    texto = None
    for _ in range(4):                                   # o botao pode ser clicado antes de a pagina 'ligar': tenta de novo
        self.js("(()=>{const b=document.querySelector('[data-testid=compose-bar-button-messaging__open_quick_replies]'); if(b) b.click()})()")
        time.sleep(2.5)
        texto = self.js(JS_RESPOSTAS_RAPIDAS)
        if texto:
            break
    self.js("(()=>{const b=[...document.querySelectorAll('[role=dialog] button')].find(x=>/Fechar/.test(x.getAttribute('aria-label')||x.innerText)); if(b) b.click()})()")
    time.sleep(0.5)
    return parse_respostas_rapidas(texto)


def _ab_resposta_rapida(self, thread_id, titulo):
    return _ab_modelos(self, thread_id).get(titulo.lower())


def _ab_decidir_reserva(self, thread_id, acao):
    """acao 'preaprovar' (consulta) ou 'aceitar' (pedido). Devolve (ok, motivo). Confere o cartao na conversa antes e depois."""
    rot, conf, marca = {"preaprovar": (r"^Pré-aprovar$", r"^Sim, pré-aprovar", r"Convite enviado|pr[eé]-aprova"),
                        "aceitar": (r"^Aceitar( pedido)?$", r"^(Sim, aceitar|Aceitar|Confirmar)", r"Pedido aceito|Confirmado")}.get(acao, (None, None, None))
    if not rot:
        return False, "acao desconhecida"
    antes = len(re.findall(marca, json.dumps([m["texto"] for m in self.ler(thread_id, 40)["mensagens"] if m["de"] == "sistema"]), re.I))
    self.ir(f"https://www.airbnb.com.br/hosting/reservations/thread/{re.sub(chr(92) + 'D', '', str(thread_id))}?isBessieThread=true")
    if not self._esperar("!![...document.querySelectorAll('a')].find(x=>/^(Pré-aprovar|Aceitar)/.test((x.innerText||'').trim()))", 15):
        return False, "nao achei o botao (a reserva pode ja ter sido tratada)"
    if not self.js(JS_CLICAR_TEXTO % (json.dumps(rot), json.dumps("a,button"))):
        return False, f"botao {acao} nao encontrado"
    time.sleep(2)
    dlg = self.js(JS_DIALOGO) or ""
    if not re.search(r"pré-aprovar|aceitar|aceit", dlg, re.I):
        return False, "a janela de confirmacao nao apareceu como esperado (nada foi confirmado)"
    if not self.js(JS_CLICAR_TEXTO % (json.dumps(conf), json.dumps("[role=dialog] button"))):
        return False, "botao de confirmar nao encontrado (nada foi confirmado)"
    time.sleep(3)
    depois = len(re.findall(marca, json.dumps([m["texto"] for m in self.ler(thread_id, 40)["mensagens"] if m["de"] == "sistema"]), re.I))
    return (True, "") if depois > antes else (False, "cliquei em confirmar mas nao vi o resultado na conversa; confira no Airbnb")


AB.modelos = _ab_modelos
AB.resposta_rapida = _ab_resposta_rapida
AB.decidir_reserva = _ab_decidir_reserva
