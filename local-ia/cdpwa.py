# -*- coding: utf-8 -*-
"""Acesso minimo ao WhatsApp Web via Chrome de automacao (porta 9222)."""
import json, itertools, http.client, time, websocket

HOST, PORT = "127.0.0.1", 9222
_ids = itertools.count(1)

def _aba_whatsapp():
    c = http.client.HTTPConnection(HOST, PORT, timeout=5)
    c.request("GET", "/json"); abas = json.loads(c.getresponse().read()); c.close()
    for a in abas:
        if a.get("type") == "page" and "web.whatsapp.com" in a.get("url", ""):
            return a["webSocketDebuggerUrl"]
    raise RuntimeError("Aba do WhatsApp Web nao encontrada no Chrome de automacao")

class WA:
    def __enter__(self):
        self.url = _aba_whatsapp()
        self.ws = websocket.create_connection(self.url, timeout=20, suppress_origin=True, max_size=16*1024*1024)
        self._garantir_janela()
        self._trazer_para_frente()
        self._limpar_lista()
        return self

    def _trazer_para_frente(self):
        """Com outras abas abertas (ChatGPT, Gemini...), a do WhatsApp pode ficar 'hidden' e os cliques falham: sempre ativa esta aba."""
        try:
            alvo = self.url.rstrip("/").split("/")[-1]
            self.cmd("Target.activateTarget", {"targetId": alvo})
            self.cmd("Page.bringToFront")
        except Exception:
            pass

    def _limpar_lista(self):
        """Lista de conversas sempre no estado normal: sem texto na busca (senao mostra resultados de busca) e rolada ao topo
        (rolada para baixo, o vigia nao via as conversas novas, que ficam no topo)."""
        try:
            self.js("""(function(){var i=document.querySelector('#side input');
              if(i && i.value){i.focus(); document.execCommand('selectAll'); document.execCommand('delete'); i.blur();}
              var p=document.querySelector('#pane-side'); if(p) p.scrollTop=0;})()""")
            time.sleep(0.4)
        except Exception:
            pass

    def _garantir_janela(self):
        """Janela MINIMIZADA = pagina 'hidden': o WhatsApp nao recebe cliques nem toca audio e o Jarvis para de responder.
        Se estiver minimizada, restaura e deixa FORA DA AREA VISIVEL (ninguem minimiza/fecha por engano; continua 'visible' pro Chrome)."""
        try:
            r = self.cmd("Browser.getWindowForTarget")
            if (r.get("bounds") or {}).get("windowState") == "minimized":
                self.cmd("Browser.setWindowBounds", {"windowId": r["windowId"], "bounds": {"windowState": "normal"}})
                self.cmd("Browser.setWindowBounds", {"windowId": r["windowId"],
                                                     "bounds": {"left": -2600, "top": 40, "width": 1280, "height": 900}})
        except Exception:
            pass  # nunca impede o uso normal
    def __exit__(self, *a):
        self.ws.close()
    def cmd(self, method, params=None):
        mid = next(_ids)
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == mid:
                if "error" in m: raise RuntimeError(f"{method}: {m['error']}")
                return m.get("result", {})
    def js(self, expr):
        r = self.cmd("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True})
        if r.get("exceptionDetails"): raise RuntimeError(str(r["exceptionDetails"])[:300])
        return r.get("result", {}).get("value")
