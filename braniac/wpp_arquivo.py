# -*- coding: utf-8 -*-
"""Enviar um ARQUIVO (documento) pelo WhatsApp Web, via Chrome de automacao (porta 9222).

Como: Anexar > Documento com o seletor de arquivo INTERCEPTADO (Page.setInterceptFileChooserDialog) -> o Chrome nos devolve o no do <input>
e escolhemos o arquivo por DOM.setFileInputFiles (nenhuma janela do Windows abre) -> legenda opcional -> Enviar -> espera sair o 'Pendente'.
O WhatsApp bloqueia executaveis (.exe, .bat, .msi...): `compactar()` os coloca num .zip antes de enviar.
So manda o que o Dono mandou mandar: nao esta ligado a nenhum atendimento automatico (use pela linha de comando ou pelo Jarvis do dono)."""
import json, os, re, tempfile, time, zipfile
from pathlib import Path
from . import whatsapp, wpp_voz

LIMITE_MB = 100            # conservador; o WhatsApp Web aceita ate 2 GB, mas upload longo demais trava a pagina unica
BLOQUEADAS = {".exe", ".bat", ".cmd", ".msi", ".scr", ".com", ".vbs", ".js", ".jar", ".ps1", ".dll", ".lnk", ".apk"}
ESPERA_ENVIO_S = 240

JS_ITEM_DOCUMENTO = """(function(){ var els=[...document.querySelectorAll('[role=menuitem], li[role=button], [data-animate-dropdown-item], li, button')];
  var alvo=els.find(e=>/^documento$/i.test((e.innerText||'').trim()) && e.getBoundingClientRect().width>0);
  if(!alvo) return null; var r=alvo.getBoundingClientRect(); return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2}); })()"""
# tela de pre-visualizacao do anexo: o botao de enviar e so um icone (sem aria-label) e o X fecha sem enviar
JS_ICONE = """(function(ic){ var i=[...document.querySelectorAll('[data-icon="'+ic+'"]')].find(e=>e.getBoundingClientRect().width>0);
  if(!i) return null; var b=i.closest('button,[role=button]')||i; var r=b.getBoundingClientRect();
  return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2}); })(%s)"""
# o X da PRE-VISUALIZACAO: sobe a arvore a partir do botao de enviar ate achar um X junto (o aviso de notificacoes tambem tem um X)
JS_X_DA_PREVIA = """(function(){ var s=document.querySelector('[data-icon="wds-ic-send-filled"]'); if(!s) return null; var n=s;
  for (var k=0;k<14 && n;k++){ n=n.parentElement; var x=n && n.querySelector('[data-icon="x-alt"]');
    if(x){ var b=x.closest('button,[role=button]')||x; var r=b.getBoundingClientRect(); if(r.width>0) return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2}); } }
  return null; })()"""
# previa nova (15/11): sem data-icon; o anexo sai pelo 'Remover anexo' (fechar a previa por X nao funciona mais)
JS_REMOVER_ANEXO = """(function(){ var e=[...document.querySelectorAll('[aria-label="Remover anexo"]')].find(x=>x.getBoundingClientRect().width>0);
  if(!e) return null; var r=e.getBoundingClientRect(); return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2}); })()"""
PREVIA_NAO_ABRIU = "A pré-visualização do arquivo não abriu (o botão Enviar não apareceu). Nada foi enviado."
JS_LEGENDA ="""(function(){ var c=[...document.querySelectorAll('[contenteditable="true"]')].find(e=>!e.closest('#side') && !e.closest('footer') && e.getBoundingClientRect().width>0);
  if(!c) return false; c.focus(); return true; })()"""
