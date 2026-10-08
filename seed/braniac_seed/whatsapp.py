# -*- coding: utf-8 -*-
"""WhatsApp da pessoa pelo navegador do assistente (WhatsApp Web). A pessoa le o QR code uma vez, na propria tela; depois a janela some e so o
assistente usa. Funcoes: ver nao lidas, ler uma conversa, enviar mensagem. NAO verifica permissao aqui (isso e feito em pc_tools, que exige
'whatsapp.ler' / 'whatsapp.enviar'). O conteudo das conversas nunca vai para IA online: so volta para a propria pessoa."""
import json, os, re, tempfile, time, unicodedata, zipfile
from pathlib import Path
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


def melhor(nome, candidatos):
    """Entre varios contatos parecidos, o que combina com TODAS as palavras ditas ('Matheus Autista' escolhe 'Matheus Autista Silva', nao 'Matheus Heyah')."""
    import difflib
    q = [p for p in _norm(nome).split() if len(p) > 1]

    def pontos(c):
        toks = _norm(c).split()
        return sum((r if r >= 0.75 else 0) for r in (max((difflib.SequenceMatcher(None, p, t).ratio() for t in toks), default=0) for p in q)) + (0.5 if _norm(c) == _norm(nome) else 0)
    return max(candidatos, key=pontos)


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


def _achar_conversa(a, nome, achados):
    """Abre a conversa certa SEM ficar perguntando: o contato visivel que mais combina; se nao ha nenhum, procura na busca do WhatsApp (agenda inteira)."""
    if achados:
        alvo = melhor(nome, achados) if len(achados) > 1 else achados[0]
        if _abrir_conversa(a, alvo):
            return alvo
    a.js("var i=document.querySelector('#side input[aria-label^=\"Pesquisar\"], #side [contenteditable=true]'); i&&i.focus()")
    a.cmd("Input.insertText", {"text": (re.split(r"[^\w\s.\-]", nome)[0].strip() or nome)})
    time.sleep(2)
    nomes = [c["nome"] for c in json.loads(a.js(JS_LISTA))]
    cand = resolver(nome, nomes)
    if not cand:
        raise WhatsAppErro(f"Não achei '{nome}' nem na agenda do WhatsApp. Nada foi enviado. Se me disser o número, eu tento por ele.")
    alvo = melhor(nome, cand) if len(cand) > 1 else cand[0]
    if not _abrir_conversa(a, alvo):
        raise WhatsAppErro(f"Não consegui abrir a conversa com {alvo}. Nada foi enviado.")
    return alvo


# ---------- arquivos ----------
BLOQUEADAS = {".exe", ".bat", ".cmd", ".msi", ".scr", ".com", ".vbs", ".js", ".jar", ".ps1", ".dll", ".lnk"}     # o WhatsApp bloqueia: vao dentro de um .zip
BLOQUEIO_CAMINHO = (".env", ".pem", ".key", ".pfx", ".kdbx", "id_rsa", ".ssh", "cookies", "login data", "appdata", "braniac-dados", "\\windows\\", "program files", "programdata")
LIMITE_MB = 100
JS_ITEM_DOCUMENTO = r"""(function(){var els=[...document.querySelectorAll('[role=menuitem], li[role=button], [data-animate-dropdown-item], li, button')];
  var alvo=els.find(e=>/^documento$|^document$/i.test((e.innerText||'').trim()) && e.getBoundingClientRect().width>0); if(!alvo) return null;
  var r=alvo.getBoundingClientRect(); return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2});})()"""
JS_ICONE = r"""(function(ic){var i=[...document.querySelectorAll('[data-icon="'+ic+'"]')].find(e=>e.getBoundingClientRect().width>0); if(!i) return null;
  var b=i.closest('button,[role=button]')||i; var r=b.getBoundingClientRect(); return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2});})(%s)"""
JS_ANEXAR = r"""(function(){var b=[...document.querySelectorAll('footer button, footer [role=button]')].find(e=>/anexar|attach/i.test(e.getAttribute('aria-label')||'')&&e.getBoundingClientRect().width>0);
  if(!b) return null; var r=b.getBoundingClientRect(); return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2});})()"""
JS_LEGENDA = r"""(function(){var c=[...document.querySelectorAll('[contenteditable=true]')].find(e=>!e.closest('#side')&&!e.closest('footer')&&e.getBoundingClientRect().width>0); if(!c) return false; c.focus(); return true})()"""


