# -*- coding: utf-8 -*-
"""Gera imagem pelo GEMINI (aba logada do Chrome do Braniac) e salva o arquivo (Dono autorizou em 02/10 e pediu a arte do canal em 08/10).
Mesmo cuidado do ia_web: so uma aba na frente por vez, sob a trava do WhatsApp, e o foco volta ao WhatsApp no fim.
O prompt vai para o Google (arte do canal; nunca ponha dado pessoal ou de terceiros)."""
import base64, json, time
from pathlib import Path
from . import ia_web, whatsapp

JS_IMGS = """(function(){ var r=[...document.querySelectorAll('model-response, .model-response-text, message-content')]; var alvo=r[r.length-1]||document;
  var imgs=[...alvo.querySelectorAll('img')].filter(i=>i.naturalWidth>=256 && !/avatar|logo|icon/i.test(i.className+i.alt)).map(i=>({src:i.currentSrc||i.src,w:i.naturalWidth,h:i.naturalHeight}));
  return JSON.stringify(imgs); })()"""
JS_BAIXAR = """(async function(src){ const r=await fetch(src); const b=await r.blob(); const buf=new Uint8Array(await b.arrayBuffer()); let bin='';
  for(let i=0;i<buf.length;i+=0x8000) bin+=String.fromCharCode.apply(null,buf.subarray(i,i+0x8000)); return JSON.stringify({tipo:b.type,b64:btoa(bin)}); })(%s)"""


class ImagemErro(RuntimeError):
    pass


JS_CANVAS = """(async function(){ var i=document.images[0]; if(!i || !i.complete || !i.naturalWidth) return null; try { await i.decode(); } catch(e) {}
  var c=document.createElement('canvas'); c.width=i.naturalWidth; c.height=i.naturalHeight; var x=c.getContext('2d'); x.drawImage(i,0,0);
  var px=x.getImageData(0,0,c.width,c.height).data, nb=0; for (var k=0;k<px.length;k+=4000){ if (px[k]<245||px[k+1]<245||px[k+2]<245) nb++; }
  if (!nb) return null;   // ainda em branco: o navegador nao terminou de desenhar
  return JSON.stringify({w:c.width,h:c.height,b64:c.toDataURL('image/png').split(',')[1]}); })()"""


def _baixar(src):
    """O fetch da pagina do Gemini e bloqueado (CORS). Abrimos a IMAGEM como documento propria (mesma origem) em aba nova e lemos pelo canvas. Pede tamanho 2048 (capa do YouTube exige >= 2048x1152)."""
    import re
    from . import pesquisa
    url = re.sub(r"=s\d+(-rj)?$", "=s2048-rj", src) if re.search(r"=s\d+", src) else src
    aba = pesquisa._nova_aba(url)
    try:
        ws, cmd, js = pesquisa._ws(aba)
        try:
            for _ in range(20):
                time.sleep(1.5)
                r = js(JS_CANVAS)
                if r:
                    d = json.loads(r)
                    if d["w"] > 0:
                        return base64.b64decode(d["b64"])
        finally:
            ws.close()
    finally:
        pesquisa._fechar_aba(aba["id"])
    raise ImagemErro("não consegui baixar a imagem gerada")


def _anexar(a, caminho):
    """Anexa um arquivo (foto de referencia) na caixa do Gemini: abre o menu 'Envio e ferramentas' e poe o arquivo no input[type=file] que aparece."""
    a.js("(function(){var b=[...document.querySelectorAll('button')].find(b=>/Envio e ferramentas|Upload|Enviar arquivo/i.test(b.getAttribute('aria-label')||'')); if(b) b.click()})()")
    time.sleep(2)
    raiz = a.cmd("DOM.getDocument", {"depth": -1, "pierce": True})["root"]["nodeId"]
    nos = a.cmd("DOM.querySelectorAll", {"nodeId": raiz, "selector": "input[type=file]"}).get("nodeIds", [])
    if not nos:
        raise ImagemErro("não achei onde anexar a foto de referência no Gemini")
    aceita = [n for n in nos if "image" in (dict(zip(*[iter(a.cmd("DOM.getAttributes", {"nodeId": n}).get("attributes", []))] * 2)).get("accept", "image"))]
    a.cmd("DOM.setFileInputFiles", {"files": [str(Path(caminho).resolve())], "nodeId": (aceita or nos)[0]})
    a.js("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))")
    time.sleep(6)          # tempo do upload aparecer na caixa


def gerar(prompt, destino, timeout_s=180, referencia=None):
    """Pede a imagem ao Gemini e salva em `destino` (png/jpg). Devolve o caminho. Levanta ImagemErro se nao vier imagem.
    referencia: foto anexada antes do pedido (ex.: a pessoa que deve aparecer). So com autorizacao de quem esta na foto."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    site = ia_web.SITES["gemini"]
    with whatsapp.LOCK:
        try:
            with ia_web._Aba(site) as a:
                alvo_id = a.url.rstrip("/").split("/")[-1]
                a.cmd("Target.activateTarget", {"targetId": alvo_id})
                a.cmd("Page.bringToFront")
                a.cmd("Page.navigate", {"url": site["nova"]})
                time.sleep(5)
                if referencia:
                    _anexar(a, referencia)
                a.js(f"document.querySelector({json.dumps(site['entrada'])}).focus()")
                a.cmd("Input.insertText", {"text": prompt})
                time.sleep(1)
                a.js(f"(function(){{var b=document.querySelector({json.dumps(site['enviar'])}); if(b) b.click()}})()")
                fim = time.time() + timeout_s
                img = None
                while time.time() < fim:
                    time.sleep(3)
                    try:
                        a.cmd("Target.activateTarget", {"targetId": alvo_id})
                        a.cmd("Page.bringToFront")
                    except ia_web.IAWebErro:
                        pass
                    imgs = json.loads(a.js(JS_IMGS) or "[]")
                    if imgs:
                        time.sleep(4)          # deixa terminar de renderizar a versao final
                        imgs = json.loads(a.js(JS_IMGS) or "[]") or imgs
                        img = max(imgs, key=lambda i: i["w"] * i["h"])
                        break
                if not img:
                    raise ImagemErro("o Gemini não devolveu imagem a tempo (pode ter recusado o pedido ou estar sem cota)")
                destino.write_bytes(_baixar(img["src"]))
                return str(destino)
        finally:
            ia_web._devolver_foco_ao_whatsapp()
