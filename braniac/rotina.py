# -*- coding: utf-8 -*-
"""Rotinas diarias do Jarvis (pedido do Dono, 07/10/2026), todas LOCAIS e sem IA online:
 - 06:00 'bom dia': relatorio do que o Braniac/Claude fizeram de madrugada + resumo dos e-mails do dia + disco, no WhatsApp do Dono ('Eu').
 - de hora em hora: e-mail promissor de TRABALHO com PRAZO -> avisa o Dono e a Parceira (so o essencial: remetente, assunto, prazo; nunca o corpo).
Gmail e SOMENTE LEITURA e o conteudo dos e-mails nunca passa por IA online (ver gmail.py). Sem Gmail conectado a rotina avisa uma vez por dia como conectar."""
import json, re, threading, time
from datetime import datetime
from .store import DATA

ESTADO = DATA / "rotina.json"
RELATORIO = DATA / "relatorio_noturno.md"
HISTORICO = DATA / "relatorio_historico.md"   # relatorios ja entregues (nada se perde)
RUIDO_RELATORIO = re.compile(r"lembrou o Dono de '|A\.L\.M\.A\. lembrou", re.I)
HORA_BOM_DIA = 6
PRAZO = re.compile(r"\b(?:prazo|deadline|at[ée]\s+(?:o\s+dia\s+)?\d{1,2}(?:[/.]\d{1,2})?|inscri[cç][oõ]es?\s+(?:at[ée]|abertas)|due\s+(?:by|on|date)|apply\s+by|"
                   r"encerra(?:m)?\s+(?:em|dia|hoje|amanh[ãa])|vence(?:m)?\s+(?:em|dia|hoje|amanh[ãa])|[uú]ltimos?\s+dias|expira)\b", re.I)
TRABALHO = re.compile(r"\b(?:vaga|vagas|emprego|contrata[cç][ãa]o|processo\s+seletivo|entrevista|oportunidade|proposta|freelance|freela|job|hiring|position|"
                      r"recrutador|recruiter|candidatura|curr[ií]culo|projeto|or[çc]amento|contrato)\b", re.I)
RUIDO = re.compile(r"\b(?:unsubscribe|descadastr|newsletter|promo[cç][ãa]o|cupom|desconto|black\s*friday|oferta)\b", re.I)


def _ler():
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _gravar(d):
    DATA.mkdir(exist_ok=True)
    ESTADO.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def registrar(texto):
    """Anota no relatorio da madrugada (o Claude e o Braniac chamam isto ao terminar cada tarefa)."""
    DATA.mkdir(exist_ok=True)
    with RELATORIO.open("a", encoding="utf-8") as f:
        f.write(f"- {datetime.now():%d/%m %H:%M} · {texto.strip()}\n")


def promissor(assunto, texto=""):
    """(True, prazo) se parece oportunidade de trabalho COM prazo. Filtro por palavras: roda local, sem IA."""
    alvo = f"{assunto}\n{texto}"
    if not TRABALHO.search(alvo) or RUIDO.search(assunto):
        return False, ""
    m = PRAZO.search(alvo)
    return (True, m.group(0)) if m else (False, "")


def _gmail():
    from . import gmail
    return gmail


def emails_do_dia(horas=24, n=60):
    """[(id, remetente, assunto, nao_lida)] da caixa de entrada nas ultimas horas (so metadados)."""
    g = _gmail()
    dias = max(1, int(horas / 24 + 0.99))
    ids = [m["id"] for m in g._get("/messages", q=f"in:inbox newer_than:{dias}d", maxResults=n).get("messages", [])]
    out = []
    corte = time.time() - horas * 3600
    for i in ids:
        m = g._get(f"/messages/{i}", format="metadata", metadataHeaders=["From", "Subject", "Date"])
        if int(m.get("internalDate", 0)) / 1000 < corte:
            continue
        out.append((i, g._remetente(m)[:40], (g._cabecalho(m, "Subject") or "(sem assunto)")[:90], "UNREAD" in (m.get("labelIds") or [])))
    return out


