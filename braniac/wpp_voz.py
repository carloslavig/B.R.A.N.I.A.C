# -*- coding: utf-8 -*-
"""Voz no WhatsApp Web: ENVIAR mensagem de voz e OUVIR audios recebidos (via Chrome de automacao, porta 9222).

ENVIAR: o Chrome do agente roda com microfone virtual (--use-file-for-fake-audio-capture=data/mic.wav%noloop). Trocamos o
        mic.wav pelo audio do Jarvis, apertamos o botao de gravar do WhatsApp, esperamos o audio acabar e enviamos.
        Sai como mensagem de voz de verdade. O Chrome precisa ter sido aberto por monitor/start-chrome-debug.bat.
OUVIR:  um gancho em URL.createObjectURL (instalado a cada carregamento da pagina) captura o arquivo de audio que o
        WhatsApp gera ao renderizar a conversa; recarregamos a pagina, abrimos a conversa e o 1o arquivo capturado e o
        audio MAIS RECENTE (o WhatsApp renderiza de baixo para cima). Nada e tocado. Transcricao: Whisper local.
"""
import base64, io, json, os, tempfile, time, wave
from pathlib import Path
from . import voz, whatsapp

MIC = Path(__file__).parent / "data" / "mic.wav"
FOLGA_S = 0.8  # espera depois do audio acabar, antes de apertar Enviar
_LOCK = whatsapp.LOCK  # a MESMA trava da pagina do WhatsApp (microfone virtual e pagina unicos)

SRC_GANCHO = """(function(){ if(window.__hkp) return; window.__hkp=true; window.__aud=[];
  var o=URL.createObjectURL;
  URL.createObjectURL=function(b){ try{ if(b && b.type && b.type.indexOf('audio')===0){ window.__aud.push(b); if(window.__aud.length>30) window.__aud.shift(); } }catch(e){} return o.call(this,b); };
})();"""
JS_PRIMEIRO_BLOB = """(async function(){ var bs=window.__aud||[]; if(!bs.length) return null; var b=bs[bs.length-1];   /* 25/10: o MAIS RECENTE (antes pegava o 1o e, com varios audios na tela, ouvia o errado) */
  var buf=new Uint8Array(await b.arrayBuffer()); var bin='';
  for (var i=0;i<buf.length;i+=0x8000) bin+=String.fromCharCode.apply(null,buf.subarray(i,i+0x8000));
  return JSON.stringify({tipo:b.type,b64:btoa(bin)}); })()"""
JS_DIRECOES_AUDIO = """(function(){ var main=document.querySelector('#main'); if(!main) return '[]';
  var btns=[].slice.call(main.querySelectorAll('[aria-label="Reproduzir mensagem de voz"], [aria-label="Pausar mensagem de voz"]'));
  return JSON.stringify(btns.map(function(b){ var r=b.closest('[role="row"]')||b.parentElement;
    var nossa=!!(r.className.indexOf('message-out')>=0||r.querySelector('[class*="message-out"],[data-icon="tail-out"],[data-icon^="msg-check"],[data-icon^="msg-dblcheck"],[data-icon^="msg-time"],[data-icon*="status-dblcheck"],[data-icon*="status-check"]')||[].slice.call(r.querySelectorAll('[aria-label]')).some(function(e){return /^\s*(Entregue|Lida|Enviada|Pendente|Delivered|Read|Sent|Pending)\s*$|^Você:$/i.test(e.getAttribute('aria-label'));}));
    var m=(r.innerText.match(/(\\d+):(\\d\\d)/)||[]); return [!nossa, m.length?(+m[1])*60+(+m[2]):0]; })); })()"""
JS_POSICAO_AUDIO = """(function(i){ var main=document.querySelector('#main'); var btns=[].slice.call(main.querySelectorAll('[aria-label="Reproduzir mensagem de voz"], [aria-label="Pausar mensagem de voz"]'));
  var b=btns[i]; if(!b) return null; b.scrollIntoView({block:'center'}); var r=b.getBoundingClientRect(); return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2}); })(%d)"""
JS_DURACOES = """(async function(){ var arr=(window.__aud||[]).slice(), n0=window.__aud.length, out=[];
  for (var b of arr){ out.push(await new Promise(function(ok){ var a=new Audio(URL.createObjectURL(b)); a.onloadedmetadata=function(){ok(a.duration)}; a.onerror=function(){ok(-1)}; setTimeout(function(){ok(-1)},4000); })); }
  window.__aud.length=n0; return JSON.stringify(out); })()"""
