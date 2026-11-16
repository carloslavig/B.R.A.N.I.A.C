# -*- coding: utf-8 -*-
"""EMPRESA DE MARKETING (29/10/2026, pedido do Dono): o 3o andar do Braniac, "Fornalha" (nome e equipe do conselho de IAs, data/conselho_mkt.txt).
Tudo gerado por IA a partir de FOTOS REAIS. Fluxo de cada pedido: novo -> prompt (Vega/Cena) -> gerado (Gemini; Meta AI de reserva) -> legendado (Verso)
-> revisado (Cris) -> entregue (Pasta: sobe para o Google Drive). Ravi planeja a pauta do dia; Ponte recebe os pedidos do Jarvis (WhatsApp).
Abas do Gemini/Meta/Drive abrem sob demanda e fecham no fim (ia_web._Aba) para poupar RAM. Travas: nada e publicado (so entregue no Drive);
nada de dado pessoal no prompt; preco/horario so se vierem do briefing; teto de passos por dia (equipe.json)."""
import json
import re
import threading
import time
from datetime import datetime
from pathlib import Path

from . import fornalha_estudio as E
from .store import DATA

PASTA = DATA / "empresa_mkt"
SAIDA = PASTA / "saida"
EQUIPE_JSON = PASTA / "equipe.json"
PEDIDOS_JSON = PASTA / "pedidos.json"
_lock = threading.RLock()
SEGREDO = re.compile(r"(?i)\bsenha\b|\bcvv\b|\bcpf\b|api[_ -]?key|secret|\btoken\b|cart[aã]o|\bpix\b")
TIPOS = ("imagem", "carrossel", "video", "stories")
CALENDARIO = {0: ["imagem"], 1: ["video"], 2: ["carrossel"], 3: ["video"], 4: ["imagem", "imagem"], 5: ["imagem"], 6: ["imagem"]}   # 0 = segunda (conselho)


def _ler(p, padrao):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return padrao


def _gravar(p, dado):
    PASTA.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(dado, ensure_ascii=False, indent=1), encoding="utf-8")
    for i in range(10):          # Windows: leitor (sauraki/antivirus) segura o arquivo por instantes
        try:
            tmp.replace(p)
            return
        except PermissionError:
            time.sleep(0.5)
    p.write_text(tmp.read_text(encoding="utf-8"), encoding="utf-8")


def config():
    return _ler(EQUIPE_JSON, {"empresa": "Fornalha", "agentes": [], "clientes": {}, "limites": {}})


def agentes():
    return config().get("agentes", [])


def nomes():
    return [a["nome"] for a in agentes()]


def limite(chave, padrao):
    try:
        return max(0, int(config().get("limites", {}).get(chave, padrao)))
    except (TypeError, ValueError):
        return padrao


def _hoje():
    return datetime.now().strftime("%Y-%m-%d")


def _uso(chave, somar=False):
    d = _ler(PASTA / "uso.json", {})
    v = d.get(_hoje(), {})
    if somar:
        v[chave] = v.get(chave, 0) + 1
        _gravar(PASTA / "uso.json", {_hoje(): v})
    return v.get(chave, 0)


def _pedidos():
    return _ler(PEDIDOS_JSON, [])


def _chave_cliente(cliente):
    import unicodedata
    c = unicodedata.normalize("NFKD", cliente or "").encode("ascii", "ignore").decode().lower().strip()
    return next((k for k in config().get("clientes", {}) if c and (k in c or c in k)), c)


def _ia(sistema, prompt):
    from .router import Router
    global _router
    if _router is None:
        _router = Router()
    return _router.responder_neutro(sistema, prompt)[0]


_router = None
_gerar_imagem_fn = None     # testes trocam por funcoes falsas
_gerar_video_fn = None
_drive_fn = None