def resumo_emails(horas=24):
    g = _gmail()
    if not g.logado():
        return "🔔 LEMBRETE: você ainda precisa LOGAR no Gmail para eu resumir seus e-mails e avisar de vagas com prazo. Abra http://127.0.0.1:8765/email no seu PC e siga o passo a passo (leva uns 5 min)."
    msgs = emails_do_dia(horas)
    if not msgs:
        return "📧 Nenhum e-mail novo nas últimas 24 h."
    prom = [(r, a, p) for _, r, a, _ in msgs for ok, p in [promissor(a)] if ok]
    ruido = sum(1 for _, r, a, _ in msgs if RUIDO.search(a))
    linhas = [f"📧 {len(msgs)} e-mails nas últimas 24 h ({sum(1 for m in msgs if m[3])} não lidos; ~{ruido} promoções/newsletters)."]
    if prom:
        linhas.append("⭐ Possíveis oportunidades com prazo:")
        linhas += [f"  • {r} — {a} [{p}]" for r, a, p in prom[:5]]
    outros = [(r, a) for _, r, a, _ in msgs if not RUIDO.search(a)][:8]
    if outros:
        linhas.append("Principais:")
        linhas += [f"  • {r} — {a}" for r, a in outros]
    return "\n".join(linhas)


def verificar_promissores(enviar_dono, enviar_parceira, horas=24):
    """Avisa UMA vez por e-mail promissor (guarda os ids). Devolve quantos avisou."""
    g = _gmail()
    if not g.logado():
        return 0
    est = _ler()
    vistos = set(est.get("alertados", []))
    novos = 0
    for i, rem, assunto, _ in emails_do_dia(horas):
        if i in vistos:
            continue
        ok, prazo = promissor(assunto)
        if not ok:
            # o assunto pode nao ter o prazo: olha o comeco do corpo (so localmente)
            if not TRABALHO.search(assunto) or RUIDO.search(assunto):
                continue
            ok, prazo = promissor(assunto, g.ler(i, max_chars=1500))
            if not ok:
                continue
        msg = f"📌 E-mail de trabalho com prazo ({prazo}): {rem} — {assunto}. Vale conferir na caixa de entrada."
        enviar_dono(msg)
        enviar_parceira("Parceira, aqui é o Jarvis. " + msg + " (aviso a pedido do Dono)")
        vistos.add(i)
        novos += 1
    est["alertados"] = list(vistos)[-300:]
    _gravar(est)
    return novos


DB1_BUSCA = "newer_than:7d (from:db1 OR from:inhire OR from:anymarket OR subject:DB1 OR subject:Anymarket)"


def verificar_db1(enviar_dono):
    """Candidatura DB1 (19/10/2026): avisa o Dono no WhatsApp UMA vez por e-mail da DB1/InHire. So metadados, tudo local. Devolve quantos avisou."""
    g = _gmail()
    if not g.logado():
        return 0
    est = _ler()
    vistos = set(est.get("db1_vistos", []))
    novos = 0
    for m in g._get("/messages", q=DB1_BUSCA, maxResults=10).get("messages", []):
        if m["id"] in vistos:
            continue
        msg = g._get(f"/messages/{m['id']}", format="metadata", metadataHeaders=["From", "Subject", "Date"])
        enviar_dono(f"📩 Chegou e-mail da DB1 sobre a sua candidatura: {g._remetente(msg)} — {g._cabecalho(msg, 'Subject')}. Abra o seu e-mail para ver e responder.")
        vistos.add(m["id"])
        novos += 1
    est["db1_vistos"] = list(vistos)[-100:]
    _gravar(est)
    return novos