JS_RECT = """(function(escopo, rot){
  var els=[].slice.call(document.querySelectorAll(escopo)); var alvo=null;
  for (var e of els){ var a=(e.getAttribute('aria-label')||'').toLowerCase(); var r=e.getBoundingClientRect();
    if (new RegExp(rot,'i').test(a) && r.width>0) alvo=e; }
  if(!alvo) return null; var r=alvo.getBoundingClientRect(); return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2}); })(%s, %s)"""
JS_CONTA_VOZ = """document.querySelectorAll('#main [aria-label="Reproduzir mensagem de voz"], #main [aria-label="Pausar mensagem de voz"]').length"""
# a ULTIMA mensagem do chat e um audio? e e DELES (bolha do lado esquerdo)?
JS_ULTIMO_AUDIO = """(function(){
  var main=document.querySelector('#main'); if(!main) return null;
  var btns=[].slice.call(main.querySelectorAll('[aria-label="Reproduzir mensagem de voz"], [aria-label="Pausar mensagem de voz"]'));
  if(!btns.length) return JSON.stringify({audio:false,total:0});
  var rows=[].slice.call(main.querySelectorAll('[role="row"]')); var ultima=rows[rows.length-1];
  var tem=!!(ultima && ultima.querySelector('[aria-label="Reproduzir mensagem de voz"], [aria-label="Pausar mensagem de voz"]'));
  // mensagens ENVIADAS por nos tem "tiques" de entrega (aria-label Entregue/Lida/Enviada/Pendente); as recebidas nao
  var nossa=false; if(ultima){ [].slice.call(ultima.querySelectorAll('[aria-label]')).forEach(function(e){
    if(/^\\s*(entregue|lida|enviada|pendente)\\s*$/i.test(e.getAttribute('aria-label')||'')) nossa=true; }); }
  return JSON.stringify({audio:tem, dele:(tem && !nossa), total:btns.length}); })()"""