def abrir(cliente, tipo, briefing="", foto=""):
    """Ponte: novo pedido. foto = caminho de uma foto REAL (a que o Jarvis baixou do WhatsApp ou da pasta do cliente)."""
    tipo = (tipo or "imagem").lower().replace("í", "i").replace("é", "e")
    tipo = "carrossel" if tipo.startswith("carro") else tipo
    if tipo not in TIPOS:
        return None, f"Tipo inválido ({'/'.join(TIPOS)})."
    if SEGREDO.search(briefing or ""):
        return None, "Pedido recusado: tem palavra de segredo/dado pessoal (senha, token, CPF, cartão, Pix)."
    ck = _chave_cliente(cliente)
    if ck not in config().get("clientes", {}):
        return None, f"Cliente «{cliente}» ainda não está cadastrado na Fornalha."
    with _lock:
        ps = _pedidos()
        p = {"id": f"P{len(ps) + 1:03d}", "cliente": ck, "tipo": tipo, "briefing": (briefing or "").strip()[:800], "foto": foto or "", "estado": "novo",
             "tentativas": 0, "arquivos": [], "legenda": "", "drive": [], "historico": [], "criado": time.time()}
        ps.append(p)
        _gravar(PEDIDOS_JSON, ps)
    return p, f"{p['id']} aberto: {tipo} para {ck}"


def _hist(p, quem, txt):
    p["historico"].append({"ts": time.time(), "quem": quem, "txt": txt[:300]})
    del p["historico"][:-12]


def _foto_base(ck):
    """Foto real do cliente menos usada (rodizio), da pasta configurada."""
    c = config()["clientes"][ck]
    fotos = []
    for d in [c.get("fotos", "")] + c.get("fotos_extra", []):
        pasta = Path(d)
        if pasta.is_dir():
            fotos += [f for f in sorted(pasta.iterdir()) if f.suffix.lower() in (".jpg", ".jpeg")]
    if not fotos:
        return ""
    usadas = [x["foto"] for x in _pedidos()]
    return str(min(fotos, key=lambda f: usadas.count(str(f))))


def planejar(agora=None):
    """Ravi: 1x por dia abre os pedidos da pauta (calendario semanal do conselho), no maximo `pedidos_dia`."""
    agora = agora or datetime.now()
    if _ler(PASTA / "pauta.json", {}).get("dia") == _hoje():
        return []
    _gravar(PASTA / "pauta.json", {"dia": _hoje()})
    abertos = []
    for ck, c in config().get("clientes", {}).items():
        for tipo in CALENDARIO[agora.weekday()][:limite("pedidos_dia", 3)]:
            tema = _ia("Você é o Ravi, planejador de pauta de marketing. Responda só uma linha, em português do Brasil.",
                       f"Dê a ideia do post de hoje ({tipo}) para: {c['marca']}. Uma linha, sem preço nem horário.")
            p, _ = abrir(ck, tipo, (tema or "post do dia").strip()[:300], _foto_base(ck))
            if p:
                abertos.append(p["id"])
    return abertos


def _descrever_foto(foto):
    if not foto or not Path(foto).exists():
        return ""
    try:
        from . import imagem
        return imagem.descrever(Path(foto).read_bytes(), "Descreva em 3 linhas a comida/produto e o cenário desta foto, para recriar a imagem fielmente.")
    except Exception:
        return ""


def _fazer_prompt(p):
    c = config()["clientes"][p["cliente"]]
    quem = "Cena" if p["tipo"] == "video" else "Vega"
    formato = {"imagem": "imagem de feed vertical 4:5", "carrossel": "imagem de carrossel vertical 4:5 (uma de 3)", "video": "vídeo curto vertical 9:16 de 6 a 8 segundos", "stories": "imagem de stories vertical 9:16"}[p["tipo"]]
    desc = _descrever_foto(p["foto"])
    extra = ""
    est = E.estilo(PASTA, p["cliente"])
    if est:
        extra += f"\nLivro de estilo do cliente (siga):\n{est}"
    ganhos = E.melhores(PASTA, p["cliente"], p["tipo"])
    if ganhos:
        extra += "\nPrompts que já deram certo para este cliente (mesmo nível de detalhe, ideia nova):\n- " + "\n- ".join(g[:500] for g in ganhos)
    if p["tipo"] == "video":
        extra += "\n" + E.ROTEIRO_VIDEO
    txt = _ia(f"Você é {quem}, diretor(a) de arte de marketing de comida. Escreva UM prompt completo e detalhado em português para o Gemini gerar {formato}. "
              "Descreva composição, luz, cores, enquadramento e movimento (se vídeo). Preserve fielmente o produto da foto de referência. "
              "Sem texto escrito dentro da arte, sem preços, sem marcas de terceiros. Responda só o prompt.",
              f"Marca: {c['marca']}\nPedido: {p['briefing']}\nFoto real de referência: {desc or 'anexada'}{extra}")
    if not txt or len(txt) < 30:
        raise RuntimeError("não consegui montar o prompt")
    p["prompt"] = txt.strip()[:2200]
    _hist(p, quem, "prompt pronto")


