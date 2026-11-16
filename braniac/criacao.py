# -*- coding: utf-8 -*-
"""CRIAR IMAGEM / VIDEO pelo conselho de IAs (25/10/2026, pedido do Dono):
1) o Dono pede normalmente; 2) mini-reuniao: o ChatGPT (ou o Grok, se o ChatGPT falhar) escreve o 1o prompt; 3) o Gemini MELHORA o prompt;
4) o Gemini gera a imagem (com as imagens de exemplo do Dono como contexto: descritas pelo Ollama e enviadas junto);
5) se acabou a cota do Gemini -> ChatGPT gera pelo site; acabou -> Grok; acabou -> Ollama local (so se houver modelo de imagem; hoje o Ollama so gera
imagem no macOS) -> Pollinations (gratis, sem referencias). Video: so a reuniao do prompt (nao ha gerador de video gratis ligado): o prompt pronto vai ao Dono.
Nada de dado pessoal sai do PC: pedido sensivel e barrado; imagens de exemplo sao lidas localmente (Ollama) e so seguem ao Gemini se o Dono as indicou."""
import base64
import json
import re
import threading
import time
from pathlib import Path

from . import store

DADOS = store.DATA
EXEMPLOS = DADOS / "exemplos"          # pasta padrao das imagens de exemplo do Dono
CRIACOES = DADOS / "criacoes"          # registro de cada criacao (reuniao, motor, caminho): alimenta o relatorio da manha
LIMITE_RE = re.compile(r"(?i)limite|limit reached|reached (?:your|the) (?:daily )?limit|too many|daily limit|upgrade|volte (?:mais )?tarde|try again (?:later|tomorrow)|attempt limit|excedeu")
EXT_IMG = {".jpg", ".jpeg", ".png", ".webp"}
ESTADO = {"rodando": False, "pedido": ""}


class SemCriacao(RuntimeError):
    pass


def _limpar_prompt(t):
    t = re.sub(r"(?s)```.*?\n|```", "", str(t or "")).strip()
    t = re.sub(r"^(?:prompt|improved prompt|final prompt)\s*[:\-]\s*", "", t, flags=re.I).strip().strip('"“”')
    return t[:1800]


def referencias(nomes=None, maximo=3):
    """[(caminho, bytes)] das imagens de exemplo: as citadas (nome/parte do nome/caminho) ou, se nenhuma, as mais recentes de data/exemplos."""
    from . import wpp_arquivo
    caminhos = []
    for n in (nomes or []):
        try:
            caminhos.append(Path(wpp_arquivo.resolver_caminho(n)))
        except wpp_arquivo.ArquivoErro:
            continue
    if not caminhos and EXEMPLOS.exists():
        caminhos = sorted((p for p in EXEMPLOS.iterdir() if p.suffix.lower() in EXT_IMG), key=lambda p: -p.stat().st_mtime)
    return [(p, p.read_bytes()) for p in caminhos if p.suffix.lower() in EXT_IMG and p.stat().st_size < 12_000_000][:maximo]


def descrever_referencias(refs, descrever=None):
    """Estilo/conteudo de cada imagem de exemplo, lido LOCALMENTE (Ollama primeiro). So o texto segue para as IAs da internet."""
    from . import imagem
    descrever = descrever or imagem.descrever
    out = []
    for p, dados in refs:
        try:
            out.append(f"{p.name}: " + descrever(dados, "Descreva em portugues o ESTILO visual desta imagem de exemplo (cores, composicao, tipo de arte, elementos principais), em 3 frases.", 150))
        except Exception:
            continue
    return out