def _clicar(w, x, y):
    w.cmd("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
    time.sleep(0.2)
    for tipo, b in (("mousePressed", 1), ("mouseReleased", 0)):
        w.cmd("Input.dispatchMouseEvent", {"type": tipo, "x": x, "y": y, "button": "left", "buttons": b, "clickCount": 1})


def _rect(w, escopo, rotulo):
    r = w.js(JS_RECT % (json.dumps(escopo), json.dumps(rotulo)))
    return json.loads(r) if r else None


def _fechar_menus(w):
    whatsapp.cancelar_gravacao_presa(w)
    for _ in range(2):
        w.cmd("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
        time.sleep(0.25)


def _limpar_rascunho(w):
    """Apaga o que estiver escrito na caixa de mensagem: so com ela vazia o WhatsApp mostra o botao de microfone."""
    try:
        atual = w.js("(function(){var b=document.querySelector('footer [contenteditable=\"true\"]'); return b ? b.innerText.trim() : ''})()")
        if not atual:
            return
        w.js("(function(){var b=document.querySelector('footer [contenteditable=\"true\"]'); if(b) b.focus()})()")
        time.sleep(0.2)
        for tipo in ("keyDown", "keyUp"):     # Ctrl+A e depois apaga (o React do WhatsApp ignora execCommand)
            w.cmd("Input.dispatchKeyEvent", {"type": tipo, "key": "a", "code": "KeyA", "windowsVirtualKeyCode": 65, "modifiers": 2})
        time.sleep(0.2)
        for tipo in ("keyDown", "keyUp"):
            w.cmd("Input.dispatchKeyEvent", {"type": tipo, "key": "Backspace", "code": "Backspace", "windowsVirtualKeyCode": 8})
        time.sleep(0.4)
        from .store import DATA        # nada some em silencio: o rascunho apagado fica no log
        with (DATA / "voz.log").open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | rascunho apagado para gravar audio | {atual[:120]!r}\n")
    except Exception:
        pass


def _abrir_chat(W, w, nome, pedido=None):
    lista = json.loads(w.js(W.JS_LISTA))
    alvos = whatsapp.resolver_nome(nome, [c["nome"] for c in lista])
    if not alvos:  # contato sem conversa recente na lista: acha pela busca do WhatsApp
        w.js("var i=document.querySelector('#side input[aria-label^=\"Pesquisar\"]'); i&&i.focus()")
        w.cmd("Input.insertText", {"text": nome})
        time.sleep(2)
        lista = json.loads(w.js(W.JS_LISTA))
        alvos = whatsapp.resolver_nome(nome, [c["nome"] for c in lista])
    if not alvos:
        return None, f"Não achei conversa com '{nome}' no WhatsApp."
    if len(alvos) > 1:   # nao pergunta ao Dono: nome exato, senao o primeiro resultado
        alvos = [whatsapp.melhor_candidato(nome, alvos)]
    if not W.abrir(w, alvos[0]):
        # 15/10: a conversa estava na lista mas fora da area visivel (nao da para clicar): busca pelo nome e tenta de novo
        w.js("var i=document.querySelector('#side input[aria-label^=\"Pesquisar\"]'); i&&i.focus()")
        w.cmd("Input.insertText", {"text": whatsapp._chave_busca(alvos[0])})
        time.sleep(2)
        if not W.abrir(w, alvos[0]):
            return None, f"Não consegui abrir a conversa com {alvos[0]}."
    time.sleep(1.2)
    bloqueio = whatsapp.trava_destino(w, pedido or nome)    # 14/10: confere o NOME NO TOPO do chat contra o que foi pedido
    if bloqueio:
        return None, bloqueio
    whatsapp.cancelar_gravacao_presa(w)
    return alvos[0], None


def ultimo_audio_dele(w):
    """No chat ABERTO: {'audio': bool, 'dele': bool, 'total': n}. 'dele' = a bolha esta do lado de la (recebido)."""
    r = w.js(JS_ULTIMO_AUDIO)
    return json.loads(r) if r else {"audio": False, "dele": False, "total": 0}


# ---------- enviar ----------

def preparar_mic(wav_bytes):
    """Grava o audio do Jarvis em mic.wav (PCM 16-bit mono) com um pouco de silencio no fim. Devolve a duracao em segundos."""
    with wave.open(io.BytesIO(wav_bytes)) as w:
        taxa, dados, n = w.getframerate(), w.readframes(w.getnframes()), w.getnframes()
    tmp = Path(str(MIC) + ".tmp")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(dados + b"\x00\x00" * int(taxa * 1.5))
    os.replace(tmp, MIC)
    return n / taxa


def enviar_voz(nome, wav_bytes):
    with _LOCK:
        r = _enviar_voz(nome, wav_bytes)
    if str(r).startswith("✅"):
        try:
            from . import monitor_dono
            monitor_dono.registrar_envio(nome)      # para nao confundir o audio do Jarvis com um comando de voz do Dono
        except Exception:
            pass
    return r


def _enviar_voz(nome, wav_bytes):
    """Envia `wav_bytes` como MENSAGEM DE VOZ para a conversa `nome`. Devolve texto de resultado (comeca com ✅ se deu certo)."""
    try:
        dur = preparar_mic(wav_bytes)
        W = whatsapp._wpp()
        with W.WA() as w:
            _fechar_menus(w)
            alvo, erro = _abrir_chat(W, w, nome)
            if erro:
                return erro
            antes = int(w.js(JS_CONTA_VOZ) or 0)
            _limpar_rascunho(w)      # 15/10: com texto na caixa o WhatsApp troca o microfone por 'Enviar' e o audio nao saia
            mic = _rect(w, "footer [aria-label]", "mensagem de voz")
            if not mic:
                return "Não achei o botão de mensagem de voz do WhatsApp."
            _clicar(w, mic["x"], mic["y"])  # comeca a gravar (o microfone virtual toca o mic.wav)
            time.sleep(dur + FOLGA_S)
            env = _rect(w, "footer [aria-label]", "^enviar")
            if not env:
                _fechar_menus(w)
                return "A gravação não abriu (o Chrome do agente foi iniciado sem o microfone virtual?). Use monitor/start-chrome-debug.bat."
            _clicar(w, env["x"], env["y"])
            time.sleep(3)
            depois = int(w.js(JS_CONTA_VOZ) or 0)
        return f"✅ Áudio enviado para {alvo}." if depois > antes else f"Cliquei em enviar para {alvo}, mas não vi o áudio aparecer; confira."
    except Exception as e:
        return whatsapp._erro(e)


# ---------- ouvir ----------

def baixar_ultimo_audio(nome):
    with _LOCK:
        return _baixar_ultimo_audio(nome)


def _log_voz(texto):
    try:
        from .store import DATA
        with (DATA / "voz.log").open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {texto}\n")
    except OSError:
        pass


def _audios_sem_recarregar(W, w, nome, espera_s=8):
    """16/11: recarregar o WhatsApp para ouvir audio deixava a aba ~10 min sem responder. Primeiro tenta na pagina aberta:
    instala o gancho (idempotente), zera a lista, fecha e reabre a conversa para as bolhas montarem de novo.
    True se apareceram audios desta conversa; False -> quem chamou recarrega a pagina como antes."""
    try:
        w.js(SRC_GANCHO)
        w.js("window.__aud=[]")      # so os blobs criados ao abrir ESTA conversa (sem misturar audio de outra pessoa)
        _fechar_menus(w)             # Esc fecha a conversa aberta
        _, erro = _abrir_chat(W, w, nome)
        if erro:
            return False
        for _ in range(espera_s):
            time.sleep(1)
            if int(w.js("(window.__aud||[]).length") or 0):
                _log_voz(f"ouvir {nome}: audio pego sem recarregar a pagina")
                return True
    except Exception:
        pass
    return False


def _baixar_audios(nome, n=1, pular_nossos=False, so_nossos=False):
    """Devolve (lista de bytes OGG/Opus dos ultimos `n` audios DELES ainda sem resposta nossa, em ordem; None) ou (None, erro). Recarrega a pagina do WhatsApp."""
    try:
        W = whatsapp._wpp()
        with W.WA() as w:
            w.cmd("Page.enable")
            w.cmd("Page.addScriptToEvaluateOnNewDocument", {"source": SRC_GANCHO})  # vale para a pagina recarregada
            if not _audios_sem_recarregar(W, w, nome):
                _log_voz(f"ouvir {nome}: sem audio novo na pagina aberta, recarregando")
                w.cmd("Page.reload", {"ignoreCache": False})
                time.sleep(3)
                limite = time.time() + 60   # 16/11: cada js travado leva 20 s; sem teto de relogio o laco segurava o WhatsApp ~14 min
                for _ in range(40):  # espera a lista de conversas voltar
                    if time.time() > limite:
                        return None, "O WhatsApp não voltou a carregar."
                    time.sleep(1.5)
                    try:
                        if len(json.loads(w.js(W.JS_LISTA))) > 3:
                            break
                    except Exception:
                        pass
                else:
                    return None, "O WhatsApp não voltou a carregar."
                alvo, erro = _abrir_chat(W, w, nome)
                if erro:
                    return None, erro
                for _ in range(10):  # a conversa renderiza e o WhatsApp gera os arquivos de audio
                    time.sleep(1)
                    if int(w.js("(window.__aud||[]).length") or 0):
                        break
                else:
                    return None, "Não há áudio nessa conversa."
            # 25/10: o audio MAIS RECENTE DELES. A ordem dos blobs nao bate com a das bolhas (o WhatsApp so cria blob de alguns), entao casa pela DURACAO da bolha.
            time.sleep(2)
            linhas = json.loads(w.js(JS_DIRECOES_AUDIO) or "[]")
            # 04/11: o pai mandou 2 audios seguidos e so o ultimo era ouvido: pega a sequencia final de audios DELES (apos o ultimo nosso), ate `n`
            fim = []
            for x in reversed(linhas):
                if not x[0]:
                    if pular_nossos:    # recuperar audios que ja ficaram para tras de uma resposta nossa
                        continue
                    break
                fim.append(x)
            fim = list(reversed(fim))[-n:] or [x for x in linhas if x[0]][-1:]
            if so_nossos:       # 13/11: o audio MAIS RECENTE do Dono (comando dele num chat), nao o da pessoa
                fim = [x for x in linhas if not x[0]][-1:]
            durs = json.loads(w.js(JS_DURACOES) or "[]") if any(x[1] for x in fim) else []
            usados, idxs = set(), []
            for x in fim:
                certos = [i for i, d_ in enumerate(durs) if i not in usados and d_ > 0 and x[1] and abs(d_ - x[1]) <= 1.6]
                if not certos:
                    if n == 1 or not idxs:
                        if x[1]:
                            return None, "O ultimo audio dele ainda nao baixou no WhatsApp Web (sem botao de reproduzir). Peca para reenviar ou mande por texto."
                        certos = [int(w.js("(window.__aud||[]).length") or 1) - 1]
                    else:
                        continue
                usados.add(certos[-1])
                idxs.append(certos[-1])
            saida = []
            for idx in idxs:
                d = json.loads(w.js(JS_PRIMEIRO_BLOB.replace("bs[bs.length-1]", "bs[%d]" % idx)))
                saida.append(base64.b64decode(d["b64"]))
            return saida, None
    except Exception as e:
        return None, whatsapp._erro(e)


def _baixar_ultimo_audio(nome):
    r, erro = _baixar_audios(nome, 1)
    return (r[-1] if r else None), erro


def ouvir_ultimo_audio(nome, n=3, pular_nossos=False, so_nossos=False):
    """Baixa os ultimos audios dele sem resposta (ate `n`) e transcreve com o Whisper local, na ordem. Devolve (texto, erro)."""
    with _LOCK:
        lista, erro = _baixar_audios(nome, n, pular_nossos, so_nossos)
    if erro:
        return None, erro
    textos = []
    for dados in lista:
        f = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
        f.write(dados)
        f.close()
        try:
            t = (voz.transcrever(f.name) or "").strip()
            if t:
                textos.append(t)
        finally:
            os.unlink(f.name)
    return " ".join(textos), None