def _clicar(a, x, y):
    a.cmd("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
    time.sleep(0.2)
    for tipo, bt in (("mousePressed", 1), ("mouseReleased", 0)):
        a.cmd("Input.dispatchMouseEvent", {"type": tipo, "x": x, "y": y, "button": "left", "buttons": bt, "clickCount": 1})


def preparar_arquivo(caminho):
    """Valida o caminho (nada de chaves/cookies/pastas do sistema/dados do proprio BRANIAC), o tamanho, e zipa executaveis. Devolve o caminho a enviar."""
    p = Path(os.path.expandvars(os.path.expanduser(str(caminho).strip().strip('"'))))
    if not p.is_file():
        raise WhatsAppErro(f"Arquivo não encontrado: {caminho}")
    baixo = str(p.resolve()).lower() + "\\"
    if any(b in baixo for b in BLOQUEIO_CAMINHO):
        raise WhatsAppErro("Esse arquivo guarda segredos ou dados protegidos (chaves, cookies, sistema): não envio.")
    if p.stat().st_size > LIMITE_MB * 1048576:
        raise WhatsAppErro(f"Arquivo grande demais (limite de {LIMITE_MB} MB).")
    if p.suffix.lower() in BLOQUEADAS:
        z = Path(tempfile.gettempdir()) / (p.stem + ".zip")
        with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            zf.write(p, p.name)
        return str(z)
    return str(p)


def _esperar_chooser(a, segundos=8):
    a.ws.settimeout(segundos)
    fim = time.time() + segundos
    try:
        while time.time() < fim:
            m = json.loads(a.ws.recv())
            if m.get("method") == "Page.fileChooserOpened":
                return m["params"]
    except Exception:
        return None
    finally:
        a.ws.settimeout(30)
    return None


def enviar_arquivo(nome, caminho, legenda=""):
    """Envia um arquivo como documento. O seletor de arquivo e interceptado pelo navegador (nenhuma janela do Windows abre). Devolve o nome do contato."""
    arq = preparar_arquivo(caminho)
    with navegador.LOCK:
        a = _conectar()
        try:
            _preparar(a)
            lista = json.loads(a.js(JS_LISTA))
            alvo = _achar_conversa(a, nome, resolver(nome, [c["nome"] for c in lista]))
            a.cmd("Page.enable")
            a.cmd("Page.setInterceptFileChooserDialog", {"enabled": True})
            try:
                anexar = a.js(JS_ANEXAR)
                if not anexar:
                    raise WhatsAppErro("Não achei o botão Anexar do WhatsApp.")
                anexar = json.loads(anexar)
                _clicar(a, anexar["x"], anexar["y"])
                time.sleep(1.2)
                item = a.js(JS_ITEM_DOCUMENTO)
                if not item:
                    raise WhatsAppErro("Não achei a opção Documento no menu Anexar.")
                item = json.loads(item)
                _clicar(a, item["x"], item["y"])
                ch = _esperar_chooser(a)
                if not ch or "backendNodeId" not in ch:
                    raise WhatsAppErro("O WhatsApp não abriu o seletor de arquivo.")
                a.cmd("DOM.setFileInputFiles", {"files": [str(Path(arq).resolve())], "backendNodeId": ch["backendNodeId"]})
            finally:
                try:
                    a.cmd("Page.setInterceptFileChooserDialog", {"enabled": False})
                except Exception:
                    pass
            env = None
            for _ in range(30):
                r = a.js(JS_ICONE % json.dumps("wds-ic-send-filled"))
                if r:
                    env = json.loads(r)
                    break
                time.sleep(0.5)
            if not env:
                raise WhatsAppErro("A pré-visualização do arquivo não abriu. Nada foi enviado.")
            if legenda and a.js(JS_LEGENDA):
                a.cmd("Input.insertText", {"text": legenda})
                time.sleep(0.4)
                env = json.loads(a.js(JS_ICONE % json.dumps("wds-ic-send-filled")) or json.dumps(env))
            _clicar(a, env["x"], env["y"])
            time.sleep(4)
            return alvo
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
            alvo = _achar_conversa(a, nome, achados)
            if not a.js(JS_CAIXA):
                raise WhatsAppErro("caixa de mensagem não encontrada")
            achados = [alvo]
            a.cmd("Input.insertText", {"text": texto})
            time.sleep(0.4)
            a.enter()
            time.sleep(0.8)
            return achados[0]
        finally:
            a.__exit__()
