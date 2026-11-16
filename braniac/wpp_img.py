# -*- coding: utf-8 -*-
"""Imagens no WhatsApp Web (Chrome de automacao, porta 9222): LER a foto/print mais recente que a pessoa mandou.

A foto aparece no chat como <img src="blob:...">; lemos os bytes desse blob na propria pagina (nada e baixado, nada e enviado).
E a miniatura que o WhatsApp mostra no chat (boa para foto e print grande; texto muito miudo pode sair incompleto).
"""
import base64, json, time
from . import imagem, whatsapp, wpp_voz

JS_ULTIMA_IMAGEM = """(async function(){
  var main=document.querySelector('#main'); if(!main) return null;
  var imgs=[].slice.call(main.querySelectorAll('[role="row"] img[src^="blob:"]')).filter(function(i){
    return !i.closest('[class*="message-out"]') && (i.naturalWidth||i.width)>=80; });
  if(!imgs.length) return null;
  var alvo=imgs[imgs.length-1]; alvo.scrollIntoView({block:'nearest'});
  var b=await (await fetch(alvo.src)).blob(); var buf=new Uint8Array(await b.arrayBuffer()); var bin='';
  for (var i=0;i<buf.length;i+=0x8000) bin+=String.fromCharCode.apply(null,buf.subarray(i,i+0x8000));
  return JSON.stringify({tipo:b.type,b64:btoa(bin),w:alvo.naturalWidth,h:alvo.naturalHeight}); })()"""


def baixar_ultima_imagem(nome):
    """Abre a conversa e devolve (bytes da imagem recebida mais recente, None) ou (None, erro)."""
    with whatsapp.LOCK:
        try:
            W = whatsapp._wpp()
            with W.WA() as w:
                alvo, erro = wpp_voz._abrir_chat(W, w, nome)
                if erro:
                    return None, erro
                for _ in range(8):  # a miniatura carrega depois da conversa abrir
                    time.sleep(1)
                    r = w.js(JS_ULTIMA_IMAGEM)
                    if r:
                        return base64.b64decode(json.loads(r)["b64"]), None
                return None, "Não achei imagem recebida nessa conversa."
        except Exception as e:
            return None, whatsapp._erro(e)


def ver_ultima_imagem(nome):
    """Baixa a imagem mais recente da conversa e a descreve (Gemini; plano B local). Devolve (texto, erro)."""
    dados, erro = baixar_ultima_imagem(nome)
    if erro:
        return None, erro
    try:
        return imagem.descrever(dados), None
    except imagem.SemImagem as e:
        return None, str(e)[:120]