# ---- mini-reuniao do prompt ----
def prompt_inicial(pedido, contexto, perguntar):
    base = ("Voce e especialista em prompts para geradores de imagem/video. Escreva UM prompt detalhado, em INGLES, para este pedido do cliente: "
            f"\"{pedido}\". " + (f"Imagens de exemplo que ele quer como referencia de estilo: {contexto}. " if contexto else "")
            + "Descreva sujeito, cena, estilo, iluminacao, cores, composicao e formato. Nao peca texto escrito dentro da imagem. "
              "Responda SOMENTE com o prompt, sem explicacao.")
    erros = []
    for ia in ("chatgpt", "grok"):
        try:
            p = _limpar_prompt(perguntar(ia, base))
            if len(p) > 30:
                return p, ia
        except Exception as e:
            erros.append(f"{ia}: {str(e)[:60]}")
    raise SemCriacao("nenhuma IA do conselho escreveu o prompt (" + "; ".join(erros) + ")")


def melhorar_prompt(prompt, pedido, contexto, melhorar_gemini):
    ped = ("Melhore este prompt de geracao de imagem para ficar o mais fiel e bonito possivel: deixe mais especifico (sujeito, estilo, luz, lente, cores, composicao), "
           f"sem mudar a ideia do pedido original do cliente (\"{pedido}\"). " + (f"Referencias de estilo: {contexto}. " if contexto else "")
           + f"Responda SOMENTE com o prompt final em ingles.\n\nPROMPT ATUAL:\n{prompt}")
    try:
        novo = _limpar_prompt(melhorar_gemini(ped))
        return (novo, "gemini") if len(novo) > 30 else (prompt, "(sem melhoria)")
    except Exception:
        return prompt, "(sem melhoria)"


def _gemini_texto(pergunta):
    from . import imagem
    import requests
    corpo = {"contents": [{"parts": [{"text": pergunta}]}], "generationConfig": {"temperature": 0.7, "maxOutputTokens": 900}}
    for modelo in imagem.MODELOS_VISAO:
        try:
            r = imagem._post(modelo, corpo, 60)
        except (requests.RequestException, imagem.SemImagem):
            continue
        if r.status_code == 200:
            t = " ".join(p.get("text", "") for p in imagem._partes(r)).strip()
            if t:
                return t
    from . import ia_web
    return ia_web.perguntar("gemini", pergunta)    # sem cota na API: pela aba logada do Gemini


# ---- motores de geracao ----
IMGS_JS = ("JSON.stringify([...document.querySelectorAll('main img, [role=main] img, article img')].filter(i=>i.complete&&i.naturalWidth>=300&&i.naturalHeight>=300)"
           ".map(i=>i.currentSrc||i.src))")
BAIXAR_JS = ("(async u=>{try{const r=await fetch(u,{credentials:'include'});const b=await r.blob();return await new Promise(ok=>{const f=new FileReader();f.onload=()=>ok(f.result);f.readAsDataURL(b)})}"
             "catch(e){const i=[...document.images].find(x=>(x.currentSrc||x.src)===u);const c=document.createElement('canvas');c.width=i.naturalWidth;c.height=i.naturalHeight;c.getContext('2d').drawImage(i,0,0);return c.toDataURL('image/png')}})(%s)")


def gerar_pelo_site(site, prompt, timeout_s=300):
    """ChatGPT ou Grok (aba logada do Chrome do Braniac): pede a imagem e baixa a que aparecer. Levanta SemCriacao (inclusive 'limite')."""
    from . import ia_web, whatsapp
    with whatsapp.LOCK:
        try:
            return _gerar_pelo_site(site, prompt, timeout_s)
        finally:
            ia_web._devolver_foco_ao_whatsapp()