# a ULTIMA linha do chat: ainda 'Pendente' (relogio)? ja tem tique de enviada/entregue/lida? cita o nome do arquivo?
JS_ULTIMA = """(function(nome){ var main=document.querySelector('#main'); if(!main) return null;
  var rows=[].slice.call(main.querySelectorAll('[role="row"]')); var u=rows[rows.length-1]; if(!u) return JSON.stringify({achou:false});
  var tx=(u.innerText||''); var lab=[].slice.call(u.querySelectorAll('[aria-label]')).map(e=>(e.getAttribute('aria-label')||'').toLowerCase());
  var pend=lab.some(l=>/pendente/.test(l)); var ok=lab.some(l=>/^(enviada|entregue|lida)$/.test(l.trim()));
  return JSON.stringify({achou: tx.indexOf(nome)>=0, pendente: pend, enviada: ok}); })(%s)"""


class ArquivoErro(RuntimeError):
    pass


# Dono (07/10): o Jarvis pode mandar QUALQUER arquivo do PC quando ele pedir (foco: pastas do Braniac). So fica de fora o que guarda segredo
# (chaves, cookies, cofre, bancos do Jarvis/WhatsApp, perfil do Chrome, AppData), o legado pessoal e as pastas do sistema.
_HOME = Path.home()
_BRANIAC = Path(__file__).parent
PRIORIDADE = [_BRANIAC, _BRANIAC.parent / "cortes-lives", _HOME / "Projetos" / "BRANIAC", _HOME / "Projetos", _HOME / "OneDrive" / "Área de Trabalho",
              _HOME / "Desktop", _HOME / "Downloads", _HOME / "Documents", _HOME / "OneDrive", _HOME / "Pictures"]
BLOQUEIO = (".env", ".pem", ".key", ".pfx", ".kdbx", "id_rsa", ".ssh", ".db", ".sqlite", "cookies", "login data", "cofre", "chromeagente", "appdata",
            "bravoseguranca", r"\legado", r"\gustavo", r"\braniac\data" + "\\", r"\windows" + "\\", r"\program files", r"\programdata")
LIBERADO_DENTRO_DE_DATA = (r"\braniac\data\imagens", r"\braniac\data\cortes\saida")
IGNORAR_NA_BUSCA = {".git", "node_modules", "target", "__pycache__", ".pytest_cache", "pyi", "binaries"}
ATALHOS = {"jogo": _BRANIAC.parent / "jogo-apk" / "dist" / "JOGO.apk", "braniac": _HOME / "OneDrive" / "Área de Trabalho" / "BRANIAC" / "BRANIAC_0.3.0.zip"}


def _bloqueado(p):
    baixo = str(p).lower() + "\\"
    if any(m in baixo for m in LIBERADO_DENTRO_DE_DATA):
        return False
    return any(b in baixo for b in BLOQUEIO)


def buscar(consulta, limite=8, segundos=6):
    """Procura arquivos pelo nome (todas as palavras) nas pastas de PRIORIDADE (Braniac primeiro) e depois no resto do perfil. Devolve [Path] (mais relevantes primeiro)."""
    import os
    toks = [t for t in re.findall(r"[\wÀ-ÿ.]+", consulta.lower()) if len(t) > 1]
    if not toks:
        return []
    fim = time.time() + segundos
    achados, vistos = [], set()
    for raiz in PRIORIDADE + [_HOME]:
        if not raiz.exists():
            continue
        for dirpath, dirs, files in os.walk(raiz):
            dirs[:] = [d for d in dirs if d.lower() not in IGNORAR_NA_BUSCA and not _bloqueado(Path(dirpath) / d)]
            for f in files:
                if all(t in f.lower() for t in toks):
                    caminho = Path(dirpath) / f
                    if str(caminho) not in vistos and not _bloqueado(caminho):
                        vistos.add(str(caminho))
                        achados.append(caminho)
            if time.time() > fim or len(achados) >= limite * 4:
                break
        if achados and time.time() > fim:
            break
        if len(achados) >= limite and raiz in PRIORIDADE[:4]:
            break
    def chave(p):
        try:
            return (0 if p.name.lower() == consulta.strip().lower() else 1, 0 if any(str(p).lower().startswith(str(r).lower()) for r in PRIORIDADE[:4]) else 1, -p.stat().st_mtime)
        except OSError:
            return (2, 0)
    return sorted(achados, key=chave)[:limite]


