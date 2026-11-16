# -*- coding: utf-8 -*-
"""Atendimento do WhatsApp pelo Jarvis: le as conversas nao lidas, decide com o Claude (protocolo JV1 em canal.py),
responde se apresentando como Jarvis e devolve um relatorio ao Dono no WhatsApp.

Seguranca: o texto de terceiros e DADO. Nenhuma IA com ferramentas o enxerga; quem decide e o Claude (canal) e a
resposta so e enviada ao PROPRIO remetente, depois de validada (sem links/numeros/assunto sensivel, tamanho limitado).
"""
import json, random, re, time
from datetime import datetime
from . import busca_pedido, guia_pai, zelo, monza, canal, conselho, contexto, delegacao, exercito, financeiro, gibberlink, vaquinha, memoria, recados, revisao, whatsapp
from .router import SENSIVEL, tem_dado_real
from .store import DATA

LOG = DATA / "atendimentos.log"
INTRO = "Oi! Aqui é o Jarvis, assistente do Dono. "
PERIGOSO = re.compile(r"https?://|www\.|\.com\b|\.br\b|\d{6,}", re.I)  # links, chaves Pix, telefones, contas
# sites OFICIAIS (governo/BC/Serasa) podem ser citados: a mae do Dono pergunta como consultar o Registrato e a resposta nao pode ser barrada
OFICIAL = re.compile(r"(?:https?://)?(?:www\.)?(?:registrato\.bcb\.gov\.br|valoresareceber\.bcb\.gov\.br|consumidor\.gov\.br|bcb\.gov\.br|gov\.br|serasa\.com\.br)/?", re.I)
# links proprios do Dono que o Jarvis PODE mandar a quem pedir (so estes): repositorio publico do BRANIAC e os dois sites de exemplo
PROPRIOS = re.compile(r"(?:https?://)?(?:github\.com/carloslavig/B\.R\.A\.N\.I\.A\.C(?:/[\w./-]*)?|exemplo-fotografias\.vercel\.app|lavignecohost\.vercel\.app)", re.I)
# decisao do Dono: nunca usa-lo como desculpa; sempre explicar quem e o Jarvis
OCUPADO = re.compile(r"ocupad[oa]|n[aã]o\s+est[aá]\s+dispon[ií]vel|indispon[ií]vel|(?:est[aá]|t[aá])\s+off|sem\s+tempo|n[aã]o\s+pode\s+atender", re.I)


