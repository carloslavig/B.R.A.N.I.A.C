# -*- coding: utf-8 -*-
"""WhatsApp da pessoa pelo navegador do assistente (WhatsApp Web). A pessoa le o QR code uma vez, na propria tela; depois a janela some e so o
assistente usa. Funcoes: ver nao lidas, ler uma conversa, enviar mensagem. NAO verifica permissao aqui (isso e feito em pc_tools, que exige
'whatsapp.ler' / 'whatsapp.enviar'). O conteudo das conversas nunca vai para IA online: so volta para a propria pessoa."""
import json, re, time, unicodedata
from . import navegador
from .ias_web import _Aba

SITE = {"titulo": "WhatsApp", "dominio": "web.whatsapp.com", "url": "https://web.whatsapp.com/"}


class WhatsAppErro(RuntimeError):
    pass


JS_ESTADO = r"""JSON.stringify({logado: !!document.querySelector('#pane-side'),
  qr: !!document.querySelector('canvas[aria-label*="QR" i], [data-ref]'), carregando: !!document.querySelector('progress, [data-icon="lock"]')})"""
JS_LISTA = r"""(function(){var out=[];
  document.querySelectorAll('#pane-side [role="row"], #pane-side [role="listitem"]').forEach(function(r,i){
    var t=r.querySelector('span[title]'); if(!t) return;
    var b=r.querySelector('[aria-label*="não lida" i],[aria-label*="unread" i]'); var n=0;
    if(b){var m=(b.getAttribute('aria-label')||'').match(/\d+/); n=m?parseInt(m[0],10):1;}
    out.push({nome:t.getAttribute('title'), nao_lidas:n});});
  return JSON.stringify(out);})()"""
JS_RECT = r"""(function(nome){var rows=document.querySelectorAll('#pane-side [role="row"], #pane-side [role="listitem"]');
  for(var r of rows){var t=r.querySelector('span[title]'); if(t&&t.getAttribute('title')===nome){r.scrollIntoView({block:'nearest'});
  var b=r.getBoundingClientRect(); return JSON.stringify({x:b.x+b.width/2,y:b.y+b.height/2});}} return null;})(%s)"""
JS_MSGS = r"""(function(max){var msgs=[];
  document.querySelectorAll('[data-pre-plain-text]').forEach(function(el){
    var corpo=el.querySelector('span.selectable-text, span[dir]'); var txt=(corpo?corpo.innerText:el.innerText)||'';
    var row=el.closest('[class*="message-in"],[class*="message-out"]');
    msgs.push({de: row && row.className.indexOf('message-out')>=0 ? 'eu' : 'ele', texto: txt.trim()});});
  return JSON.stringify(msgs.slice(-max));})(%d)"""
JS_CAIXA = r"""(function(){var b=document.querySelector('footer [contenteditable="true"], [contenteditable="true"][data-tab="10"]'); if(!b) return false; b.focus(); return true})()"""


def _norm(x):
    return "".join(c for c in unicodedata.normalize("NFD", x.lower()) if unicodedata.category(c) != "Mn").strip()


def _aba():
    navegador.abrir_aba(SITE["url"])
    return _Aba(SITE)


def _preparar(a):
    a.cmd("Target.activateTarget", {"targetId": a.id})
    a.cmd("Page.bringToFront")
    time.sleep(0.6)


def estado():
    """{'logado': bool, 'qr': bool} ou None se a aba ainda nao abriu."""
    try:
        with navegador.LOCK, _Aba(SITE) as a:
            return json.loads(a.js(JS_ESTADO))
    except Exception:
        return None


def abrir_login():
    with navegador.LOCK:
        navegador.abrir_aba(SITE["url"])
        navegador.mostrar()


def _abrir_conversa(a, nome):
    rc = a.js(JS_RECT % json.dumps(nome))
    if not rc:
        return False
    rc = json.loads(rc)
    a.cmd("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": rc["x"], "y": rc["y"]})
    time.sleep(0.3)
    for tipo, bt in (("mousePressed", 1), ("mouseReleased", 0)):
        a.cmd("Input.dispatchMouseEvent", {"type": tipo, "x": rc["x"], "y": rc["y"], "button": "left", "buttons": bt, "clickCount": 1})
    time.sleep(1.5)
    base = (re.split(r"[^\w\s.\-]", nome)[0].strip() or nome)[:12]      # emoji vira imagem no cabecalho e nao aparece no texto
    return bool(a.js("[...document.querySelectorAll('header')].some(h=>h.innerText.indexOf(%s)>=0 && !h.closest('#side'))" % json.dumps(base)))


def resolver(nome, nomes):
    """Busca parcial sem acento/maiuscula. Devolve os candidatos (exato primeiro)."""
    alvo = _norm(nome)
    exatos = [n for n in nomes if _norm(n) == alvo]
    return exatos or [n for n in nomes if alvo and alvo in _norm(n)]


def _conectar():
    with navegador.LOCK:
        a = _aba()
        a.__enter__()
        try:
            est = json.loads(a.js(JS_ESTADO))
        except Exception:
            a.__exit__()
            raise
        if not est["logado"]:
            a.__exit__()
            raise WhatsAppErro("O WhatsApp ainda não está conectado. Leia o QR code no BRANIAC (Configurações › WhatsApp).")
        return a


def nao_lidas(max_chats=8):
    with navegador.LOCK:
        a = _conectar()
        try:
            _preparar(a)
            lista = json.loads(a.js(JS_LISTA))
        finally:
            a.__exit__()
    pend = [c for c in lista if c["nao_lidas"] > 0][:max_chats]
    return pend


def ler_conversa(nome, n=8):
    with navegador.LOCK:
        a = _conectar()
        try:
            _preparar(a)
            lista = json.loads(a.js(JS_LISTA))
            achados = resolver(nome, [c["nome"] for c in lista])
            if not achados:
                raise WhatsAppErro(f"Não achei conversa com '{nome}' entre as visíveis.")
            if len(achados) > 1:
                raise WhatsAppErro(f"Achei mais de uma conversa para '{nome}': {', '.join(achados[:5])}. Seja mais específico.")
            if not _abrir_conversa(a, achados[0]):
                raise WhatsAppErro(f"Não consegui abrir a conversa com {achados[0]}.")
            return achados[0], json.loads(a.js(JS_MSGS % n))
        finally:
            a.__exit__()


def enviar(nome, texto):
    texto = (texto or "").strip()
    if not texto:
        raise WhatsAppErro("mensagem vazia")
    with navegador.LOCK:
        a = _conectar()
        try:
            _preparar(a)
            lista = json.loads(a.js(JS_LISTA))
            achados = resolver(nome, [c["nome"] for c in lista])
            if not achados:
                raise WhatsAppErro(f"Não achei conversa com '{nome}'. Nada foi enviado.")
            if len(achados) > 1:
                raise WhatsAppErro(f"Achei mais de uma conversa para '{nome}': {', '.join(achados[:5])}. Nada foi enviado.")
            if not _abrir_conversa(a, achados[0]):
                raise WhatsAppErro(f"Não consegui abrir a conversa com {achados[0]}. Nada foi enviado.")
            if not a.js(JS_CAIXA):
                raise WhatsAppErro("caixa de mensagem não encontrada")
            a.cmd("Input.insertText", {"text": texto})
            time.sleep(0.4)
            a.enter()
            time.sleep(0.8)
            return achados[0]
        finally:
            a.__exit__()