def _gerar_arquivos(p):
    """Imagem/carrossel: Gemini (aba logada), Meta AI se o Gemini falhar. Vídeo: Gemini; sem recurso/cota, o erro fica no histórico."""
    pasta = SAIDA / p["cliente"].replace(" ", "-") / p["id"]
    n = 3 if p["tipo"] == "carrossel" else 1
    ref = p["foto"] if p["foto"] and Path(p["foto"]).exists() else None
    arqs = []
    for i in range(1, n + 1):
        prompt = p["prompt"] + (f"\n\nCorrija o defeito da versão anterior: {p['ajuste']}." if p.get("ajuste") else "") + (f"\n\nEsta é a imagem {i} de {n} de um carrossel, no mesmo estilo." if n > 1 else "")
        destino = pasta / f"{p['id']}_{i}.png"
        if p["tipo"] == "video":
            arqs.append((_gerar_video_fn or _video_gemini)(prompt, pasta / f"{p['id']}.mp4", ref))
            continue
        try:
            if _gerar_imagem_fn:
                arqs.append(_gerar_imagem_fn(prompt, destino, ref))
            else:
                from . import ia_img
                arqs.append(ia_img.gerar(prompt, destino, referencia=ref))
        except Exception as e:
            _hist(p, "Vega", f"Gemini falhou ({str(e)[:60]}); tentando Meta AI")
            from . import ia_web
            m = Path(ia_web.gerar_imagem(prompt)[0])
            destino.parent.mkdir(parents=True, exist_ok=True)
            alvo = destino.with_suffix(".jpg")
            alvo.write_bytes(m.read_bytes())
            arqs.append(str(alvo))
    p["arquivos"] = arqs


JS_VIDEO = "JSON.stringify([...document.querySelectorAll('video')].map(v=>v.currentSrc||v.src).filter(Boolean))"


def _video_gemini(prompt, destino, ref=None):
    """Pede o vídeo ao Gemini (aba logada, abre e fecha) e baixa o <video> que aparecer. Sem cota/recurso: levanta RuntimeError."""
    import base64
    from . import ia_img, ia_web, whatsapp
    destino.parent.mkdir(parents=True, exist_ok=True)
    site = ia_web.SITES["gemini"]
    with whatsapp.LOCK:
        try:
            with ia_web._Aba(site) as a:
                a.cmd("Target.activateTarget", {"targetId": a.url.rstrip("/").split("/")[-1]})
                a.cmd("Page.bringToFront")
                a.cmd("Page.navigate", {"url": site["nova"]})
                time.sleep(5)
                if ref:
                    ia_img._anexar(a, ref)
                a.js(f"document.querySelector({json.dumps(site['entrada'])}).focus()")
                a.cmd("Input.insertText", {"text": "Gere um vídeo (apenas o vídeo): " + prompt})
                time.sleep(1)
                a.js(f"(function(){{var b=document.querySelector({json.dumps(site['enviar'])}); if(b) b.click()}})()")
                fim = time.time() + 420
                while time.time() < fim:
                    time.sleep(5)
                    vs = json.loads(a.js(JS_VIDEO) or "[]")
                    if vs:
                        b64 = a.js("fetch(%s).then(r=>r.blob()).then(b=>new Promise(o=>{var f=new FileReader();f.onload=()=>o(f.result.split(',')[1]);f.readAsDataURL(b)}))" % json.dumps(vs[-1]))
                        if b64:
                            destino.write_bytes(base64.b64decode(b64))
                            return str(destino)
        finally:
            ia_web._devolver_foco_ao_whatsapp()
    raise RuntimeError("o Gemini não devolveu vídeo (sem cota ou sem o recurso)")


def _acabar(p):
    """Matiz (editor + colorista local): corte no formato do post, cor, nitidez; vídeo ganha loudness e capa. O bruto fica ao lado."""
    ok = []
    for a in p["arquivos"]:
        if a.lower().endswith((".png", ".jpg", ".jpeg")):
            ok.append(E.acabar_imagem(a, p["tipo"]))
        elif a.lower().endswith(".mp4"):
            ok.append(E.acabar_video(a))
    _hist(p, "Matiz", "acabamento local: " + ("; ".join(ok) or "nada a fazer"))