def _gerar_pelo_site(nome, prompt, timeout_s):
    from . import ia_web
    site = ia_web.SITES[nome]
    pedido = f"Gere uma imagem (apenas a imagem, sem perguntas) com este prompt: {prompt}"
    try:
        with ia_web._Aba(site) as a:
            a.cmd("Target.activateTarget", {"targetId": a.url.rstrip("/").split("/")[-1]})
            a.cmd("Page.bringToFront")
            a.cmd("Page.navigate", {"url": site["nova"]})
            time.sleep(5)
            for _ in range(10):
                est = json.loads(a.js(ia_web._estado_js(site)))
                if est["caixa"] and est["n"] == 0:
                    break
                time.sleep(1)
            if est["deslogado"] or not est["caixa"]:
                raise SemCriacao(f"{nome}: deslogado")
            antes = set(json.loads(a.js(IMGS_JS)))
            a.js(f"document.querySelector({json.dumps(site['entrada'])}).focus()")
            a.cmd("Input.insertText", {"text": pedido})
            time.sleep(0.8)
            if site["enviar"]:
                a.js(f"(function(){{var b=document.querySelector({json.dumps(site['enviar'])}); if(b) b.click()}})()")
            else:
                a.enter()
            alvo_id = a.url.rstrip("/").split("/")[-1]
            fim = time.time() + timeout_s
            while time.time() < fim:
                time.sleep(3)
                try:
                    a.cmd("Target.activateTarget", {"targetId": alvo_id})
                    a.cmd("Page.bringToFront")
                except ia_web.IAWebErro:
                    pass
                novas = [u for u in json.loads(a.js(IMGS_JS)) if u not in antes]
                if novas:
                    time.sleep(4)       # a imagem termina de carregar/aparecer em alta resolucao
                    novas = [u for u in json.loads(a.js(IMGS_JS)) if u not in antes] or novas
                    data = a.js(BAIXAR_JS % json.dumps(novas[-1]))
                    if data and data.startswith("data:image"):
                        return base64.b64decode(data.split(",", 1)[1])
                texto = a.js(ia_web._ultima_js(site)) or ""
                if texto and LIMITE_RE.search(texto) and not novas:
                    raise SemCriacao(f"{nome}: limite de imagens do dia")
            raise SemCriacao(f"{nome}: tempo esgotado esperando a imagem")
    except ia_web.IAWebErro as e:
        raise SemCriacao(f"{nome}: {str(e)[:80]}")


def gerar_local(prompt):
    """Ollama local: so se houver modelo de imagem instalado (x/z-image-turbo, x/flux2-klein). No Windows/GTX 1650 nao ha: levanta SemCriacao."""
    from . import imagem
    modelos = [m for m in imagem._instalados() if m.startswith(("x/z-image", "x/flux"))]
    if not modelos:
        raise SemCriacao("ollama sem modelo de imagem (so existe no macOS e pede ~13 GB de VRAM)")
    raise SemCriacao("ollama com modelo de imagem instalado, mas a geracao local ainda nao foi ligada")


def criar(pedido, refs_nomes=None, avisar=None, perguntar=None, melhorar=None, motores=None, descrever=None):
    """Roda a reuniao e gera. Devolve {'caminho','motor','prompt','reuniao':[...]} ou levanta SemCriacao (com o prompt pronto no texto)."""
    from . import ia_web, imagem
    from .router import SENSIVEL, carregar_env, tem_dado_real
    carregar_env()      # chave do Gemini (no servidor ja esta; aqui garante em execucao avulsa)
    if SENSIVEL.search(pedido) or tem_dado_real(pedido):
        raise SemCriacao("o pedido tem dado sensivel (cartao, CPF, senha...): nao mando para IA da internet")
    av = avisar or (lambda t: None)
    reuniao = []
    refs = referencias(refs_nomes)
    ctx = " | ".join(descrever_referencias(refs, descrever)) if refs else ""
    if refs:
        av(f"🖼 Li {len(refs)} imagem(ns) de exemplo (Ollama, no seu PC).")
    p1, quem = prompt_inicial(pedido, ctx, perguntar or ia_web.perguntar)
    reuniao.append((quem, p1))
    av(f"🗣 {quem} escreveu o 1º prompt. Agora o Gemini melhora.")
    p2, quem2 = melhorar_prompt(p1, pedido, ctx, melhorar or _gemini_texto)
    reuniao.append((quem2, p2))
    imagens = [d for _, d in refs]
    ordem = motores or [
        ("gemini", lambda: imagem.gerar(p2, referencias=imagens, pollinations=False)[0]),
        ("chatgpt", lambda: gerar_pelo_site("chatgpt", p2)),
        ("grok", lambda: gerar_pelo_site("grok", p2)),
        ("ollama", lambda: gerar_local(p2)),
        ("pollinations", lambda: imagem._gerar_pollinations(p2, 90)[0]),
    ]
    falhas = []
    for nome, fn in ordem:
        try:
            dados = fn()
        except (SemCriacao, imagem.SemImagem) as e:
            falhas.append(f"{nome}: {str(e)[:70]}")
            av(f"↪ {nome} não deu ({str(e)[:50]}); tentando o próximo.")
            continue
        pasta = CRIACOES
        pasta.mkdir(parents=True, exist_ok=True)
        ext = ".png" if dados[:4] == b"\x89PNG" else ".jpg"
        caminho = pasta / f"{time.strftime('%Y%m%d_%H%M%S')}{ext}"
        caminho.write_bytes(dados)
        res = {"caminho": str(caminho), "motor": nome, "prompt": p2, "reuniao": reuniao, "falhas": falhas, "pedido": pedido}
        (pasta / (caminho.stem + ".json")).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        return res
    raise SemCriacao("nenhum motor gerou a imagem (" + "; ".join(falhas) + f"). Prompt pronto: {p2}")