def bom_dia(extras=""):
    """Texto do bom dia das 6h: o que foi feito de madrugada + e-mails + disco."""
    partes = ["Bom dia, Dono! ☀️ Aqui é o Jarvis com o relatório da madrugada."]
    try:
        feito = RELATORIO.read_text(encoding="utf-8").strip()
    except OSError:
        feito = ""
    partes.append("*O que foi feito:*\n" + feito if feito else "Nada novo registrado durante a madrugada.")
    try:
        partes.append(resumo_emails())
    except Exception as e:
        partes.append(f"📧 Não consegui ler os e-mails agora ({str(e)[:80]}).")
    try:
        import shutil
        d = [f"{l}: {shutil.disk_usage(l + ':/').free / 1e9:.0f} GB livres" for l in "CE" if __import__('os').path.exists(l + ':/')]
        partes.append("💽 " + " · ".join(d))
    except Exception:
        pass
    try:
        from . import guarda
        partes.append(guarda.resumo())
    except Exception:
        pass
    if extras:
        partes.append(extras)
    return "\n\n".join(partes)[:3800]


def _enviar(nome, texto):
    from . import wpp_arquivo
    return wpp_arquivo.enviar_texto(nome, texto)


def _para_fala(texto, maximo=230):
    """Deixa um registro do relatorio PRONUNCIAVEL: sem link, caminho, emoji, crase ou numero enorme; so a primeira frase."""
    t = re.sub(r"https?://\S+|[A-Za-z]:[\\/]\S+|\S+/\S+\.\w+|`[^`]*`", "", texto)
    t = re.sub(r"[🀀-🿿☀-➿←-⇿]", "", t)
    t = re.sub(r"\b\d{6,}\b", "", t)
    t = " ".join(t.replace("_", " ").replace("—", ",").replace("/", " de ").split())
    m = re.match(r"(.{40,%d}?[.!?])(\s|$)" % maximo, t)
    return (m.group(1) if m else t[:maximo]).strip(" -·")


def bom_dia_falado():
    """O bom dia das 6h como FALA (Dono, 10/10: audio, nunca relatorio por escrito). Texto corrido, curto, sem links nem listas."""
    partes = ["Bom dia, Dono! Aqui é o Jarvis com o resumo da madrugada."]
    try:
        feitos = [re.sub(r"^-\s*\d\d/\d\d\s+\d\d:\d\d\s*·\s*", "", l) for l in RELATORIO.read_text(encoding="utf-8").splitlines() if l.strip()]
    except OSError:
        feitos = []
    # 24/10: os lembretes da A.L.M.A. enchiam o relatorio e o que foi FEITO de madrugada ficava de fora (so as 6 ultimas linhas iam na fala)
    feitos = [f for f in feitos if not RUIDO_RELATORIO.search(f)]
    fala = [f for f in (_para_fala(x) for x in feitos[-12:]) if f]
    partes.append("O que foi feito: " + " ".join(fala) if fala else "De madrugada não houve nada novo para registrar.")
    try:        # 28/10: reuniao dos agentes (Cofre, Correio, Ilheu, Compasso, Tino): cada um relata o que tem; quem nao tem nada fica calado
        from . import reuniao_matinal
        r = reuniao_matinal.para_fala()
        partes.append(r if r else "Passei pelos agentes e nenhum tem nada urgente para reportar.")
    except Exception:
        partes.append("Não consegui reunir os agentes agora.")
    try:
        import shutil, os
        d = [f"o disco {l} tem {shutil.disk_usage(l + ':/').free / 1e9:.0f} gigas livres" for l in "CE" if os.path.exists(l + ":/")]
        partes.append("No computador, " + " e ".join(d) + ".")
    except Exception:
        pass
    try:
        from . import guarda
        u = guarda._ler().get("ultima") or {}
        ok = u.get("firewall_desligado") == [] and (u.get("defender") or {}).get("tempo_real") and not (u.get("falhas_login_1h") or 0)
        partes.append("A segurança do computador está em ordem." if ok else "Confira a segurança do computador: há algo fora do normal no painel.")
    except Exception:
        pass
    partes.append("Tenha um ótimo dia. Qualquer coisa, é só me chamar.")
    return " ".join(partes)[:3500]


def _enviar_audio(nome, texto):
    from . import voz, wpp_voz
    return wpp_voz.enviar_voz(nome, voz.falar_wav(texto))