def _log(linha):
    DATA.mkdir(exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {linha}\n")


def validar_resposta(texto):
    """(ok, motivo). Barra o que poderia causar dano se a decisao estivesse errada ou manipulada."""
    if not texto.strip():
        return False, "vazia"
    if len(texto) > 500:
        return False, "longa demais"
    if PERIGOSO.search(PROPRIOS.sub("", OFICIAL.sub("", texto))):
        return False, "contem link/numero"
    if OCUPADO.search(texto):
        return False, "diz que o Dono esta ocupado/indisponivel (nao pode; explique quem e o Jarvis)"
    if tem_dado_real(texto):          # so barra o DADO (cartao/CPF/senha) ou pedir esses dados; falar de pagamento/cartao/Pix e permitido
        return False, "contem dado sensivel (cartao/CPF/senha) ou pede esses dados"
    return True, ""


SAUDACAO = re.compile(r"\b(?:oi+|ol[aá]|opa|e\s*a[ií]|eai|bom\s+dia|boa\s+tarde|boa\s+noite|tudo\s+(?:bem|bom|certo|joia)|td\s+bem|blz|beleza|salve|fala|hey|hello)\b", re.I)
URGENTE = re.compile(r"urgente|urg[eê]ncia|preciso\s+falar|me\s+liga|ligar\s+(?:pra|para)|liga\s+(?:pra|para)|falar\s+com\s+(?:o\s+)?dono|chama\s+o\s+dono|proposta|"
                     r"entrevista|reuni[aã]o|contrato|cobran[cç]a|problema|reclama|socorro|emerg[eê]ncia", re.I)
PRIMEIRO_CONTATO = "Como posso te ajudar?"      # o prefixo de apresentacao (quem e o Jarvis) e colocado por com_apresentacao


def importante(entrada):
    """Primeira mensagem de contato novo que o Dono precisa ver: urgencia, pedido para falar/ligar com ele, proposta, contrato, problema, audio.
    Duvida de rotina (preco, vaga, horario) o Jarvis responde sozinho: nao vira aviso."""
    t = (entrada or "").strip()
    return bool(t) and (bool(URGENTE.search(t)) or "🎙" in t)


PERGUNTA_DA_LAYLA = re.compile(r"\?|\b(?:preciso|precisa|ajuda|ajudar|erro|problema|como|quando|qual|quais|onde|por\s+que|pode|consegue|d[aá]\s+pra)\b", re.I)
VOZ_ATENDER_MAX = 650  # respostas a terceiros em audio (~45 s, ja com a apresentacao); maior que isso vai por escrito (o texto em si e limitado a 500)


# 16/11: ouvir audio recarrega a pagina do WhatsApp; se falhou, nao repete por 20 min para a mesma pessoa (o pai travava o atendimento de todos)
AUDIO_FALHOU, AUDIO_PAUSA_S = {}, 1200


def _enviar_resposta(nome, final, it):
    """PADRAO: audio (voz do Jarvis). Texto se a pessoa pediu por escrito (a preferencia fica salva), se a resposta e longa
    ou tem que ser lida; e tambem se o envio do audio falhar. Do outro lado e IA em modo GL1 (Gibberlink): sempre texto,
    sem gastar TTS nem o Whisper dela. Devolve o resultado (comeca com ✅ se enviou)."""
    if it.get("gl") == "ativo":
        return whatsapp.enviar(nome, final)
    if it.get("msgs"):      # resposta a terceiro: ultimo filtro (repeticao, vazamento, textao) antes de sair
        from . import clareza
        try:
            _s = [t for d, t in memoria.historico(nome, 12) if d == "C"]
            final = clareza.polir(nome, final, " ".join(it.get("msgs", [])), _s)
        except Exception:
            pass
        if not final:
            return "silencio"
    if guia_pai.eh_pai(nome):   # pai do Dono: NUNCA texto (Dono, 10/11); sem limite de tamanho e sem cair para escrita se o audio falhar
        try:
            from . import voz, wpp_voz
            return wpp_voz.enviar_voz(nome, voz.falar_wav(final))
        except Exception as e:
            return f"⚠️ audio ao pai falhou ({str(e)[:60]}); texto bloqueado"
    contexto.atualizar_preferencia(nome, " ".join(it.get("msgs", [])))
    if contexto.deve_falar(nome, final) and len(final) <= VOZ_ATENDER_MAX:
        try:
            from . import voz, wpp_voz
            r = wpp_voz.enviar_voz(nome, voz.falar_wav(final))
            if r.startswith("✅"):
                return r
        except Exception:
            pass
    return whatsapp.enviar(nome, final)


def _audio_recado(destino, fala):
    """Recado ao Dono em AUDIO (conversa, nao relatorio). Devolve 'comeca com ✅' se enviou."""
    from . import voz, wpp_voz
    return wpp_voz.enviar_voz(destino, voz.falar_wav(fala))


def nao_responder_ou_grupo(nome, flags):
    return contexto.nao_responder(nome) or "G" in flags


def com_apresentacao(chat, texto, pergunta=""):
    """1o contato: se apresenta como Jarvis. Familia/Parceira tem abertura propria (ex.: 'Oi, minha tia!').
    Quem ja conhece o Jarvis nao ouve a apresentacao de novo (nem a que a IA escreveu no proprio texto), salvo se perguntar quem ele e."""
    if contexto.apresentado(chat) or any(d == "C" and contexto._QUEM_SOU.search(t) for d, t in memoria.historico(chat, 30)):
        return contexto.sem_reapresentacao(texto, pergunta)
    if "jarvis" in texto.lower():
        return texto
    return contexto.abertura_padrao(chat) + texto


def _ouvir_audio(nome):
    """Transcreve (Whisper local) o audio mais recente que a pessoa mandou. Devolve (texto, erro)."""
    from . import wpp_voz
    return wpp_voz.ouvir_ultimo_audio(nome)


def _ver_imagem(nome):
    """Descreve (Gemini; plano B local) a imagem mais recente que a pessoa mandou. Devolve (texto, erro)."""
    from . import wpp_img
    return wpp_img.ver_ultima_imagem(nome)


def _autor(cabecalho):
    m = re.search(r"\]\s*(.*?):\s*$", cabecalho or "")
    return m.group(1).strip() if m else ""


def _finais_deles(msgs):
    """Mensagens DELES no fim da conversa, depois da ultima nossa (as 'sem resposta')."""
    fim, pulando = [], True
    for m in reversed(msgs):
        if pulando and m["d"] != "ELE" and contexto.saudacao_automatica(m.get("t", "")):
            continue            # saudacao automatica do WhatsApp Business (vem como 'nossa'): nao conta como resposta
        pulando = False
        if m["d"] != "ELE":
            break
        fim.append(m)
    return list(reversed(fim))


def idade_horas(cabecalho, agora=None):
    """Idade (em horas) de uma mensagem pelo cabecalho '[17:13, 01/10/2026] Nome: '. None se nao der para ler."""
    m = re.search(r"\[(\d{1,2}):(\d{2}),\s*(\d{1,2})/(\d{1,2})/(\d{4})\]", cabecalho or "")
    if not m:
        return None
    h, mi, d, mo, a = (int(x) for x in m.groups())
    try:
        quando = datetime(a, mo, d, h, mi)
    except ValueError:
        return None
    return ((agora or datetime.now()) - quando).total_seconds() / 3600


def idade_linha(resumo, agora=None):
    """Idade (horas) da ultima mensagem pela LISTA ('Nome | 17:47 | texto'): so entende horario de hoje (HH:MM).
    'Ontem', dia da semana ou data => None (velho demais para responder de repente)."""
    agora = agora or datetime.now()
    for parte in str(resumo).split(" | ")[1:3]:
        m = re.fullmatch(r"(\d{1,2}):(\d{2})", parte.strip())
        if m:
            quando = agora.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
            h = (agora - quando).total_seconds() / 3600
            return h if h >= 0 else h + 24  # horario 'no futuro' = ontem
    return None


def esperando_resposta(linhas, agora=None, max_idade_h=12):
    """Conversas cuja ULTIMA mensagem e DELES (lida ou nao) e recente: as que estao esperando resposta."""
    dono_nome = contexto.contato("dono")
    nomes = []
    for c in linhas:
        if (c.get("nossa") and not contexto.saudacao_automatica(c.get("resumo", ""))) or c["nome"] == dono_nome or contexto.nao_responder(c["nome"]):
            continue
        h = idade_linha(c.get("resumo", ""), agora)
        if h is not None and h <= max_idade_h:
            nomes.append(c["nome"])
    return nomes


def eh_grupo(cabecalho):
    """Cabecalho do chat aberto: grupo mostra os participantes ('A, B, Você') ou 'dados do grupo'; 1:1 mostra 'visto por último'/'online'."""
    h = (cabecalho or "").lower()
    if "dados do grupo" in h or "group info" in h:
        return True
    return h.count(",") >= 2 and not re.search(r"visto|online|digitando|[úu]ltim", h)


def coletar(max_chats=5, max_msgs=4, somente=None, max_idade_h=None):
    """Conversas com nao lidas OU ainda sem resposta (olhar o WhatsApp marca como lida, mas continua pendente).
    Devolve lista de dicts ou string de erro. O chat do Dono fica de fora: e do vigia (dono.py)."""
    try:
        W = whatsapp._wpp()
        dono_nome = contexto.contato("dono")
        itens = []
        with whatsapp.LOCK, W.WA() as w:  # a pagina do WhatsApp e uma so: ninguem mais mexe enquanto lemos as conversas
            lista = json.loads(w.js(W.JS_LISTA))
            if not lista:
                return "A lista de conversas do WhatsApp veio vazia (carregando ou deslogado)."
            nomes = [c["nome"] for c in lista]
            if somente is not None:  # vigia automatico: so as conversas que ele escolheu (sem pendencias antigas)
                candidatos = [n for n in somente if n in nomes]
            else:
                candidatos = [c["nome"] for c in lista if c["nao_lidas"] > 0]
                candidatos += [n for n in whatsapp.pendentes_ler() if n in nomes and n not in candidatos]
                from . import dono  # tambem as LIDAS e sem resposta: ultima mensagem da conversa e dela
                candidatos += [n for n in esperando_resposta(json.loads(w.js(dono.JS_LINHAS)), None, 12) if n in nomes and n not in candidatos]
            for nome in candidatos:
                if nome == dono_nome:
                    continue
                if len(itens) >= max_chats:
                    break
                if not W.abrir(w, nome):
                    continue
                time.sleep(1.5)
                d = json.loads(w.js(W.JS_MSGS % 14))
                novas = _finais_deles(d["msgs"])
                cab = w.js("(document.querySelector('#main header')||{}).innerText||''") or ""
                from . import wpp_voz
                audio_dele = bool(wpp_voz.ultimo_audio_dele(w).get("dele"))  # o ultimo item e um audio DELA/DELE?
                # so texto velho (dias atras) nao reabre a conversa; mas audio/midia dele no fim a vigia ja viu chegar (respostas nossas em audio nao entram em msgs)
                if max_idade_h and novas and not d["midias"] and not audio_dele and all((idade_horas(m["c"]) or 0) > max_idade_h for m in novas):
                    continue
                if max_idade_h and (d["midias"] or audio_dele):   # 04/11: texto de dias atras nao entra junto do audio novo (o Jarvis respondia o texto velho e ignorava o audio)
                    novas = [m for m in novas if (idade_horas(m["c"]) or 0) <= max_idade_h]
                if not novas and not d["midias"] and not audio_dele:
                    whatsapp.pendente_remover(nome)  # ja respondida por alguem
                    continue
                itens.append({"nome": nome, "nl": len(novas), "audio_dele": audio_dele, "grupo": eh_grupo(cab),
                              "msgs": [m["t"] for m in novas[-max_msgs:] if m["t"]] + [x["t"] for x in d["midias"]],
                              "ctx": [("C: " if m["d"] == "EU" else "E: ") + m["t"][:100] for m in d["msgs"][-8:] if m["t"]],
                              "autores": {_autor(m["c"]) for m in novas if _autor(m["c"])},
                              "midia": bool(d["midias"]) or not any(m["t"] for m in novas)})
        return itens
    except Exception as e:
        return whatsapp._erro(e)


def flags_de(it):
    f = ""
    if len(it["autores"]) > 1 or it.get("grupo"):
        f += "G"
    if SENSIVEL.search(" ".join(it["msgs"])):
        f += "S"
    if it["midia"]:
        f += "A"
    if not contexto.apresentado(it["nome"]):
        f += "N"
    if it.get("gl") == "ativo":
        f += "M"
    return f or "-"


def _enriquecer_ctx(it):
    """Completa o contexto da conversa com o que o banco local lembra (mais antigo que as ultimas mensagens da tela)."""
    visto = " ".join(it.get("ctx", []))
    antigas = [("E: " if d == "E" else "C: ") + t[:100] for d, t in memoria.historico(it["nome"], 14)[:-2]
               if t[:40] not in visto]
    it["ctx"] = (antigas[-6:] + list(it.get("ctx", [])))[-10:]


def _familia(nome):
    from . import jarvis
    return jarvis._eh_familia(nome)


def _resposta_familia(nome, entrada):
    """Resposta curta e carinhosa para a familia (so com o que ela disse; nada inventado). IA sem persona e sem Claude; se cair, um acolhimento simples."""
    try:
        from .router import Router
        r, _ = Router().responder_neutro(
            "Voce e o Jarvis, assistente de IA do Dono, falando com a FAMILIA dele no WhatsApp (se for a mae, chame de 'minha tia' ou 'Mae', jeito de sobrinho, "
            "carinhoso e informal). Responda em 1 ou 2 frases, acolhendo o que ela disse. NAO invente fatos, promessas, links, remedios nem diagnosticos.",
            "Mensagem dela: " + entrada[:500])
        if r and len(r) < 600:
            return r.strip()
    except Exception:
        pass
    return "Oi, minha tia! Recebi sua mensagem e já avisei o Dono. Cuida bem de você, tá?"


def decidir(it, flags, espera_s=150):
    """Pergunta ao Claude: ao vivo se ele esta presente no canal; senao, um Claude em segundo plano."""
    id_ = canal.uuid.uuid4().hex[:6]
    ctx = it.get("ctx")
    if canal.presente():
        res = canal.perguntar(it["nome"], flags, it["msgs"], espera_s=espera_s, id_=id_, ctx=ctx)
        if res:
            return res[1], res[2]
    mem = memoria.contexto_para_decidir(it["nome"], " ".join(it["msgs"]))  # ficha local: o Claude decide sem precisar perguntar
    res = contexto.decidir_claude(canal.formatar_pergunta(id_, it["nome"], flags, it["msgs"], ctx), memoria_txt=mem)
    return (res[1], res[2]) if res else None


ULTIMO = {"enviados": [], "linhas": [], "tratados": []}  # tratados = conversas com decisao tomada (enviar/ignorar/avisar/perguntar)  # resultado do ultimo atender() (o vigia automatico le daqui)


def atender(notificar=None, max_chats=5, espaco_s=(15, 30), espera_s=150, relatar=True, ouvir_audio=None,
            somente=None, max_idade_h=None, pular_grupos=False, ver_imagem=None):
    ouvir_audio = ouvir_audio or _ouvir_audio
    ver_imagem = ver_imagem or _ver_imagem
    ULTIMO.update(enviados=[], linhas=[], tratados=[], grupos=[])
    itens = coletar(max_chats, somente=somente, max_idade_h=max_idade_h) if (somente is not None or max_idade_h) else coletar(max_chats)
    if isinstance(itens, str):
        return itens
    if not itens:
        return "Nenhuma mensagem nova para atender no WhatsApp. ✅"
    linhas, enviados = [], 0
    for it in itens:
        nome = it["nome"]
        if it.get("audio_dele") and not contexto.nao_responder(nome):  # OUVE o audio (local) antes de decidir
            if time.time() - AUDIO_FALHOU.get(nome, 0) < AUDIO_PAUSA_S:
                txt, erro = None, "ouvir falhou ha pouco: sem recarregar o WhatsApp de novo"
            else:
                try:
                    txt, erro = ouvir_audio(nome)
                except Exception as e:
                    txt, erro = None, str(e)[:80]
                if not (txt or "").strip() and erro:
                    AUDIO_FALHOU[nome] = time.time()
            it["msgs"] = [m for m in it["msgs"] if m != "[AUDIO]"] + ([f"🎙 {txt.strip()}"] if (txt or "").strip() else ["[ÁUDIO não compreendido]"])
            it["midia"] = not (txt or "").strip()
            _log(f"{nome} | audio ouvido | {(txt or erro or '')[:100]!r}")
            if contexto.prioritario(nome):   # Layla (IA) nao ouve audio: devolve a transcricao em TEXTO e encerra (ela le e age)
                msg = f"Transcrição do seu áudio:\n\n{txt.strip()}" if (txt or "").strip() else "Não consegui entender o seu áudio. Pode mandar de novo ou escrever?"
                memoria.registrar_msg(nome, "E", (txt or "[áudio]").strip(), audio=True)
                r = whatsapp.enviar(nome, msg)
                linhas.append(f"• {nome}: áudio transcrito e devolvido em texto ({r[:40]})")
                ULTIMO["tratados"].append(nome)
                whatsapp.pendente_remover(nome)
                continue
        if "[IMAGEM]" in it["msgs"] and not contexto.nao_responder(nome) and not (pular_grupos and it.get("grupo")):   # grupo ignorado: nem gasta visao  # VE a imagem antes de decidir (Gemini; local de reserva)
            try:
                desc, erro = ver_imagem(nome)
            except Exception as e:
                desc, erro = None, str(e)[:80]
            it["msgs"] = [m for m in it["msgs"] if m != "[IMAGEM]"] + ([f"🖼 {desc.strip()}"] if (desc or "").strip() else ["[IMAGEM não compreendida]"])
            it["midia"] = any(m.startswith("[") and m.endswith("]") for m in it["msgs"])  # sobrou midia que o Claude nao ve
            _log(f"{nome} | imagem vista | {(desc or erro or '')[:100]!r}")
        docs = [m for m in it["msgs"] if m.startswith("[DOC:")]
        if docs and not contexto.nao_responder(nome) and not it.get("grupo"):   # DOCUMENTO: avisa, baixa e o Claude ajuda e devolve (wpp_doc.py)
            from . import claude_agent, wpp_doc
            for m_ in it["msgs"]:
                memoria.registrar_msg(nome, "E", m_.replace("[DOC:", "[arquivo ").replace("]", "]", 1))
            try:
                linha = wpp_doc.tratar(nome, it, docs, lambda t: _enviar_resposta(nome, com_apresentacao(nome, t), it),
                                       lambda tarefa: claude_agent.executar_em_segundo_plano(tarefa, None))
            except Exception as e:
                linha = f"⚠️ {nome}: mandou um arquivo e deu erro ao tratar ({str(e)[:80]})"
            linhas.append(linha)
            _log(f"{nome} | documento | {linha[:120]}")
            ULTIMO["tratados"].append(nome)
            whatsapp.pendente_remover(nome)
            continue
        if guia_pai.eh_pai(nome) and not it.get("grupo"):   # Zelo: pai do Dono le devagar; explica em audio o que a mensagem de agora diz (so o de agora)
            linha = guia_pai.tratar(nome, it)
            if linha:
                linhas.append(linha)
                if linha.startswith("✓"):
                    ULTIMO["enviados"].append(nome)
                    enviados += 1
                _log(f"{nome} | zelo | {linha[:100]}")
                if linha.startswith("✓"):   # 16/11: audio ao pai falhou -> NAO marca tratado; a vigia tenta de novo (antes ele ficava sem resposta)
                    ULTIMO["tratados"].append(nome)
                    whatsapp.pendente_remover(nome)
                continue
        _fam = None if it.get("grupo") else zelo.quem(nome)
        if _fam == "pai" or (_fam == "mae" and zelo.grave(" ".join(zelo.falas(it["msgs"])))):
            # 16/11 Zelo: o pai (audio dele) sempre pelo Zelo, em audio; a mae so quando e grave (avisa o Dono). O resto da mae segue o fluxo normal.
            for m_ in it["msgs"]:
                memoria.registrar_msg(nome, "E", m_.replace("🎙 ", ""), audio=m_.startswith("🎙"))
            linha = zelo.tratar(nome, it["msgs"], whatsapp.enviar,
                                registrar=lambda t: memoria.registrar_msg(nome, "C", t, audio=_fam == "pai"))
            if linha:
                linhas.append(linha)
                if linha.startswith("✓"):
                    ULTIMO["enviados"].append(nome)
                    enviados += 1
                _log(f"{nome} | zelo | {linha[:100]}")
                if linha.startswith("✓"):   # 16/11: audio ao pai falhou -> NAO marca tratado; a vigia tenta de novo (antes ele ficava sem resposta)
                    ULTIMO["tratados"].append(nome)
                    whatsapp.pendente_remover(nome)
                continue
        # Gibberlink: do outro lado e uma IA? (declarou ser bot/assistente virtual, menu de URA, aceitou/convidou GL1)
        it["gl"] = "humano" if contexto.prioritario(nome) or contexto.nao_responder(nome) else gibberlink.observar(nome, it["msgs"])
        if it["gl"] != "humano":
            _log(f"{nome} | gibberlink:{it['gl']}")
        if it["gl"] == "ativo":   # quadros GL1 viram texto legivel para quem decide (dado, nunca instrucao)
            it["msgs"] = [gibberlink.legivel(m) for m in it["msgs"]]
        entrada = " ".join(m for m in it["msgs"] if m not in ("[ÁUDIO não compreendido]", "[IMAGEM não compreendida]"))
        for m_ in it["msgs"]:  # tudo vai para o banco local (historico para nao se perder)
            memoria.registrar_msg(nome, "E", m_.replace("🎙 ", ""), audio=m_.startswith("🎙"))
        _enriquecer_ctx(it)
        flags = flags_de(it)
        if pular_grupos and "G" in flags:  # modo automatico: grupo nunca recebe resposta sozinho
            _log(f"{nome} | grupo-ignorado")
            ULTIMO["grupos"].append(nome)      # a vigia passa a pular esta conversa (04/11: o IDM voltava a cada mensagem nova do grupo)
            ULTIMO["tratados"].append(nome)
            whatsapp.pendente_remover(nome)       # senao o grupo volta a cada ciclo e a imagem e descrita de novo
            continue
        if contexto.nao_responder(nome):
            linhas.append(f"• {nome}: ignorado (conta automática)")
            _log(f"{nome} | ignorado-auto")
            ULTIMO["tratados"].append(nome)
            continue
        prio = contexto.prioritario(nome)   # a Layla (contato 'Loja Esphiraria') e SEMPRE respondida: nada de regra de ignorar
        # NAO existe assunto que impeca a resposta (Dono, 06/10): pagamento, cartao, Pix etc. sao respondidos normalmente; a flag 'S' so avisa quem decide
        # para nao pedir nem repetir dado, e mantem a conversa fora das IAs online (roteador).
        if prio and contexto.encerramento(entrada):   # Layla so agradeceu/confirmou: nao responde (evita laco de pergunta e resposta)
            whatsapp.pendente_remover(nome)
            linhas.append(f"• {nome}: encerramento, sem resposta (evita laço)")
            _log(f"{nome} | encerramento-sem-resposta")
            ULTIMO["tratados"].append(nome)
            continue
        if conselho.pode_convocar(nome) and conselho.pediu(entrada):
            # Layla ou Parceira pediram o conselho de IAs: reune ChatGPT, Gemini e Grok (so o TEMA sai; nada do WhatsApp)
            from . import jarvis as _jv
            rel = conselho.reunir(conselho.tema_de(entrada), _jv.consultar_reuniao, conselho.sintetizar_padrao, formato=entrada[:600])
            dec = ("E", conselho.para_enviar(rel))
            cod, texto = dec
            ok, motivo = True, ""
            final = com_apresentacao(nome, texto)
            r = _enviar_resposta(nome, final, it)
            if r.startswith("✅"):
                contexto.marcar_apresentado(nome)
                memoria.registrar_msg(nome, "C", final)
                ULTIMO["enviados"].append(nome)
                linhas.append(f"✓ {nome} (conselho de IAs): «{final[:90]}»")
                _log(f"{nome} | conselho-ias | {final[:100]}")
            ULTIMO["tratados"].append(nome)
            whatsapp.pendente_remover(nome)
            continue
        _rl = None if (_familia(nome) or prio or it.get("grupo")) else busca_pedido.resposta_de_lugar(nome, entrada)
        if _rl:       # clinica/loja que o Jarvis consultou respondeu: repassa a quem pediu e NAO responde nem agenda nada (05/11)
            from . import barramento
            r = whatsapp.enviar(_rl[0], _rl[1])
            barramento.enviar("Correio", "Jarvis", "alerta", f"🏥 {nome} respondeu a consulta de {_rl[0]}: «{entrada[:200]}» (repassei).")
            linhas.append(f"✓ {nome} (resposta de lugar consultado) repassada para {_rl[0]}")
            _log(f"{nome} | busca-pedido: resposta repassada a {_rl[0]} | {r[:40]}")
            ULTIMO["tratados"].append(nome)
            whatsapp.pendente_remover(nome)
            continue
        _pode_busca = (_familia(nome) or contexto._norm(nome) == contexto._norm(contexto.contato("parceira") or "")) and not it.get("grupo")
        if _pode_busca:
            from . import barramento
            _aviso = lambda t: barramento.enviar("Correio", "Jarvis", "alerta", t)
            _conf = busca_pedido.confirmacao(nome, entrada, whatsapp.enviar, _aviso)     # "sim, pode mandar" a uma oferta de contatar clinicas
            if _conf:
                r = _enviar_resposta(nome, _conf, it)
                if r.startswith("✅"):
                    memoria.registrar_msg(nome, "C", _conf)
                    ULTIMO["enviados"].append(nome)
                _log(f"{nome} | busca-pedido: confirmacao | {_conf[:80]}")
                ULTIMO["tratados"].append(nome)
                whatsapp.pendente_remover(nome)
                continue
        if _pode_busca and busca_pedido.eh_pedido(entrada):
            # familia/Parceira pediu para PROCURAR preco/lugar (ex.: ressonancia em Itabuna): avisa, acha no Maps e na web em segundo plano e manda links e telefones (05/11)
            final = busca_pedido.iniciar(nome, entrada, lambda t, n=nome: whatsapp.enviar(n, t), _aviso, whatsapp.enviar)
            r = _enviar_resposta(nome, final, it)
            if r.startswith("✅"):
                memoria.registrar_msg(nome, "C", final)
                ULTIMO["enviados"].append(nome)
                linhas.append(f"✓ {nome} (busca na web): «{entrada[:70]}»")
                _log(f"{nome} | busca-pedido | {entrada[:100]}")
            ULTIMO["tratados"].append(nome)
            whatsapp.pendente_remover(nome)
            continue
        if monza.eh_pedido(entrada, nome) and not it.get("grupo") and not prio and not _familia(nome) and contexto._norm(nome) not in {contexto._norm(contexto.contato(a) or "") for a in ("parceira", "dono", "mae")}:
            # pedido de corrida: o Monza pergunta origem/destino, calcula a rota (R$ 2,30/km) e avisa o Dono (sem IA)
            from . import barramento
            final = monza.responder(nome, entrada, lambda t: barramento.enviar("Monza", "Jarvis", "alerta", t))   # o Jarvis repassa ao Dono
            r = _enviar_resposta(nome, final, it)
            if r.startswith("✅"):
                memoria.registrar_msg(nome, "C", final)
                ULTIMO["enviados"].append(nome)
                linhas.append(f"✓ {nome} (Monza): corrida")
                _log(f"{nome} | monza | {final[:100]}")
            ULTIMO["tratados"].append(nome)
            whatsapp.pendente_remover(nome)
            continue
        if contexto.agradecimento(entrada) and (contexto.apresentado(nome) or memoria.ja_falamos(nome)) and not prio:   # so 'valeu': nao se reapresenta (29/10)
            final = contexto.agradecimento(entrada) if (_familia(nome) or contexto._norm(nome) == contexto._norm(contexto.contato("parceira") or "")) else None
            r = _enviar_resposta(nome, final, it) if final else "silencio"   # os demais: sem resposta (evita laco de 'valeu' e 'de nada')
            if final is None or r.startswith("✅"):
                if final:
                    memoria.registrar_msg(nome, "C", final)
                    ULTIMO["enviados"].append(nome)
                linhas.append(f"• {nome}: agradeceu" + (" (respondi curto)" if final else " (sem resposta necessária)"))
                _log(f"{nome} | agradecimento | {final or 'sem resposta'}")
                ULTIMO["tratados"].append(nome)
                whatsapp.pendente_remover(nome)
                continue
        if contexto.elogio(entrada) and contexto.apresentado(nome):   # so elogio: agradece curto, sem repetir quem e o Jarvis (29/10)
            final = contexto.elogio(entrada)
            r = _enviar_resposta(nome, final, it)
            if r.startswith("✅"):
                memoria.registrar_msg(nome, "C", final)
                ULTIMO["enviados"].append(nome)
                linhas.append(f"✓ {nome} (elogio): agradeci")
                _log(f"{nome} | elogio | {final}")
            ULTIMO["tratados"].append(nome)
            whatsapp.pendente_remover(nome)
            continue
        if exercito.eh_checklist(entrada) and contexto._norm(nome) in {contexto._norm(contexto.contato(a) or "") for a in ("parceira", "dono", "mae")}:
            # checklist dos exames (Cabo Tito): so o Dono marca; Parceira e Mae so veem a lista (local, sem IA)
            dono = contexto._norm(nome) == contexto._norm(contexto.contato("dono") or "")
            final = exercito.marcar(entrada) if dono else exercito.checklist()
            r = _enviar_resposta(nome, final, it)
            if r.startswith("✅"):
                memoria.registrar_msg(nome, "C", final)
                ULTIMO["enviados"].append(nome)
                linhas.append(f"✓ {nome} (Cabo Tito): checklist de exames")
            ULTIMO["tratados"].append(nome)
            whatsapp.pendente_remover(nome)
            continue
        if exercito.eh_pergunta(entrada) and contexto._norm(nome) in {contexto._norm(contexto.contato(a) or "") for a in ("parceira", "dono", "mae")}:
            # Dono, Parceira e Mãe: prazo/exames/EAF do Exército saem do Cabo Tito (local, sem IA)
            final = com_apresentacao(nome, delegacao.consultar("Cabo Tito", entrada)["texto"])
            r = _enviar_resposta(nome, final, it)
            if r.startswith("✅"):
                contexto.marcar_apresentado(nome)
                memoria.registrar_msg(nome, "C", final)
                ULTIMO["enviados"].append(nome)
                linhas.append(f"✓ {nome} (Cabo Tito): exames/prazos do Exército")
                _log(f"{nome} | cabo-tito | respondido")
            ULTIMO["tratados"].append(nome)
            whatsapp.pendente_remover(nome)
            continue
        if contexto._norm(nome) == contexto._norm(contexto.contato("parceira") or "") and financeiro.eh_pergunta(entrada):
            # Parceira tem acesso TOTAL (Dono, 27/10): saldo/meta/relatorios saem do agente financeiro local, sem IA e sem perguntar ao Dono
            final = com_apresentacao(nome, delegacao.consultar("Cofre", entrada)["texto"])
            r = _enviar_resposta(nome, final, it)
            if r.startswith("✅"):
                contexto.marcar_apresentado(nome)
                memoria.registrar_msg(nome, "C", final)
                ULTIMO["enviados"].append(nome)
                linhas.append(f"✓ {nome} (financeiro): resposta com saldo/meta")
                _log(f"{nome} | financeiro | respondido")
            ULTIMO["tratados"].append(nome)
            whatsapp.pendente_remover(nome)
            continue
        if contexto._norm(nome) == contexto._norm(contexto.contato("parceira") or "") and vaquinha.aguardando() and (vaquinha.valores_da_resposta(entrada) or vaquinha.confirmando()):
            # a Parceira respondeu o saldo da vaquinha: grava, atualiza o site e avisa o Dono (sem IA)
            from . import contexto as _c
            _avisa = lambda m: _enviar_resposta(_c.contato("dono") or "Eu", m, {})
            if vaquinha.confirmando():     # conflito de valores pendente: so 'a mais' ou 'total' resolvem
                final = vaquinha.resolver_confirmacao(entrada, enviar_dono=_avisa) or "Não entendi. Responde só uma destas: a mais, ou total."
            else:
                final = vaquinha.registrar_valores(vaquinha.valores_da_resposta(entrada), "Parceira", rotulado=vaquinha.tem_rotulo(entrada), enviar_dono=_avisa)
            r = _enviar_resposta(nome, final, it)
            if r.startswith("✅"):
                memoria.registrar_msg(nome, "C", final)
                ULTIMO["enviados"].append(nome)
                linhas.append(f"✓ {nome} (vaquinha): saldo anotado")
                _log(f"{nome} | vaquinha | saldo anotado")
            ULTIMO["tratados"].append(nome)
            whatsapp.pendente_remover(nome)
            continue
        regra = None if (prio or _familia(nome)) else (memoria.decisao_repetida(nome, entrada, ("I",), dias=30) or memoria.decisao_repetida(nome, entrada, ("A",), dias=1))
        if regra:  # o Claude ja decidiu EXATAMENTE isto antes: nao gasta pergunta
            whatsapp.pendente_remover(nome)
            linhas.append(f"• {nome}: igual a uma mensagem já tratada ({'ignorada' if regra == 'I' else 'avisada'}), sem nova pergunta")
            _log(f"{nome} | regra-aprendida:{regra}")
            ULTIMO["tratados"].append(nome)
            continue
        dec = decidir(it, flags, espera_s)
        if not dec and prio and PERGUNTA_DA_LAYLA.search(entrada):   # ninguem decidiu a tempo: so cobre com resposta de reserva se ela perguntou/pediu algo
            dec = ("E", "Recebi sua mensagem, Layla. Já estou verificando e te respondo.")
            _log(f"{nome} | sem-decisao: resposta de reserva para a Layla")
        novo = "N" in flags and "G" not in flags and not contexto.nao_responder(nome) and not memoria.ja_falamos(nome)   # 1o contato (contas automaticas e grupos ficam de fora)
        if not dec and not nao_responder_ou_grupo(nome, flags):
            # Dono (06/10): o Jarvis nao pode deixar ninguem sem resposta nem 'ignorar' contato novo. Sem decisao a tempo: responde na hora
            # (contato novo = se apresenta e pergunta como ajudar; os demais = resposta neutra) e deixa o aviso para o Dono no relatorio.
            dec = ("E", PRIMEIRO_CONTATO if novo else revisao.NEUTRA)
            linhas.append(f"⏸ {nome}: ninguém decidiu a tempo; respondi com {'a apresentação' if novo else 'um recebimento'} e deixei a mensagem pra você: «{entrada[:100]}»")
            _log(f"{nome} | sem-decisao: resposta imediata ({'apresentacao' if novo else 'neutra'})")
        if not dec:
            linhas.append(f"⏸ {nome}: ninguém decidiu a tempo, segurei")
            _log(f"{nome} | sem-decisao")
            continue
        cod, texto = dec
        # NADA sai sem passar pela revisao: o auditor barra rotular a pessoa, repetir o que ja foi dito e ignorar pedido de cliente;
        # barrado => vai ao Claude (ao vivo ou revisor de fundo); sem revisor, o Jarvis SEGURA em vez de enviar.
        cod, texto, nota = revisao.decidir_com_revisao(it, flags, (cod, texto), espera_s)
        if cod in ("I", "A", "P") and _familia(nome):
            cod, texto = "E", _resposta_familia(nome, entrada)   # 24/10: a mae mandou audio e o Claude 'ignorou' -> familia nunca fica sem resposta
            _log(f"{nome} | familia: nao ignora, respondeu")
        if prio and cod in ("I", "A", "P") and PERGUNTA_DA_LAYLA.search(entrada):
            cod, texto = "E", "Entendido, Layla. Já estou vendo isso e te retorno."   # ela perguntou/pediu algo: nunca fica sem resposta
        aviso_novo = None
        if novo and not prio:
            original = (cod, texto)
            if cod != "E":            # contato novo NUNCA e ignorado, segurado ou so avisado: responde se apresentando e pergunta como ajudar
                cod, texto = "E", PRIMEIRO_CONTATO
                _log(f"{nome} | contato novo: decisao {original[0]} trocada por apresentacao")
            if importante(entrada) or original[0] in ("A", "P"):
                nota_c = (original[1] if original[0] in ("A", "P") and original[1] else entrada)[:140]
                aviso_novo = f"⚠️ {nome} (contato novo, parece importante): «{nota_c}» — já me apresentei e respondi"
        memoria.registrar_decisao(nome, entrada, cod, texto)  # a decisao (ja revisada) fica no banco
        recado_na_fila = False
        if not prio and not contexto.nao_responder(nome) and "G" not in flags:   # RECADOS: literal, em fila, com nova tentativa (recados.py)
            if cod in ("A", "P") or (aviso_novo and cod == "E"):
                recado_na_fila = recados.enfileirar(nome, entrada, nota=(texto if cod in ("A", "P") else ""))
        if "americo" in contexto._norm(nome):     # tio da Parceira: so o que for do divorcio vira recado para a Mariana (Telegram, telegram_ex.py)
            try:
                from . import telegram_ex
                telegram_ex.atualizacao(entrada)
            except Exception:
                pass
        ULTIMO["tratados"].append(nome)
        if cod in ("E", "I", "A"):
            whatsapp.pendente_remover(nome)  # tratada; 'P' (segurar) continua pendente
        if cod == "E":
            ok, motivo = validar_resposta(texto)
            if not ok and motivo.startswith("longa"):  # nao descarta: pede de novo, mais curta (flag L no protocolo)
                nova = decidir(it, flags + "L", espera_s)
                if nova and nova[0] == "E":
                    texto = nova[1]
                    ok, motivo = validar_resposta(texto)
                    _log(f"{nome} | resposta longa refeita ({len(texto)} chars)")
            if not ok:
                linhas.append(f"⚠️ {nome}: resposta barrada ({motivo}), segurei")
                _log(f"{nome} | barrada:{motivo} | {texto[:80]}")
                continue
            if enviados:  # espaca os envios: evita o WhatsApp limitar o numero
                time.sleep(random.uniform(*espaco_s))
            if it.get("gl") == "ativo":   # IA <-> IA: quadro compacto, sem cortesia (1o contato leva quem somos num campo)
                final = gibberlink.compactar(texto, de=None if contexto.apresentado(nome) else gibberlink.QUEM_SOMOS)
                if not validar_resposta(final)[0]:   # quadro estranho: volta para a fala normal em vez de arriscar
                    _log(f"{nome} | gibberlink: quadro barrado, enviado em texto normal")
                    it["gl"], final = "humano", com_apresentacao(nome, texto)
            else:
                final = com_apresentacao(nome, texto, entrada)
                if it.get("gl") == "oferecer":
                    final = gibberlink.com_convite(final)
            r = _enviar_resposta(nome, final, it)
            if r.startswith("✅"):
                if it.get("gl") == "oferecer":
                    gibberlink.marcar_oferecido(nome)
                elif it.get("gl") == "ativo":   # mede a economia (o conselho pediu numeros antes de espalhar o GL1)
                    gibberlink.medir(nome, com_apresentacao(nome, texto), final)
                como = "áudio" if r.startswith("✅ Áudio") else ("GL1" if it.get("gl") == "ativo" else "texto")
                contexto.marcar_apresentado(nome)
                memoria.registrar_msg(nome, "C", final, audio=como == "áudio")
                enviados += 1
                ULTIMO["enviados"].append(nome)
                linhas.append(f"✓ {nome} ({como}): «{final[:90]}»")
                _log(f"{nome} | enviado({como}) | {final}")
                if not prio and not recado_na_fila and nome in (contexto.contato("mae"), contexto.contato("pai")) and len(entrada.split()) >= 4:
                    recado_na_fila = recados.enfileirar(nome, entrada, resposta=texto)    # 05/11: o que a mae/o pai disseram o Dono sempre ouve (resumo em audio)
                if not prio and not recado_na_fila and not contexto.nao_responder(nome) and "G" not in flags and recados.promete_repassar(texto):
                    recado_na_fila = recados.enfileirar(nome, entrada, resposta=texto)    # prometeu repassar: o recado vai de verdade
                    if recado_na_fila:
                        _log(f"{nome} | recado enfileirado (promessa na resposta)")
                if aviso_novo:
                    linhas.append(aviso_novo if not recado_na_fila else "📩 " + aviso_novo.lstrip("⚠️ "))         # linha com ⚠️ => o relatorio vai para o WhatsApp do Dono
            else:
                linhas.append(f"⚠️ {nome}: falhou o envio ({r[:60]})")
                _log(f"{nome} | falha-envio | {r[:80]}")
        elif cod == "I":
            linhas.append(f"• {nome}: sem resposta necessária")
            _log(f"{nome} | ignorado")
        elif cod == "A":
            linhas.append(f"{'📩' if recado_na_fila else '⚠️'} {nome}: {texto[:140]}")
            _log(f"{nome} | avisar | {texto[:100]}")
        else:  # P: so quando o Claude julgou que depende do Dono; o texto e a pergunta exata
            linhas.append((f"{'📩' if recado_na_fila else '❓'} {nome}: {texto[:160]}") if texto else f"⏸ {nome}: segurei, aguardando você")
            _log(f"{nome} | segurado")
    try:   # entrega os recados da fila ao Dono (literais; se o WhatsApp falhar, a rotina tenta de novo)
        dono = contexto.contato("dono")
        if dono and recados.pendentes():
            with whatsapp.LOCK:
                recados.entregar(whatsapp.enviar, dono, audio=_audio_recado)
    except Exception as e:
        _log(f"recados: erro na entrega {e!r}")
    ULTIMO["linhas"] = list(linhas)
    if not linhas:  # tudo foi ignorado em silencio (grupos etc.): nao ha o que relatar
        return "Nenhuma conversa para atender (ignoradas)."
    relatorio = "Jarvis ✓ atendimento: " + " | ".join(linhas)
    # Autonomia total: o Dono so recebe relatorio quando ha algo para ele (aviso, pergunta ou problema); respostas normais nao viram ruido
    precisa_dele = any(l.startswith(("⚠️", "❓", "⏸")) for l in linhas)
    if relatar and precisa_dele and contexto.contato("dono"):
        whatsapp.enviar(contexto.contato("dono"), relatorio[:900])  # copia para o WhatsApp do Dono
    return relatorio
