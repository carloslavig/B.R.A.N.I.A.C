# -*- coding: utf-8 -*-
"""
IA local do Claudinho: le o WhatsApp Web (Chrome de automacao) e resume com
Ollama, sem gastar tokens do Claude.

Uso:
  python wpp_local.py ler [--max-chats 8] [--msgs 8]     -> resumo das conversas nao lidas
  python wpp_local.py enviar "<nome do contato>" "<texto>" -> envia uma mensagem
Regras: so le e envia; nunca decide nada sozinha. Quem escreve as respostas e o Claude.
"""
import sys, json, time, argparse, urllib.request
from cdpwa import WA

OLLAMA = "http://127.0.0.1:11434/api/generate"
MODELO = "qwen2.5:3b"

JS_LISTA = r"""
(function(){
  var out=[];
  document.querySelectorAll('#pane-side [role="row"], #pane-side [role="listitem"]').forEach(function(r,i){
    var t=r.querySelector('span[title]'); if(!t) return;
    var badge=r.querySelector('[aria-label*="não lida" i],[aria-label*="unread" i]');
    var n=0; if(badge){ var m=(badge.getAttribute('aria-label')||'').match(/\d+/); n=m?parseInt(m[0],10):1; }
    out.push({i:i,nome:t.getAttribute('title'),nao_lidas:n});
  });
  return JSON.stringify(out);
})()
"""

JS_ABRIR = r"""
(function(nome){
  var rows=document.querySelectorAll('#pane-side [role="row"], #pane-side [role="listitem"]');
  for (var r of rows){ var t=r.querySelector('span[title]');
    if(t && t.getAttribute('title')===nome){ r.dispatchEvent(new MouseEvent('mousedown',{bubbles:true})); r.click(); return true; } }
  return false;
})(%s)
"""

JS_MSGS = r"""
(function(max){
  var msgs=[];
  document.querySelectorAll('[data-pre-plain-text]').forEach(function(el){
    var cab=el.getAttribute('data-pre-plain-text')||'';
    var corpo=el.querySelector('span.selectable-text, span[dir]');
    var txt=(corpo?corpo.innerText:el.innerText)||'';
    var row=el.closest('[class*="message-in"],[class*="message-out"]');
    var dir=row && row.className.indexOf('message-out')>=0 ? 'EU' : 'ELE';
    if (/\]\s*Dono\s*:/i.test(cab)) dir='EU';  // layout novo: so o cabecalho indica o autor
    msgs.push({d:dir,c:cab.replace(/\s+/g,' ').trim(),t:txt.trim()});
  });
  // midia sem texto (audio/foto) aparece como linhas separadas
  var extras=[];
  var linhas=[...document.querySelectorAll('#main [role="row"], [role="application"] [role="row"]')];   // o layout novo do WhatsApp Web nao tem mais role=application
  var ultimaNossa=-1;   // indice da ultima linha enviada por NOS (texto ou arquivo): documento antes disso ja foi tratado
  // nossa = message-out, rabinho de saida ou icone de status (so mensagem nossa tem tique); audio nosso em sequencia nao tem rabinho (24/10: a mae recebeu 4 respostas)
  var nossa=function(r){ return !!(r.className.indexOf('message-out')>=0||r.querySelector('[class*="message-out"],[data-icon="tail-out"],[data-icon^="msg-check"],[data-icon^="msg-dblcheck"],[data-icon^="msg-time"],[data-icon*="status-dblcheck"],[data-icon*="status-check"]') || [...r.querySelectorAll('[aria-label]')].some(function(e){return /^\s*(Entregue|Lida|Enviada|Pendente|Delivered|Read|Sent|Pending)\s*$|^Você:$/i.test(e.getAttribute('aria-label'));})); };
  linhas.forEach(function(r,i){ if(nossa(r)) ultimaNossa=i; });
  linhas.forEach(function(r,i){
    var doc=r.querySelector('[data-icon^="document-"]');    // documento (html, pdf, docx, zip...): ha o icone document-XXX-icon e o botao 'Baixar "nome"'
    if(doc && !r.querySelector('[data-icon="tail-out"]')){
      var b=r.querySelector('[title^="Baixar"]'), m=b && (b.getAttribute('title')||'').match(/"(.+)"/);
      if(m && i>ultimaNossa) extras.push({d:'ELE',c:'',t:'[DOC:'+m[1]+']'});
      return;
    }
    if(r.querySelector('[data-pre-plain-text]')) return;
    var tipo='';
    if(r.querySelector('audio,[aria-label*="mensagem de voz" i],[data-icon*="audio" i],[data-icon*="ptt" i]')) tipo='[AUDIO]';
    else if(r.querySelector('img[src^="blob"]')) tipo='[IMAGEM]';
    if(tipo && i>ultimaNossa) extras.push({d:nossa(r)?'EU':'ELE',c:'',t:tipo});   // midia antes da nossa ultima resposta ja foi respondida
  });
  return JSON.stringify({msgs:msgs.slice(-max), midias:extras.slice(-3)});
})(%d)
"""