def entregar_bom_dia(enviar_audio=_enviar_audio, enviar_texto=None):
    """Audio; se falhar duas vezes, UM aviso curto por escrito (para o Dono nao ficar sem saber). Devolve True se algo foi entregue."""
    from . import contexto
    nome = contexto.contato("dono") or "Eu"
    fala = bom_dia_falado()
    for _ in range(2):
        r = enviar_audio(nome, fala)
        if str(r).startswith("✅"):
            return True
    if enviar_texto:
        r = enviar_texto(nome, "Bom dia, Dono! Não consegui gerar o áudio agora. O resumo da madrugada está salvo; me peça que eu falo.")
        return str(r).startswith("✅")
    return False


CUIDADO_DIARIO = [   # (chave no estado, apelido do contato, a partir de que hora, texto(s) por dia da semana)
    ("cuidado_parceira", "parceira", 7, [
        "Bom dia, Parceira! ☀️ Aqui é o Jarvis. Como você está hoje? Dormiu bem?",
        "Bom dia, Parceira! 🌞 Passando pra saber como você tá hoje. Tá tudo bem por aí?",
        "Bom dia, Deusa! ☀️ Aqui é o Jarvis. Como você acordou hoje? Se precisar de qualquer coisa, é só falar.",
        "Bom dia, Parceira! 💛 Como você está? Já tomou café?",
        "Bom dia, Parceira! ☀️ Como tá o seu dia começando? Me conta como você está.",
        "Bom dia, Deusa! 🌷 O Jarvis aqui perguntando: como você está hoje?",
        "Bom dia, Parceira! ☀️ Domingo tranquilo? Como você está?"]),
    ("cuidado_mae", "mae", 8, [
        "Bom dia, minha tia! ☀️ Aqui é o Jarvis. Como você tá hoje? E o braço, melhorou?",
        "Bom dia, minha tia! 🌞 Como você amanheceu? O braço tá doendo menos?",
        "Bom dia, minha tia! ☀️ Passei pra saber como você está hoje. E o braço, como tá?",
        "Bom dia, minha tia! 💛 Aqui é o Jarvis. Dormiu bem? Como tá o braço hoje?",
        "Bom dia, minha tia! ☀️ Como você está hoje? Tá conseguindo se cuidar direitinho? E o braço?",
        "Bom dia, minha tia! 🌷 O Jarvis perguntando: como você tá? O braço melhorou?",
        "Bom dia, minha tia! ☀️ Domingo de descanso, né? Como você tá hoje? E o braço?"]),
    ("cuidado_pai", "pai", 9, [   # 16/11 (Dono): pai so AUDIO, voz do Zelo; nunca texto
        "Bom dia, Pai! Aqui é o Jarvis. Como é que o senhor tá hoje? Tá tudo certo por aí? Me manda um áudio contando.",
        "Bom dia, Pai! Passando pra saber do senhor. Dormiu bem? Tá tudo bem por aí?",
        "Oi, Pai, bom dia! É o Jarvis. Como o senhor tá se sentindo hoje? Precisa de alguma coisa?",
        "Bom dia, Pai! Como foi a noite? Tá tudo tranquilo aí? Se quiser, me manda um áudio.",
        "Bom dia, Pai! Aqui é o Jarvis, querendo saber como o senhor tá. Tá tudo certinho?",
        "Bom dia, Pai! Sábado chegou. Como o senhor tá? Tá tudo bem por aí?",
        "Bom dia, Pai! Domingo de descanso, né? Como o senhor tá hoje? Tá tudo certo?"]),
]
PERGUNTA_BRACO_ATE = "2026-11-15"      # a mae caiu de moto (10/2026): pergunta do braco ate esta data; depois so 'como você esta'