def _legenda(p):
    c = config()["clientes"][p["cliente"]]
    txt = _ia("Você é o Verso, redator de marketing. Escreva a legenda de Instagram em português do Brasil: 2 a 4 linhas, 1 chamada para ação e 5 hashtags. "
              "NUNCA cite preço, horário ou sabor que não esteja no pedido.", f"Marca: {c['marca']}\nPedido: {p['briefing']}")
    if not re.search(r"R\$\s*\d", p["briefing"]):
        txt = re.sub(r"R\$\s*[\d.,]+", "", txt or "")      # preço que não veio do briefing é inventado: tira
    txt, tirados = E.tirar_promessas((txt or "").strip(), p["briefing"])
    p["legenda"] = txt[:900]
    _hist(p, "Verso", "legenda pronta" + (f" (tirei promessas sem autorização: {', '.join(tirados)[:80]})" if tirados else ""))


def _revisar(p):
    """Cris: arquivo existe e passa no placar 0-100 (resolução, formato, brilho, nitidez, contraste; vídeo: duração, altura, 9:16). Mínimo = `nota_minima`."""
    notas_p = []
    for a in p["arquivos"]:
        f = Path(a)
        if not f.exists() or f.stat().st_size < 10_000:
            return False, f"{f.name} ausente ou vazio"
        if f.suffix.lower() in (".png", ".jpg", ".jpeg"):
            nota, avisos = E.placar_imagem(f, p["tipo"])
        elif f.suffix.lower() == ".mp4":
            nota, avisos = E.placar_video(f)
        else:
            continue
        notas_p.append(nota)
        if nota < limite("nota_minima", 75):
            return False, f"{f.name} nota {nota}: " + "; ".join(avisos)
    p["nota"] = min(notas_p) if notas_p else 100
    return True, f"nota {p['nota']}"


def _nomear(p):
    """Pasta: nomes data_cliente_formato_n e a legenda em .txt ao lado."""
    novos = []
    for i, a in enumerate(p["arquivos"], 1):
        f = Path(a)
        novo = f.with_name(f"{datetime.now():%Y%m%d}_{p['cliente'].replace(' ', '-')}_{p['tipo']}_{i}{f.suffix}")
        f.replace(novo)
        novos.append(str(novo))
    if p["legenda"]:
        leg = Path(novos[0]).with_name(Path(novos[0]).stem + "_legenda.txt")
        leg.write_text(p["legenda"], encoding="utf-8")
        novos.append(str(leg))
    p["arquivos"] = novos


JS_ACHAR = """(function(re,sel){var e=[...document.querySelectorAll(sel)].filter(x=>re.test((x.getAttribute('aria-label')||x.innerText||'').trim())&&x.offsetParent!==null)[0];
  if(!e) return null; var r=e.getBoundingClientRect(); return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2}); })(%s,%s)"""


def _clicar(a, regex, seletor="button,[role=button],[role=menuitem],[role=option]"):
    """Clique 'de verdade' (mouse do CDP): o seletor de arquivos do Chrome exige gesto do usuario."""
    pos = a.js(JS_ACHAR % (regex, json.dumps(seletor)))
    if not pos:
        raise RuntimeError("não achei o botão do Drive: " + regex)
    p = json.loads(pos)
    for tipo in ("mouseMoved", "mousePressed", "mouseReleased"):
        a.cmd("Input.dispatchMouseEvent", {"type": tipo, "x": p["x"], "y": p["y"], "button": "left", "clickCount": 1})