def resolver_caminho(texto):
    """Atalho ('braniac'), caminho completo ou parte do nome (acha o mais recente, Braniac primeiro). Levanta ArquivoErro se nao achar ou se for area protegida."""
    t = (texto or "").strip().strip('"')
    if not t:
        raise ArquivoErro("Faltou dizer qual arquivo.")
    p = ATALHOS.get(t.lower())
    if p is None:
        cand = Path(os.path.expandvars(os.path.expanduser(t)))
        if (cand.is_absolute() or "\\" in t or "/" in t) and (cand.exists() or cand.is_absolute()):
            p = cand
        elif "\\" in t or "/" in t:   # 24/10: a IA devolve caminho relativo ('curriculos/arquivo.pdf'): procura pelo NOME do arquivo
            ach = buscar(Path(t.replace("\\", "/")).name, limite=1)
            if not ach:
                raise ArquivoErro(f"Não achei '{t}' no PC.")
            p = ach[0]
        else:
            ach = buscar(t, limite=1)
            if not ach:
                raise ArquivoErro(f"Não achei nenhum arquivo com '{t}' no nome.")
            p = ach[0]
    try:
        p = p.resolve()
    except OSError:
        raise ArquivoErro("Caminho inválido.")
    if _bloqueado(p):
        raise ArquivoErro("Esse arquivo guarda segredos ou dados pessoais protegidos (chaves, bancos, legado, sistema): não envio.")
    if not p.is_file():
        raise ArquivoErro(f"Arquivo não encontrado: {p}")
    return str(p)