def cuidado_diario(agora, enviar, audio, estado_get=None, estado_set=None):
    """Bom dia + 'como voce esta?' todo dia para a Parceira, a Mae e (16/11) o pai, Pai, so em audio (pedido do Dono, 13/10). Texto fixo (sem IA online), 1x por dia por pessoa,
    a partir da hora indicada e ate as 21h; audio primeiro, texto se o audio falhar. A resposta delas cai no atendimento normal (que ja ve a pergunta no contexto)."""
    from . import contexto
    est = _ler()
    hoje = agora.strftime("%Y-%m-%d")
    feitos = []
    for chave, apelido, hora, textos in CUIDADO_DIARIO:
        if est.get(chave) == hoje or not (hora <= agora.hour < 21):
            continue
        nome = contexto.contato(apelido)
        if not nome:
            continue
        texto = textos[agora.weekday() % len(textos)]
        if apelido == "mae" and hoje > PERGUNTA_BRACO_ATE:
            texto = re.sub(r"\s*(?:E o braço[^?]*\?|O braço[^?]*\?|Como tá o braço[^?]*\?|E o braço, [^?]*\?)", "", texto).strip()
        if apelido == "pai":   # pai do Dono: SO audio (voz do Zelo); falhou -> tenta no proximo tick, nunca cai para texto
            from . import zelo
            ok = str((zelo.enviar_audio if audio is _enviar_audio else audio)(nome, texto)).startswith("✅")
            if ok:
                est = _ler()
                est[chave] = hoje
                _gravar(est)
                feitos.append(apelido)
                try:
                    from . import memoria
                    memoria.registrar_msg(nome, "C", texto, canal="whatsapp", audio=True)
                except Exception:
                    pass
            continue
        ok = False
        r = str(audio(nome, texto.replace("☀️", "").replace("🌞", "").replace("💛", "").replace("🌷", "").strip()))
        ok = r.startswith("✅")
        if not ok:
            ok = str(enviar(nome, texto)).startswith("✅")
        if ok:
            est = _ler()
            est[chave] = hoje
            _gravar(est)
            feitos.append(apelido)
            try:
                from . import memoria
                memoria.registrar_msg(nome, "C", texto, canal="whatsapp")     # entra no historico: a resposta dela e entendida no contexto
            except Exception:
                pass
    return feitos