JS_RECT = r"""(function(nome){var rows=document.querySelectorAll('#pane-side [role="row"], #pane-side [role="listitem"]');
 for(var r of rows){var t=r.querySelector('span[title]'); if(t&&t.getAttribute('title')===nome){r.scrollIntoView({block:'nearest'}); var b=r.getBoundingClientRect(); return JSON.stringify({x:b.x+b.width/2,y:b.y+b.height/2});}} return null;})(%s)"""

def abrir(w, nome):
    rc = w.js(JS_RECT % json.dumps(nome))
    if not rc: return False
    rc = json.loads(rc)
    w.cmd("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": rc["x"], "y": rc["y"]}); time.sleep(0.3)
    w.cmd("Input.dispatchMouseEvent", {"type": "mousePressed", "x": rc["x"], "y": rc["y"], "button": "left", "buttons": 1, "clickCount": 1})
    w.cmd("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": rc["x"], "y": rc["y"], "button": "left", "buttons": 0, "clickCount": 1})
    time.sleep(1.5)
    import re as _re
    base = _re.split(r'[^\w\s.\-]', nome)[0].strip() or nome   # emoji vira <img> no cabecalho e nao aparece no innerText
    chave = json.dumps(base[:12])
    return bool(w.js("[...document.querySelectorAll('header')].some(h=>h.innerText.indexOf(%s)>=0 && h.closest('#pane-side')==null && !h.closest('#side'))" % chave))

def ollama(prompt, timeout=120):
    body = json.dumps({"model": MODELO, "prompt": prompt, "stream": False,
                       "options": {"temperature": 0.2, "num_ctx": 4096}}).encode()
    req = urllib.request.Request(OLLAMA, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["response"].strip()

def resumir(nome, msgs):
    dialogo = "\n".join(f"{'CONTATO' if m['d']=='ELE' else 'DONO'}: {m['t'][:300]}" for m in msgs if m["t"])
    prompt = (
        "Tarefa: resumir uma conversa de WhatsApp em portugues do Brasil, em ate 2 frases, "
        "na terceira pessoa. NAO responda a conversa e NAO continue o dialogo.\n"
        "Diga o que o CONTATO quer/perguntou e se esta pendente de resposta do DONO. Nao invente.\n\n"
        f"Conversa com {nome}:\n{dialogo}\n\n"
        f"Resumo (comece com '{nome} '):"
    )
    return ollama(prompt)

def cmd_ler(a):
    with WA() as w:
        lista = json.loads(w.js(JS_LISTA))
        if not lista:
            print("ERRO: lista de conversas vazia (WhatsApp nao logado ou ainda carregando)."); return 1
        naolidas = [c for c in lista if c["nao_lidas"] > 0][: a.max_chats]
        print(f"Conversas com nao lidas: {len(naolidas)} (de {len(lista)} visiveis)\n")
        for c in naolidas:
            if not abrir(w, c["nome"]):
                print(f"## {c['nome']}: nao consegui abrir\n"); continue
            time.sleep(1.5)
            d = json.loads(w.js(JS_MSGS % a.msgs))
            msgs = d["msgs"]
            ult = [m for m in msgs if m["d"] == "ELE"][-3:]
            try: resumo = resumir(c["nome"], msgs) if msgs else "(sem texto; so midia)"
            except Exception as e: resumo = f"(IA local falhou: {e})"
            print(f"## {c['nome']} - {c['nao_lidas']} nao lida(s)")
            print(f"Resumo: {resumo}")
            for m in ult: print(f"  ELE: {m['t'][:200]}")
            if d["midias"]: print("  Midias recentes: " + ", ".join(x["t"] for x in d["midias"]))
            print()
    return 0

def cmd_enviar(a):
    with WA() as w:
        if not abrir(w, a.nome):
            print(f"ERRO: conversa '{a.nome}' nao encontrada na lista visivel."); return 1
        time.sleep(1.5)
        ok = w.js("(function(){var b=document.querySelector('footer [contenteditable=\"true\"], [contenteditable=\"true\"][data-tab=\"10\"]'); if(!b) return false; b.focus(); return true})()")
        if not ok: print("ERRO: caixa de mensagem nao encontrada"); return 1
        w.cmd("Input.insertText", {"text": a.texto})
        time.sleep(0.4)
        for tipo in ("keyDown", "keyUp"):
            w.cmd("Input.dispatchKeyEvent", {"type": tipo, "key": "Enter", "code": "Enter",
                                              "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13, "text": "\r" if tipo=="keyDown" else ""})
        time.sleep(0.8)
        print(f"Enviado para '{a.nome}'.")
    return 0

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(); sp = p.add_subparsers(dest="c", required=True)
    l = sp.add_parser("ler"); l.add_argument("--max-chats", type=int, default=8); l.add_argument("--msgs", type=int, default=8); l.set_defaults(f=cmd_ler)
    e = sp.add_parser("enviar"); e.add_argument("nome"); e.add_argument("texto"); e.set_defaults(f=cmd_enviar)
    a = p.parse_args(); sys.exit(a.f(a))