def compactar(caminho, destino_dir=None):
    """Se o arquivo e um tipo que o WhatsApp bloqueia, devolve o caminho de um .zip com ele; senao devolve o proprio caminho."""
    p = Path(caminho)
    if not p.is_file():
        raise ArquivoErro(f"Arquivo não encontrado: {caminho}")
    if p.suffix.lower() not in BLOQUEADAS:
        return str(p)
    pasta = Path(destino_dir or tempfile.gettempdir())
    zip_ = pasta / (p.stem + ".zip")
    with zipfile.ZipFile(zip_, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.write(p, p.name)
    return str(zip_)


def validar(caminho):
    p = Path(caminho)
    if not p.is_file():
        raise ArquivoErro(f"Arquivo não encontrado: {caminho}")
    mb = p.stat().st_size / 1048576
    if mb > LIMITE_MB:
        raise ArquivoErro(f"Arquivo grande demais ({mb:.0f} MB; o limite aqui é {LIMITE_MB} MB).")
    if p.suffix.lower() in BLOQUEADAS:
        raise ArquivoErro("O WhatsApp bloqueia esse tipo de arquivo: compacte em .zip antes.")
    return p


def enviar_arquivo(nome, caminho, legenda=""):
    """Envia `caminho` como documento para a conversa `nome`. Executaveis viram .zip automaticamente. Devolve texto (comeca com ✅ se deu certo)."""
    try:
        caminho = compactar(caminho)
        p = validar(caminho)
    except ArquivoErro as e:
        return str(e)
    with whatsapp.LOCK:
        r = _enviar(nome, p, legenda)
        if r == PREVIA_NAO_ABRIU:   # 15/11: a aba do WhatsApp Web travou e descartava todo anexo ate recarregar a pagina
            _recarregar()
            r = _enviar(nome, p, legenda)
        return r


def _recarregar():
    W = whatsapp._wpp()
    with W.WA() as w:
        w.cmd("Page.reload", {"ignoreCache": False})
        for _ in range(40):
            time.sleep(1.5)
            try:
                if w.js("!!document.querySelector('#pane-side')"):
                    return
            except Exception:
                pass


def _esperar_chooser(w, segundos=8):
    w.ws.settimeout(segundos)
    fim = time.time() + segundos
    try:
        while time.time() < fim:
            m = json.loads(w.ws.recv())
            if m.get("method") == "Page.fileChooserOpened":
                return m["params"]
    except Exception:
        return None
    finally:
        w.ws.settimeout(20)
    return None


JS_ENVIAR_ARIA = """(function(){ var b=[...document.querySelectorAll('[aria-label]')].find(e=>/^Enviar \\d+ ite/i.test(e.getAttribute('aria-label')||'') && e.getBoundingClientRect().width>0);
  if(!b) return null; var r=b.getBoundingClientRect(); return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2}); })()"""


def _esperar_icone(w, icone, segundos):
    fim = time.time() + segundos
    while time.time() < fim:
        r = w.js(JS_ICONE % json.dumps(icone))
        if not r and icone == "wds-ic-send-filled":   # 24/10: o botao de enviar da previa perdeu o data-icon; agora so tem aria-label 'Enviar N item selecionado'
            r = w.js(JS_ENVIAR_ARIA)
        if r:
            return json.loads(r)
        time.sleep(0.5)
    return None


def _fechar_previa(w):
    """Se sobrou uma pre-visualizacao de anexo aberta (de uma tentativa anterior), fecha pelo X SEM enviar."""
    for _ in range(3):
        x = w.js(JS_X_DA_PREVIA) or w.js(JS_REMOVER_ANEXO)
        if not x:
            return
        x = json.loads(x)
        wpp_voz._clicar(w, x["x"], x["y"])
        time.sleep(1)
    wpp_voz._fechar_menus(w)


def _enviar(nome, p, legenda):
    try:
        W = whatsapp._wpp()
        with W.WA() as w:
            _fechar_previa(w)
            wpp_voz._fechar_menus(w)
            alvo, erro = wpp_voz._abrir_chat(W, w, nome)
            if erro:
                return erro
            w.cmd("Page.enable")
            w.cmd("Page.setInterceptFileChooserDialog", {"enabled": True})
            try:
                anexar = wpp_voz._rect(w, "footer [aria-label], footer button, footer [role=button]", "^anexar|^attach")
                if not anexar:
                    return "Não achei o botão Anexar do WhatsApp."
                wpp_voz._clicar(w, anexar["x"], anexar["y"])
                it = None
                for tent in range(8):      # o menu Anexar demora a abrir (>1,2 s em 17/10/2026)
                    time.sleep(0.6)
                    it = w.js(JS_ITEM_DOCUMENTO)
                    if it:
                        break
                    if tent == 3:   # 24/10: o clique por coordenada as vezes nao abre o menu (janela do Chrome sem foco); o clique do proprio botao abre
                        w.js("(function(){var b=[...document.querySelectorAll('footer button')].find(e=>/anexar|attach/i.test(e.getAttribute('aria-label')||'')); if(b) b.click();})()")
                if not it:
                    wpp_voz._fechar_menus(w)
                    return "Não achei a opção Documento no menu Anexar."
                it = json.loads(it)
                wpp_voz._clicar(w, it["x"], it["y"])
                ch = _esperar_chooser(w)
                if not ch or "backendNodeId" not in ch:
                    wpp_voz._fechar_menus(w)
                    return "O WhatsApp não abriu o seletor de arquivo."
                w.cmd("DOM.setFileInputFiles", {"files": [str(p.resolve())], "backendNodeId": ch["backendNodeId"]})
            finally:
                try:
                    w.cmd("Page.setInterceptFileChooserDialog", {"enabled": False})
                except Exception:
                    pass
            env = _esperar_icone(w, "wds-ic-send-filled", 15)  # a pre-visualizacao do documento abre
            if not env:
                _fechar_previa(w)
                return PREVIA_NAO_ABRIU
            if legenda and w.js(JS_LEGENDA):
                w.cmd("Input.insertText", {"text": legenda})
                time.sleep(0.4)
                env = _esperar_icone(w, "wds-ic-send-filled", 3) or env
            wpp_voz._clicar(w, env["x"], env["y"])
            fim = time.time() + ESPERA_ENVIO_S
            time.sleep(2)
            while time.time() < fim:
                st = w.js(JS_ULTIMA % json.dumps(p.name[:30]))
                st = json.loads(st) if st else {}
                if st.get("achou") and not st.get("pendente") and st.get("enviada"):
                    return f"✅ Arquivo '{p.name}' enviado para {alvo}."
                time.sleep(2)
            return f"Cliquei em enviar '{p.name}' para {alvo}, mas não vi a confirmação de envio; confira o WhatsApp."
    except Exception as e:
        return whatsapp._erro(e)


JS_NOSSAS_RECENTES = """(function(){ var out=[]; document.querySelectorAll('[data-pre-plain-text]').forEach(function(el){
    var cab=el.getAttribute('data-pre-plain-text')||''; var row=el.closest('[class*="message-in"],[class*="message-out"]');
    var nossa=(row && row.className.indexOf('message-out')>=0) || /\\]\\s*Dono\\s*:/i.test(cab); if(!nossa) return;
    var corpo=el.querySelector('span.selectable-text, span[dir]'); out.push({h:cab.replace(/\\s+/g,' ').trim(), t:((corpo?corpo.innerText:el.innerText)||'').trim()}); });
  return JSON.stringify(out.slice(-6)); })()"""
JANELA_DUPLICADA_MIN = 20


def _norm_msg(t):
    return " ".join(str(t or "").lower().split())


def duplicada(recentes, texto, agora=None):
    """True se uma mensagem NOSSA igual (ou a mesma sem/com a nota do final) saiu nos ultimos 20 min nessa conversa.
    25/10: lembretes e avisos chegavam 2x (reenvio quando a confirmacao do envio nao era vista, e threads concorrentes)."""
    import re as _re
    from datetime import datetime as _dt, timedelta as _td
    agora = agora or _dt.now()
    novo = _norm_msg(texto)
    if len(novo) < 12:
        return False
    for r in recentes or []:
        m = _re.search(r"\[(\d{1,2}):(\d{2}),\s*(\d{1,2})/(\d{1,2})/(\d{4})\]", r.get("h", ""))
        if not m:
            continue
        hh, mi, dd, mo, aa = (int(x) for x in m.groups())
        try:
            quando = _dt(aa, mo, dd, hh, mi)
        except ValueError:
            continue
        if not (_td(0) <= agora - quando <= _td(minutes=JANELA_DUPLICADA_MIN)):
            continue
        velho = _norm_msg(r.get("t", ""))
        if velho and (velho == novo or velho.startswith(novo) or novo.startswith(velho)):
            return True
    return False


def enviar_texto(nome, texto, pedido=None):
    """Texto para uma conversa que PODE nao estar na lista visivel (acha pela busca do WhatsApp). `whatsapp.enviar` so enxerga a lista."""
    from . import tratamento
    texto = tratamento.corrigir(texto)
    with whatsapp.LOCK:
        try:
            W = whatsapp._wpp()
            with W.WA() as w:
                _fechar_previa(w)
                wpp_voz._fechar_menus(w)
                alvo, erro = wpp_voz._abrir_chat(W, w, nome, pedido)
                if erro:
                    return erro
                if not w.js("(function(){var b=document.querySelector('footer [contenteditable=\"true\"], [contenteditable=\"true\"][data-tab=\"10\"]'); if(!b) return false; b.focus(); return true})()"):
                    return f"Não achei a caixa de mensagem da conversa com {alvo}. Nada foi enviado."
                try:
                    if duplicada(json.loads(w.js(JS_NOSSAS_RECENTES) or "[]"), texto):
                        return f"✅ Mensagem enviada para {alvo}. (ja estava enviada ha instantes: nao repeti)"
                except Exception:
                    pass
                w.cmd("Input.insertText", {"text": texto})
                time.sleep(0.5)
                for tipo in ("keyDown", "keyUp"):
                    w.cmd("Input.dispatchKeyEvent", {"type": tipo, "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13,
                                                     "nativeVirtualKeyCode": 13, "text": "\r" if tipo == "keyDown" else ""})
                time.sleep(1.5)
                return f"✅ Mensagem enviada para {alvo}."
        except Exception as e:
            return whatsapp._erro(e)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("uso: python -m braniac.wpp_arquivo <contato> <arquivo> [legenda]")
        sys.exit(2)
    print(enviar_arquivo(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else ""))