def _escolher_arquivos(a, caminhos):
    """Novo > Upload de arquivo; intercepta o seletor de arquivos do Chrome e entrega os caminhos."""
    achado = []
    recv_original = a.ws.recv

    def recv():        # a.cmd descarta eventos; aqui guardamos o do seletor de arquivos
        m = recv_original()
        if '"Page.fileChooserOpened"' in m:
            achado.append(json.loads(m)["params"]["backendNodeId"])
        return m
    a.ws.recv = recv
    a.cmd("Page.enable")
    a.cmd("Page.setInterceptFileChooserDialog", {"enabled": True})
    aberto = "[...document.querySelectorAll('[role=menuitem]')].some(b=>b.offsetParent!==null&&/^(Upload de arquivo|File upload)/i.test(b.innerText.trim()))"
    for _ in range(4):      # o menu as vezes nao abre no 1o clique (pagina ainda carregando): so clica de novo se ainda estiver fechado
        if a.js(aberto):
            break
        _clicar(a, "/^(Novo|New)$/", "button")
        for _ in range(6):
            time.sleep(0.5)
            if a.js(aberto):
                break
    for _ in range(3):      # o item do menu so aceita o clique depois da animacao; repete se o seletor nao abrir
        time.sleep(1.5)
        if a.js(aberto):
            _clicar(a, "/^(Upload de arquivo|File upload)/i", "[role=menuitem]")
        for _ in range(8):
            a.cmd("Runtime.evaluate", {"expression": "1"})      # bombeia as mensagens do socket
            time.sleep(0.5)
            if achado:
                break
        if achado:
            break
    if achado:
        a.cmd("DOM.setFileInputFiles", {"files": caminhos, "backendNodeId": achado[0]})
        return
    raiz = a.cmd("DOM.getDocument", {"depth": -1, "pierce": True})["root"]["nodeId"]      # plano B: o input que o menu cria
    nos = a.cmd("DOM.querySelectorAll", {"nodeId": raiz, "selector": "input[type=file]"}).get("nodeIds", [])
    simples = [n for n in nos if "webkitdirectory" not in a.cmd("DOM.getAttributes", {"nodeId": n}).get("attributes", [])]
    if not (simples or nos):
        raise RuntimeError("o Drive não abriu o seletor de arquivos")
    a.cmd("DOM.setFileInputFiles", {"files": caminhos, "nodeId": (simples or nos)[0]})


def _drive_chrome(arquivos, pasta_id):
    """Sobe os arquivos para a pasta do Drive pela aba logada do Chrome do Braniac (abre e fecha a aba). RuntimeError se nao confirmar."""
    from . import ia_web, whatsapp
    site = {"dominio": "drive.google.com", "nova": f"https://drive.google.com/drive/folders/{pasta_id}", "fechar": True}
    with whatsapp.LOCK:
        janela = None
        try:
            with ia_web._Aba(site) as a:
                try:    # o seletor de arquivos so abre com a pagina "visivel": traz a janela para a tela durante o envio e a devolve depois
                    janela = a.cmd("Browser.getWindowForTarget")["windowId"]
                    a.cmd("Browser.setWindowBounds", {"windowId": janela, "bounds": {"windowState": "normal"}})
                    a.cmd("Browser.setWindowBounds", {"windowId": janela, "bounds": {"left": 60, "top": 40, "width": 1280, "height": 900}})
                except ia_web.IAWebErro:
                    pass
                a.cmd("Emulation.setFocusEmulationEnabled", {"enabled": True})
                a.cmd("Target.activateTarget", {"targetId": a.url.rstrip("/").split("/")[-1]})
                a.cmd("Page.bringToFront")
                a.cmd("Page.navigate", {"url": site["nova"]})
                time.sleep(8)
                if a.js("location.host.includes('accounts.google')"):
                    raise RuntimeError("Drive deslogado no Chrome do Braniac")
                try:
                    _escolher_arquivos(a, [str(Path(x).resolve()) for x in arquivos])
                    ultimo = Path(arquivos[-1]).name[:40]
                    for _ in range(60):
                        time.sleep(3)
                        if a.js(f"document.body.innerText.includes({json.dumps(ultimo)}) && /conclu|complete/i.test(document.body.innerText)"):
                            time.sleep(2)
                            return
                    raise RuntimeError("o Drive não confirmou o envio a tempo")
                finally:
                    try:    # janela volta para fora da area visivel (como o ia_web deixa)
                        if janela:
                            a.cmd("Browser.setWindowBounds", {"windowId": janela, "bounds": {"left": -2600, "top": 40, "width": 1280, "height": 900}})
                    except Exception:
                        pass
        finally:
            ia_web._devolver_foco_ao_whatsapp()


def _entregar(p):
    pasta_id = config()["clientes"][p["cliente"]].get("drive", {}).get(p["tipo"]) or config()["clientes"][p["cliente"]].get("drive", {}).get("imagem")
    _nomear(p)
    if not pasta_id:
        raise RuntimeError("cliente sem pasta no Drive")
    (_drive_fn or _drive_chrome)(p["arquivos"], pasta_id)
    p["drive"] = [Path(x).name for x in p["arquivos"]]
    _hist(p, "Pasta", "enviado ao Drive")
    E.guardar_vencedor(PASTA, p, p.get("nota", 0))