def tick(agora=None, enviar=_enviar, audio=_enviar_audio):
    """Chamado a cada ~10 min pela thread. Faz o bom dia (uma vez por dia, a partir das 6h) e a checagem horaria de e-mails."""
    agora = agora or datetime.now()
    from . import funil
    avisar = funil.envolver(enviar)   # 16/11: aviso automatico ao Dono passa pelo funil (urgente na hora, resto no resumo)
    est = _ler()
    hoje = agora.strftime("%Y-%m-%d")
    if agora.hour >= HORA_BOM_DIA and est.get("bom_dia") != hoje:
        ok = entregar_bom_dia(audio, enviar)
        if ok:
            est = _ler()
            est["bom_dia"] = hoje
            _gravar(est)
            with HISTORICO.open("a", encoding="utf-8") as h:   # guarda antes de zerar
                h.write(f"\n## entregue em {hoje}\n" + RELATORIO.read_text(encoding="utf-8"))
            RELATORIO.write_text("", encoding="utf-8")        # relatorio entregue: comeca o proximo
    try:    # abas paradas do Chrome do Braniac: era o que mais pesava no PC
        from . import faxina_abas
        faxina_abas.tick()
    except Exception:
        pass
    try:    # Lupa: os 5 vídeos do Parceiro aprovados -> o Claude produz os próximos 5 (pedido do Dono, 13/11/2026)
        from .link import lote_parceiro
        lote_parceiro.tick(agora.timestamp())
    except Exception:
        pass
    try:    # PDFs do TCM que faltam no site, com ou sem vídeo (Dono, 16/11): 1x por dia, em segundo plano
        if agora.hour >= 8 and est.get("pdfs_tcm") != hoje:
            from .link import pdfs_tcm
            est["pdfs_tcm"] = hoje
            _gravar(est)
            threading.Thread(target=pdfs_tcm.enviar_faltando, daemon=True).start()
    except Exception:
        pass
    try:    # esteira das capitais: refaz as contas na fonte e confere roteiro/tela/legenda/voz a cada 3 h (Dono, 15/11/2026)
        from .link import conferir_capitais
        threading.Thread(target=conferir_capitais.tick, args=(agora.timestamp(),), daemon=True).start()
    except Exception:
        pass
    try:    # bom dia + 'como voce esta?' para a Parceira e a Mae, todo dia (decisao do Dono, 13/10)
        cuidado_diario(agora, enviar, audio)
    except Exception:
        pass
    # 15/11: pendências só quando o Dono pergunta (delegacao 'Mapa'); o lembrete 10h/17h saiu
    try:    # recados para o Dono que ficaram na fila (WhatsApp indisponivel na hora): tenta de novo
        from . import contexto as _c, recados
        if recados.pendentes():
            recados.entregar(enviar, _c.contato("dono") or "Eu", audio=lambda d, f: audio(d, f))
    except Exception:
        pass
    try:    # Telegram da Mariana (Alma): responde o que ela escreveu; nao vai para o GitHub (telegram_ex.py fica fora do repositorio)
        from . import contexto as _cx, telegram_ex
        telegram_ex.tick(lambda m: enviar(_cx.contato("dono") or "Eu", m))
    except Exception:
        pass
    try:    # guarda de seguranca: a cada tick (~10 min), a qualquer hora (ataque nao espera o dia); so avisa o Dono
        from . import contexto, delegacao, guarda
        guarda.verificar(delegacao.via_jarvis("Forja", lambda m: avisar(contexto.contato("dono") or "Eu", m)))
    except Exception:
        pass
    try:    # agentes Correio (e-mail de pessoa/oferta) e Garimpeiro (vagas remotas do dia): avisam o Dono pelo Jarvis
        from . import contexto, correio, modulos, vagas
        modulos.exigir("email")
        from . import delegacao
        _avisar = lambda m: avisar(contexto.contato("dono") or "Eu", m)
        correio.verificar(delegacao.via_jarvis("Correio", _avisar))
        vagas.verificar(delegacao.via_jarvis("Garimpeiro", _avisar), agora)
    except Exception:
        pass
    try:    # candidaturas (manha/tarde/noite): aciona o Claude com navegador ate 5 vagas por janela; so avisa o Dono pelo Jarvis
        from . import candidatura_rotina, contexto, delegacao
        candidatura_rotina.tick(agora, delegacao.via_jarvis("Nando", lambda m: avisar(contexto.contato("dono") or "Eu", m)))
    except Exception:
        pass
    try:    # agente financeiro (Cofre): le a InfinitePay (so leitura) e acompanha a meta de saldo (data/pessoal.json) ate o 5o dia util
        from . import contexto, financeiro, modulos
        modulos.exigir("financeiro")
        from . import delegacao
        financeiro.verificar(delegacao.via_jarvis("Cofre", lambda m: avisar(contexto.contato("dono") or "Eu", m)))
    except Exception:
        pass
    try:    # vaquinha: a cada 6 h (8h, 14h, 20h) pergunta o saldo a Parceira; ela responde e o site e atualizado
        from . import contexto, vaquinha
        from . import delegacao
        vaquinha.tick(delegacao.via_jarvis("Vaquinha", lambda m: enviar(contexto.contato("parceira") or "Parceira", m)), delegacao.via_jarvis("Vaquinha", lambda m: avisar(contexto.contato("dono") or "Eu", m)), agora)
    except Exception:
        pass
    try:    # empresa de desenvolvimento (2o andar): daily 1x/dia util e um passo de ticket por ciclo (so os agentes gratis; o senior e o Claude, com teto)
        from . import contexto, empresa_dev, modulos
        modulos.exigir("programacao")
        empresa_dev.tick(agora, lambda m: avisar(contexto.contato("dono") or "Eu", m))
    except Exception:
        pass
    try:    # empresa de marketing Fornalha (3o andar): pauta do dia a partir das 7h e um passo de pedido por ciclo (Gemini/Drive; abas abrem e fecham)
        from . import contexto, empresa_mkt, modulos
        modulos.exigir("marketing")
        empresa_mkt.tick(agora, lambda m: avisar(contexto.contato("dono") or "Eu", m))
    except Exception:
        pass
    try:    # Quantix (4o andar): Vigil fecha em papel o que tocou stop/alvo (so simulacao; sem posicao nao usa rede)
        from . import contexto, empresa_inv, modulos
        modulos.exigir("investimentos")
        empresa_inv.tick(agora, lambda m: avisar(contexto.contato("dono") or "Eu", m))
    except Exception:
        pass
    try:    # caçador de freelas: feeds públicos + Ollama local; só avisa o Dono (nunca manda proposta)
        from . import contexto, freelas
        freelas.tick(agora, lambda m: avisar(contexto.contato("dono") or "Eu", m))
    except Exception:
        pass
    try:    # Claquete (5o andar): um passo de corte de video por ciclo (Whisper/ffmpeg locais; nada e publicado sem o OK do Dono)
        from . import contexto, empresa_cortes, modulos
        modulos.exigir("cortes_video")
        empresa_cortes.tick(agora, lambda m: avisar(contexto.contato("dono") or "Eu", m))
    except Exception:
        pass
    try:    # Pechincha (6o andar): um passo de pesquisa de compra por ciclo; so recomenda, nunca compra
        from . import contexto, empresa_compras, modulos
        modulos.exigir("compras")
        empresa_compras.tick(agora, lambda m: avisar(contexto.contato("dono") or "Eu", m))
    except Exception:
        pass
    try:    # BRAIN CENTER: consolida a memoria so quando a maioria dos agentes esta ociosa (barato quando nao esta; roda em thread)
        from . import braincenter
        braincenter.tick()
    except Exception:
        pass
    try:    # temperatura do notebook: registra e avisa o Dono se esquentar (1 aviso por hora)
        from . import contexto, delegacao, termico
        termico.verificar(delegacao.via_jarvis("Forja", lambda m: avisar(contexto.contato("dono") or "Eu", m)))
    except Exception:
        pass
    try:    # manutencao da madrugada (03h): testes + dependencias + modelos; so confere e relata no bom dia (nao instala nada)
        from . import manutencao
        manutencao.tick(agora)
    except Exception:
        pass
    try:    # avisos "so de hoje" no dossie (ex.: viagem do Dono) saem sozinhos no dia seguinte
        from . import contexto
        pend = (contexto._ler()["dossie"].get("tom") or {}).get("pendente") or ""
        if "AVISO DE HOJE (" in pend:
            import re as _re
            m = _re.search(r"AVISO DE HOJE \((\d\d)/(\d\d)/(\d{4})", pend)
            if m and datetime(int(m[3]), int(m[2]), int(m[1])).date() < agora.date():
                contexto.registrar_dossie("tom", "pendente", _re.sub(r"\s*AVISO DE HOJE \(.*?Depois de hoje ignore este aviso\.", "", pend, flags=_re.S).strip())
    except Exception:
        pass
    try:    # Claudinho (gerente master): audita o que o Jarvis respondeu e ensina regras (local; o Claude so destila, 2x/dia, janela de 48 h)
        from . import claudinho
        claudinho.tick()
    except Exception:
        pass
    try:    # A.L.M.A.: rotinas e lembretes da agenda; na hora certa ela aciona o Jarvis (protocolo em compasso.py)
        from . import compasso
        compasso.tick(agora, enviar)
    except Exception:
        pass
    try:    # resumo dos avisos segurados pelo funil (9h, 13h, 19h)
        funil.tick(agora, enviar, audio)
    except Exception:
        pass
    est = _ler()
    if 7 <= agora.hour < 22 and agora.timestamp() - est.get("ultima_checagem", 0) > 3300:   # sem acordar ninguem de noite
        est["ultima_checagem"] = agora.timestamp()
        _gravar(est)
        try:
            from . import contexto
            dono = contexto.contato("dono") or "Eu"
            verificar_promissores(lambda m: avisar(dono, m), lambda m: enviar(contexto.contato("parceira") or "Parceira", m))
        except Exception:
            pass
    try:   # DB1: a cada ciclo (10 min), sem esperar a checagem horaria
        from . import contexto as _cx
        verificar_db1(lambda m: enviar(_cx.contato("dono") or "Eu", m))
    except Exception:
        pass


def iniciar(intervalo_s=600):
    def laco():
        while True:
            try:
                tick()
            except Exception:
                pass
            time.sleep(intervalo_s)
    threading.Thread(target=laco, daemon=True, name="braniac-rotina").start()