def criar_video(pedido, refs_nomes=None, avisar=None, perguntar=None, melhorar=None, descrever=None):
    """Video: faz a reuniao do prompt; nao ha gerador de video gratis ligado, entao devolve o prompt pronto."""
    from . import ia_web
    from .router import SENSIVEL, tem_dado_real
    if SENSIVEL.search(pedido) or tem_dado_real(pedido):
        raise SemCriacao("o pedido tem dado sensivel: nao mando para IA da internet")
    refs = referencias(refs_nomes)
    ctx = " | ".join(descrever_referencias(refs, descrever)) if refs else ""
    p1, quem = prompt_inicial("VIDEO curto: " + pedido, ctx, perguntar or ia_web.perguntar)
    p2, _ = melhorar_prompt(p1, pedido, ctx, melhorar or _gemini_texto)
    return {"prompt": p2, "reuniao": [(quem, p1), ("gemini", p2)], "motor": None}


def entregar(res, enviar_arquivo=None, enviar_texto=None):
    from . import wpp_arquivo
    envia_a = enviar_arquivo or (lambda c, leg: wpp_arquivo.enviar_arquivo("Eu", c, leg))
    envia_t = enviar_texto or (lambda t: wpp_arquivo.enviar_texto("Eu", t))
    if res.get("caminho"):
        envia_a(res["caminho"], f"Imagem pronta (feita por {res['motor']}). Prompt: {res['prompt'][:300]}")
    else:
        envia_t("Prompt de vídeo pronto (cole no gerador que você usa, ex.: Gemini/Veo, Kling, Seedance):\n\n" + res["prompt"])


def em_segundo_plano(tipo, pedido, refs_nomes, avisar, enviar_arquivo=None, enviar_texto=None, fn=None):
    """Roda criar/criar_video sem travar o chat; avisa o andamento e entrega no WhatsApp do Dono."""
    if ESTADO["rodando"]:
        return "Já estou criando outra coisa: " + ESTADO["pedido"][:60] + ". Aguarde terminar."
    ESTADO.update(rodando=True, pedido=pedido)

    def roda():
        try:
            res = (fn or (criar if tipo == "imagem" else criar_video))(pedido, refs_nomes, avisar)
            entregar(res, enviar_arquivo, enviar_texto)
            (avisar or (lambda t: None))("✅ " + ("Imagem criada por " + res["motor"] if res.get("caminho") else "Prompt de vídeo pronto") + " e enviada no seu WhatsApp.")
        except Exception as e:
            (avisar or (lambda t: None))("⚠️ Não consegui criar: " + str(e)[:300])
        finally:
            ESTADO.update(rodando=False, pedido="")
    threading.Thread(target=roda, daemon=True).start()
    return ("Comecei: o conselho (ChatGPT/Grok → Gemini) vai montar o melhor prompt e eu gero a " + ("imagem" if tipo == "imagem" else "ideia do vídeo")
            + ". Pode demorar; te aviso e mando no WhatsApp.")
