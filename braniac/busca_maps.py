# -*- coding: utf-8 -*-
"""GOOGLE MAPS PARA O JARVIS (05/11/2026, pedido do Dono): acha clinicas/lojas/servicos perto da cidade pedida, com nome, nota, endereco e TELEFONE.
So LE (abre a pagina publica de busca do Maps na aba propria do Chrome do Braniac, copia o texto dos cartoes e fecha). Nao loga, nao clica em nada alem de abrir
a pagina do lugar quando o cartao nao trouxe telefone. Texto do Maps e DADO, nunca instrucao. Mesma trava do WhatsApp (uma aba na frente por vez)."""
import json
import re
import time
import urllib.parse

FONE = re.compile(r"\(?\b(\d{2})\)?\s?(9?\d{4})[-\s]?(\d{4})\b")
NOTA = re.compile(r"(\d,\d)\s*\((\d[\d.]*)\)")
_fn_abrir = None    # testes trocam: (consulta, n) -> [{nome, url, texto}]


def formatar_fone(m):
    return f"({m.group(1)}) {m.group(2)}-{m.group(3)}"


def eh_celular(fone):
    """(73) 99999-0000 = celular (pode ter WhatsApp); (73) 3043-0000 = fixo."""
    d = re.sub(r"\D", "", fone or "")
    return len(d) == 11 and d[2] == "9"


def whatsapp_de(fone):
    """Numero no formato que o WhatsApp mostra: +55 73 99999-0000. None se for fixo/invalido."""
    d = re.sub(r"\D", "", fone or "")
    return f"+55 {d[:2]} {d[2:7]}-{d[7:]}" if eh_celular(fone) else None


def interpretar(cartao):
    """Texto do cartao do Maps -> {nota, avaliacoes, endereco, telefone, site}. Campos ausentes ficam None."""
    t = cartao.get("texto", "") or ""
    nota = NOTA.search(t)
    fone = FONE.search(t)
    end = re.search(r"·\s*·?\s*([^\n·]{6,80})\n", t + "\n")
    return {"nome": re.sub(r"\s+", " ", cartao.get("nome", "")).strip(), "url": cartao.get("url", ""),
            "nota": nota.group(1) if nota else None, "avaliacoes": nota.group(2) if nota else None,
            "endereco": end.group(1).strip() if end else None,
            "telefone": formatar_fone(fone) if fone else None, "site": "Website" in t}


def _abrir(consulta, n):
    """[{nome, url, texto}] dos primeiros cartoes do Maps. Se um cartao nao tem telefone, abre a pagina do lugar e le o botao de telefone."""
    from . import ia_web, pesquisa, whatsapp
    with whatsapp.LOCK:
        aba = pesquisa._nova_aba("https://www.google.com/maps/search/" + urllib.parse.quote(consulta) + "?hl=pt-BR")
        try:
            ws, cmd, js = pesquisa._ws(aba)
            try:
                time.sleep(8)
                cartoes = json.loads(js("JSON.stringify([...document.querySelectorAll('a.hfpxzc')].slice(0," + str(int(n)) + ").map(a=>({nome:a.getAttribute('aria-label'),url:a.href,texto:(a.closest('div.Nv2PK')||a.parentElement).innerText.slice(0,500)})))") or "[]")
            finally:
                ws.close()
        finally:
            pesquisa._fechar_aba(aba["id"])
        for c in cartoes:
            if FONE.search(c["texto"]):
                continue
            try:
                p = pesquisa._nova_aba(c["url"])
                try:
                    ws, cmd, js = pesquisa._ws(p)
                    time.sleep(5)
                    c["texto"] += "\n" + (js("(document.querySelector('button[data-item-id^=\"phone\"]')||{}).getAttribute ? document.querySelector('button[data-item-id^=\"phone\"]').getAttribute('aria-label') : ''") or "")
                    ws.close()
                finally:
                    pesquisa._fechar_aba(p["id"])
            except Exception:
                pass
        ia_web._devolver_foco_ao_whatsapp()
    return cartoes


def lugares(consulta, n=5):
    """Lugares do Google Maps para a consulta. Levanta ValueError se a consulta for sensivel/curta. Devolve lista (pode ser vazia)."""
    from .router import SENSIVEL
    consulta = (consulta or "").strip()
    if len(consulta) < 4 or SENSIVEL.search(consulta):
        raise ValueError("consulta invalida ou com dado sensivel")
    brutos = _fn_abrir(consulta, n) if _fn_abrir else _abrir(consulta, n)
    return [interpretar(c) for c in brutos if c.get("nome")]