PASSOS = {"novo": "prompt", "prompt": "gerado", "gerado": "acabado", "acabado": "legendado", "legendado": "revisado", "revisado": "entregue"}


def avancar(p):
    est = p["estado"]
    if est == "novo":
        _fazer_prompt(p)
    elif est == "prompt":
        _gerar_arquivos(p)
        _hist(p, "Cena" if p["tipo"] == "video" else "Vega", f"{len(p['arquivos'])} arquivo(s) gerado(s)")
    elif est == "gerado":
        _acabar(p)
    elif est == "acabado":
        _legenda(p)
    elif est == "legendado":
        ok, motivo = _revisar(p)
        _hist(p, "Cris", motivo)
        if not ok:
            p["tentativas"] += 1
            p["ajuste"] = motivo[:160]
            E.registrar_desperdicio(PASTA, p, motivo)
            p["estado"] = "falhou" if p["tentativas"] >= 2 else "prompt"
            return f"{p['id']} reprovado pela Cris: {motivo}"
    elif est == "revisado":
        _entregar(p)
    p["estado"] = PASSOS[est]
    return f"{p['id']} → {p['estado']}"


def trabalhar(maximo=1, ignorar_teto=False):
    """Avanca ate `maximo` passos (um pedido por vez), respeitando o teto diario."""
    trava = PASTA / ".trabalhando"
    try:
        if trava.exists() and time.time() - trava.stat().st_mtime < 1500:
            return []
        PASTA.mkdir(parents=True, exist_ok=True)
        trava.write_text(str(time.time()))
    except OSError:
        pass
    feitos = []
    try:
        for _ in range(maximo):
            if not ignorar_teto and _uso("passos") >= limite("passos_dia", 8):
                break
            p = next((x for x in _pedidos() if x["estado"] in PASSOS), None)
            if not p:
                break
            try:
                feitos.append(avancar(p))
            except Exception as e:
                p["tentativas"] += 1
                _hist(p, "sistema", "erro: " + str(e)[:150])
                if p["tentativas"] >= 2:
                    p["estado"] = "falhou"
                feitos.append(f"{p['id']} erro: {str(e)[:100]}")
            _uso("passos", somar=True)
            with _lock:
                ps = _pedidos()
                for k, x in enumerate(ps):
                    if x["id"] == p["id"]:
                        ps[k] = p
                _gravar(PEDIDOS_JSON, ps)
    finally:
        try:
            trava.unlink()
        except OSError:
            pass
    return feitos


def quadro():
    ps = _pedidos()
    if not ps:
        return f"{config().get('empresa')}: nenhum pedido ainda."
    return f"{config().get('empresa')} ({_uso('passos')}/{limite('passos_dia', 8)} passos hoje, {E.desperdicio(PASTA)} reprovação(ões) na semana):\n" + "\n".join(
        f"• {p['id']} [{p['estado']}] {p['tipo']} {p['cliente']}: {p['briefing'][:60]}" for p in ps[-12:])


def situacao():
    ps = _pedidos()
    return {"empresa": config().get("empresa"), "agentes": len(agentes()), "pedidos": {e: sum(1 for p in ps if p["estado"] == e) for e in (*PASSOS, "entregue", "falhou")},
            "passos_hoje": _uso("passos"), "reprovados_semana": E.desperdicio(PASTA)}


def tick(agora=None, enviar=None):
    """Ligado ao laco da rotina (~10 min): a partir das 7h abre a pauta do dia (Ravi) e avanca um passo por ciclo; avisa o Dono de entrega/falha."""
    agora = agora or datetime.now()
    if agora.hour < 7 or agora.hour >= 21:
        return []
    novos = planejar(agora)
    if novos and enviar:
        enviar(f"Fornalha: pauta de hoje aberta ({', '.join(novos)}).")
    feitos = trabalhar(1)
    for f in feitos:
        if enviar and ("→ entregue" in f or "erro" in f or "reprovado" in f):
            enviar("Fornalha: " + f)
    return feitos


if __name__ == "__main__":
    print(json.dumps(situacao(), ensure_ascii=False, indent=1))
