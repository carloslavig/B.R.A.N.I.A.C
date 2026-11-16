# -*- coding: utf-8 -*-
"""Gmail SO LEITURA pela aba logada do Chrome do Braniac (28/10/2026): sem OAuth, entao nao expira em 7 dias. Le remetente e assunto da caixa de entrada
(aba Principal); nunca abre e-mail, nunca responde, nunca clica. A aba abre sob demanda e fecha ao terminar."""
import time

from . import ia_web

URL = "https://mail.google.com/mail/u/0/#inbox"
JS = """(()=>{const l=[...document.querySelectorAll('tr.zA')].slice(0,%d);
return l.map(r=>{const s=r.querySelector('.yX .yW span[email], .yP, .zF');const a=r.querySelector('.bog, .y6 span');
const t=r.querySelector('[data-legacy-thread-id]');
return {id:t?t.getAttribute('data-legacy-thread-id'):'', email:s?(s.getAttribute('email')||''):'', nome:s?(s.getAttribute('name')||s.textContent||''):'',
assunto:a?a.textContent:'', nao_lida:r.classList.contains('zE')}})})()"""


def caixa(n=30):
    """[{id, email, nome, assunto, nao_lida}] da caixa de entrada. Levanta ia_web.IAWebErro se o Gmail nao estiver logado/pronto."""
    with ia_web._Aba({"dominio": "mail.google.com", "nova": URL}) as a:
        try:
            for _ in range(20):
                url = a.js("location.href") or ""
                if "accounts.google.com" in url:
                    raise ia_web.IAWebErro("Gmail pediu login (sessão do Google caiu no Chrome do Braniac)")
                linhas = a.js(JS % n) or []
                if linhas:
                    return [l for l in linhas if l.get("id")]
                time.sleep(1.5)
            raise ia_web.IAWebErro("caixa de entrada do Gmail não carregou")
        finally:
            ia_web._devolver_foco_ao_whatsapp()
