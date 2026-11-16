# -*- coding: utf-8 -*-
"""ATENDIMENTO AUTOMATICO do WhatsApp: o Jarvis olha a lista de conversas o tempo todo e responde sozinho (em audio) a quem
escrever, sem ninguem precisar mandar. As decisoes continuam sendo do Claude (canal JV1 ao vivo ou um Claude de fundo).

TRAVAS (todas ativas):
- Liga/desliga SO pela interface local do PC (padrao: DESLIGADO). Qualquer canal remoto so consegue DESLIGAR.
- Responde conversas cuja ULTIMA mensagem e DELA e ninguem respondeu (lida ou nao), de hoje e dentro da janela de idade;
  ignora o chat do Dono (outro vigia), grupos, contas automaticas e empresas. Cada situacao e tratada uma vez (assinatura da conversa).
- Espera a pessoa terminar de escrever (a conversa precisa ficar estavel alguns segundos).
- Limites: por pessoa/hora, total/hora e total/dia; so dentro da janela de horario; ignora mensagens velhas.
- Mesmas validacoes do atendimento (sem link/numero/Pix/senha, nunca 'ocupado', tamanho) + log de auditoria + relatorio ao Dono.
- Para sozinho com o Braniac desligado (/desligar, modo jogo).
"""
import json, re, threading, time
from datetime import datetime
from pathlib import Path
from . import atender, contexto, dono, monitor_dono, power, whatsapp
from .store import DATA

FOTO_NA_HORA = True  # ao ligar, ja tira a foto das conversas (testes desligam isto)
_CICLO = threading.Lock()  # um ciclo por vez (o da foto inicial nao corre junto com o do loop)
ARQ = DATA / "vigia_estado.json"
LOG = DATA / "vigia.log"

CFG_PADRAO = {
    "intervalo_s": 10,          # de quanto em quanto tempo olha a lista
    "estavel_s": 8,
    "teto_espera_s": 300,       # ninguem espera mais que isso: passou, o atendimento fura os limites por hora (1x por mensagem)            # a conversa precisa ficar sem mudar por isso antes de responder
    "janela": ["07:00", "23:59"],
    "max_por_chat_hora": 3,
    "max_por_hora": 15,
    "max_por_dia": 60,
    "max_idade_h": 12,
}


def _log(txt):
    DATA.mkdir(exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {txt}\n")


def _estado():
    try:
        return json.loads(ARQ.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _salvar(e):
    DATA.mkdir(exist_ok=True)
    ARQ.write_text(json.dumps(e, ensure_ascii=False), encoding="utf-8")


def cfg_de(cfg_router=None):
    c = dict(CFG_PADRAO)
    c.update((cfg_router or {}).get("atendimento_auto", {}))
    return c


# ---------- liga / desliga ----------

def ligar():
    """Liga o atendimento automatico. SO a interface local chama isto. Nao apaga o que ja foi tratado (religar nao reenvia nada)."""
    power.set_atendimento_auto(True)
    e = _estado()
    e["estavel"] = {}
    _salvar(e)
    _log("LIGADO")


def desligar():
    power.set_atendimento_auto(False)
    _log("DESLIGADO")


def resumo():
    e = _estado()
    agora = time.time()
    envios = [x for x in e.get("envios", []) if agora - x[1] < 3600]
    return {"ligado": power.atendimento_auto(), "respostas_ultima_hora": len(envios), "tratadas": len(e.get("tratados", {}))}


# ---------- regras ----------

def dentro_da_janela(janela, agora=None):
    agora = agora or datetime.now()
    ini, fim = (tuple(int(x) for x in h.split(":")) for h in janela)
    return ini <= (agora.hour, agora.minute) < fim


def limite_ok(est, nome, agora, cfg):
    """Respeita os limites por pessoa/hora, total/hora e total/dia."""
    envios = est.setdefault("envios", [])
    envios[:] = [x for x in envios if agora - x[1] < 86400]
    hora = [x for x in envios if agora - x[1] < 3600]
    dia_hoje = [x for x in envios if datetime.fromtimestamp(x[1]).date() == datetime.fromtimestamp(agora).date()]
    return (len([x for x in hora if x[0] == nome]) < cfg["max_por_chat_hora"]
            and len(hora) < cfg["max_por_hora"] and len(dia_hoje) < cfg["max_por_dia"])


def _linhas_wpp():
    from . import whatsapp
    W = whatsapp._wpp()
    with whatsapp.LOCK, W.WA() as w:
        return json.loads(w.js(dono.JS_LINHAS))


OUTBOX = DATA / "outbox_dono.txt"


def enviar_outbox(enviar=None, enviar_audio=None, enviar_arquivo=None, enviar_voz=None):
    """Recados para o Dono que outras rotinas (ex.: busca de vagas do Claude) gravam em data/outbox_dono.txt.
    O Claude nao mexe no WhatsApp: o Braniac entrega. Blocos separados por uma linha '---'. Devolve quantos enviou.
    11/11: bloco que comeca com [audio] sai em AUDIO (o Dono nao le bem), dentro do servidor e sob a trava do WhatsApp (de fora, o audio sai cortado)."""
    if not OUTBOX.exists():
        return 0
    try:
        texto = OUTBOX.read_text(encoding="utf-8-sig").strip()
    except OSError:
        return 0
    if not texto:
        return 0
    bruto = texto
    blocos = [b.strip() for b in re.split(r"(?m)^\s*---\s*$", texto) if b.strip()]
    if enviar is None:
        from . import whatsapp
        def enviar(dest, msg):
            with whatsapp.LOCK:
                return whatsapp.enviar(dest, msg)
    dono_nome = contexto.contato("dono")
    feitos = 0
    for b in blocos:
        if b.lower().startswith("[resumo]"):
            # 16/11: aviso automatico (esteira, conferencia, painel) nao sai na hora: vai para o resumo do funil (9h/13h/19h)
            from . import funil
            funil.passar(b[8:].strip(), "outbox")
            feitos += 1
            continue
        if b.lower().startswith("[arquivo]"):
            # 14/11: [arquivo] caminho na 1a linha, legenda no resto (ex.: teste de video do estudio); sai como documento, sob a trava
            linhas = b[9:].strip().splitlines() or [""]
            if enviar_arquivo is None:
                from . import wpp_arquivo
                enviar_arquivo = wpp_arquivo.enviar_arquivo
            r = enviar_arquivo(dono_nome, linhas[0].strip(), "\n".join(linhas[1:]).strip()[:900])
        elif b.lower().startswith("[alma]"):
            # 16/11: a ALMA manda mensagem ao Dono (texto + audio na voz dela). Sem texto no bloco, ela mesma compoe com o modelo local.
            from . import alma_cuida, alma_mente
            texto = b[6:].strip()
            if texto == "@novidades":     # a Alma se apresenta e conta as novidades com as palavras dela (so os fatos de alma_mente.FATOS_NOVOS)
                texto = alma_mente.apresentacao()
                if not texto:
                    _log("outbox: [alma] @novidades: o modelo local nao acertou, nada enviado")
                    feitos += 1
                    continue
            texto = texto or alma_mente.mensagem_livre()
            r = enviar(dono_nome, texto[:1500])
            if str(r).startswith("✅"):
                alma_cuida._audio_da_alma(texto)
        elif b.lower().startswith("[voz]"):
            # 15/11: [voz] caminho.wav = manda ESSE wav como mensagem de voz (teste de motores de voz; o [audio] sempre usa a voz da cadeia)
            caminho = Path(b[5:].strip().splitlines()[0].strip().strip('"'))
            if caminho.suffix.lower() != ".wav" or not caminho.is_file():
                _log(f"outbox: [voz] ignorado, wav nao encontrado ({caminho.name})")
                feitos += 1
                continue
            if enviar_voz is None:
                from . import wpp_voz
                enviar_voz = wpp_voz.enviar_voz
            r = enviar_voz(dono_nome, caminho.read_bytes())
        elif b.lower().startswith("[audio]"):
            if enviar_audio is None:
                from . import atender
                enviar_audio = atender._audio_recado
            r = enviar_audio(dono_nome, b[7:].strip()[:1200])
        else:
            r = enviar(dono_nome, ("Claudinho (via Braniac): " + b)[:1500])
        if not str(r).startswith("✅"):
            _log(f"outbox: falhou ({str(r)[:80]}); tenta de novo no proximo ciclo")
            break
        feitos += 1
    restante = blocos[feitos:]
    try:    # 16/11: o que outro processo gravou enquanto entregavamos nao pode sumir
        agora_txt = OUTBOX.read_text(encoding="utf-8-sig").strip()
        if agora_txt != bruto:
            novo = agora_txt[len(bruto):] if agora_txt.startswith(bruto) else agora_txt
            restante += [b.strip() for b in re.split(r"(?m)^\s*---\s*$", novo) if b.strip() and b.strip() not in blocos]
    except OSError:
        pass
    if restante:
        OUTBOX.write_text("\n---\n".join(restante), encoding="utf-8")
    else:
        OUTBOX.unlink(missing_ok=True)
    if feitos:
        _log(f"outbox: {feitos} recado(s) entregue(s) ao Dono")
    return feitos



def _rodar_atendimento(cands, cfg):
    return atender.atender(max_chats=len(cands), somente=cands, max_idade_h=cfg["max_idade_h"], pular_grupos=True, relatar=True)


_ULT_REABERTURA = [0.0]


def ciclo(cfg, linhas=None, rodar=None, agora=None, so_prioritarios=False, apresentar_fn=monitor_dono.apresentar, ouvir_fn=monitor_dono.ouvir_audio_do_dono, falar_fn=monitor_dono.falar):
    """Um ciclo do vigia. Devolve um dict com o que fez (para log/teste). linhas/rodar/agora sao injetaveis.
    Criterio: a ULTIMA mensagem da conversa e DELA (sem o icone de status de mensagem nossa) e e de hoje, dentro da janela de idade.
    Ler a conversa (no celular ou o Jarvis ao 'olhar') nao tira a conversa da fila: o que conta e ninguem ter respondido."""
    agora = agora if agora is not None else time.time()
    linhas = linhas if linhas is not None else _linhas_wpp()
    est = _estado()
    tratados = est.setdefault("tratados", {})       # nome -> assinatura (preview+hora) ja tratada
    estavel = est.setdefault("estavel", {})
    tentativas = est.setdefault("tentativas", {})
    dono_nome = contexto.contato("dono")
    dt = datetime.fromtimestamp(agora)

    candidatos = []
    feito_dono = []
    for c in linhas:
        nome, sig = c["nome"], c["resumo"]           # sem o contador de nao lidas: ler nao muda o que esta sem resposta
        if nome != dono_nome and nome not in est.get("grupos", []) and c.get("nossa") and est.setdefault("apres_dono", {}).get(nome) != sig:
            # COMANDOS DO DONO (texto ou voz) valem mesmo em conversa silenciada: se apresentar, silenciar/liberar, repassar uma fala
            texto = None
            if monitor_dono.interpretar(sig)[0]:
                texto = sig
            elif monitor_dono.audio_curto_do_dono(c, agora) and (lambda i: i is not None and i <= 0.1)(atender.idade_linha(sig, dt)):
                est["voz_dono"] = [t for t in est.get("voz_dono", []) if agora - t < 3600]    # audio curto do Dono: ouve (local); limite por hora
                if len(est["voz_dono"]) < monitor_dono.MAX_POR_HORA:
                    est["voz_dono"].append(agora)
                    try:
                        texto = ouvir_fn(nome)
                    except Exception as e:
                        _log(f"{nome} | audio do dono: erro ao ouvir ({str(e)[:60]})")
                est["apres_dono"][nome] = sig
            if texto and monitor_dono.interpretar(texto)[0]:
                est["apres_dono"][nome] = sig
                acao, conteudo = monitor_dono.interpretar(texto)
                try:
                    r = monitor_dono.executar(nome, acao, conteudo, apresentar_fn, falar_fn)
                except Exception as e:
                    r = f"erro: {str(e)[:80]}"
                _log(f"{nome} | comando do dono: {acao} | {str(r)[:60]}")
                feito_dono.append(nome)
                continue
            if est["apres_dono"].get(nome) == sig:
                continue
        if nome == dono_nome or contexto.nao_responder(nome) or nome in est.get("grupos", []):
            continue
        prio = contexto.prioritario(nome)
        if so_prioritarios and not prio:
            continue                                  # fora do horario so a Layla e atendida
        if re.search(r"(?i)\| (gravando [aá]udio|digitando|recording audio|typing)\.*$", sig):
            continue                                  # 'gravando audio...'/'digitando...' nao e mensagem nova (24/10: a mae recebeu 4 respostas seguidas)
        if c.get("nossa") and not contexto.saudacao_automatica(sig):   # a ultima e nossa: nada a responder (a saudacao automatica do WhatsApp Business NAO conta)
            # (NAO vira 'tratada': se a leitura
            estavel.pop(nome, None)                  # do icone mudar, a conversa precisa continuar elegivel)
            tratados.pop(nome, None)
            continue
        if tratados.get(nome) == sig:
            continue
        idade = atender.idade_linha(sig, dt)
        if idade is None or idade > cfg["max_idade_h"]:  # 'Ontem', dia da semana, data ou muito antiga: nao responde de repente
            tratados[nome] = sig
            continue
        visto = estavel.get(nome)
        if not visto or visto["sig"] != sig:         # mudou de novo: reinicia a espera (a pessoa pode estar digitando)
            estavel[nome] = {"sig": sig, "desde": agora}
            continue
        if agora - visto["desde"] < cfg["estavel_s"]:
            continue
        # Dono (15/10): ninguem espera mais de 5 min. Passou o teto -> fura limites e desistencia UMA vez por mensagem (a neutra/apresentacao sai)
        urgente = agora - visto["desde"] >= cfg.get("teto_espera_s", 300) and est.setdefault("urgente_feito", {}).get(nome) != sig
        if not prio and not urgente and tentativas.get(f"{nome}|{sig}", 0) >= 2:  # tentou 2x sem conseguir tratar: desiste desta (nao entra em laco)
            tratados[nome] = sig
            _log(f"{nome} | desistiu apos 2 tentativas")
            continue
        if not prio and not urgente and not limite_ok(est, nome, agora, cfg):     # limite atingido: NAO marca como tratado; tenta de novo quando liberar
            if est.setdefault("limite_logado", {}).get(nome) != sig:   # loga so uma vez por conversa (antes enchia o log a cada 20 s)
                est["limite_logado"][nome] = sig
                _log(f"{nome} | limite atingido: aguardando")
            continue
        est["atendidos"] = [x for x in est.setdefault("atendidos", []) if agora - x[1] < 3600]
        if not prio and not urgente and len([x for x in est["atendidos"] if x[0] == nome]) >= 8:   # anti-laco: no maximo 8 tentativas por hora na mesma conversa (a Layla nao: o laco dela e cortado por contexto.encerramento)
            if est.setdefault("laco_logado", {}).get(nome) != sig:       # nunca mais em silencio: fica no log e o Dono pode ver
                est["laco_logado"][nome] = sig
                _log(f"{nome} | anti-laco: 8 tentativas na ultima hora, aguardando")
            continue
        if urgente:
            est["urgente_feito"][nome] = sig
            _log(f"{nome} | esperou mais de {cfg.get('teto_espera_s', 300) // 60} min: atendimento forcado")
        candidatos.append((nome, sig))

    feito = {"candidatos": [n for n, _ in candidatos], "enviados": [], "comando_dono": feito_dono}
    if candidatos:
        nomes = [n for n, _ in candidatos]
        est.setdefault("atendidos", []).extend([n, agora] for n in nomes)
        _log(f"atendendo: {nomes}")
        for n, sig in candidatos:
            tentativas[f"{n}|{sig}"] = tentativas.get(f"{n}|{sig}", 0) + 1
        _salvar(est)
        (rodar or (lambda cs: _rodar_atendimento(cs, cfg)))(nomes)
        enviados = list(atender.ULTIMO.get("enviados", []))
        resolvidos = set(atender.ULTIMO.get("tratados", [])) | set(enviados)
        feito["enviados"] = enviados
        for g in atender.ULTIMO.get("grupos", []):      # grupo/comunidade: nunca recebe resposta sozinha, entao a vigia nem tenta mais
            if g not in est.setdefault("grupos", []):
                est["grupos"].append(g)
        for n in enviados:
            est.setdefault("envios", []).append([n, agora])
        for n, sig in candidatos:
            if n in resolvidos:                      # decidido (enviou, ignorou, avisou ou perguntou ao Dono): nao repete
                tratados[n] = sig
                estavel.pop(n, None)
                tentativas.pop(f"{n}|{sig}", None)
    _salvar(est)
    return feito


def _safe_linhas():
    try:
        return _linhas_wpp()
    except Exception:
        return []


class _Queda:
    """Chrome do agente fora do ar (09-10/10: 155 linhas iguais de ConnectionRefused no log, nada era feito). Agora: loga o 1o erro e
    depois 1 vez por hora; com a porta 9222 fechada, reabre o Chrome do agente no maximo 1 vez por hora."""
    def __init__(self):
        self.desde, self.ult_log, self.ult_reabrir = None, 0.0, 0.0

    def registrar(self, e, agora=None, reabrir=None):
        agora = agora or time.time()
        if self.desde is None:
            self.desde = agora
        if isinstance(e, ConnectionRefusedError) and agora - self.ult_reabrir >= 3600:
            self.ult_reabrir = agora
            try:                                  # falha aqui nao pode derrubar a thread do vigia
                (reabrir or _reabrir_chrome)()
            except Exception as e2:
                _log(f"nao consegui reabrir o Chrome do agente: {e2!r}")
        if agora - self.ult_log >= 3600:
            self.ult_log = agora
            return True
        return False

    def voltou(self):
        caiu, self.desde, self.ult_log, self.ult_reabrir = self.desde is not None, None, 0.0, 0.0
        return caiu


def _reabrir_chrome():
    from . import sentinela
    if sentinela.porta_aberta(9222):
        return
    bat = sentinela.RAIZ / "monitor" / "start-chrome-debug.bat"
    if bat.exists():
        import subprocess
        subprocess.Popen(["cmd", "/c", str(bat)], cwd=str(bat.parent), creationflags=0x08000000 | 0x00000008,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _log("Chrome do agente estava fechado: reabrindo")


_QUEDA = _Queda()


_ronda_fim = threading.Event()


def _vigiar_travamento(tid, limite_s=240):
    """10/11: o atendimento da Mae ficou 13 min preso (aba do WhatsApp congelada) sem nenhum log. Se uma ronda passar de `limite_s`,
    grava em que linha ela esta parada, para achar a causa em vez de adivinhar."""
    _ronda_fim.clear()

    def olhar():
        if _ronda_fim.wait(limite_s):
            return
        import sys
        import traceback
        f = sys._current_frames().get(tid)
        onde = " | ".join(" ".join(l.split()) for l in traceback.format_stack(f)[-4:]) if f else "?"
        _log(f"RONDA LENTA (>{limite_s}s), parada em: {onde}")
    threading.Thread(target=olhar, daemon=True).start()


def iniciar(router):
    """Thread do vigia automatico. Nao faz nada com o atendimento automatico desligado, com o Braniac desligado, fora da janela de horario
    ou enquanto um atendimento manual ainda roda."""
    from . import jarvis

    def loop():
        espera = 5
        while True:
            time.sleep(espera)
            cfg = cfg_de(router.cfg)
            espera = cfg["intervalo_s"]
            try:
                if not power.atendimento_auto() or power.pausado():
                    continue
                fora = not dentro_da_janela(cfg["janela"])       # fora do horario so a Layla (prioridade total)
                if not jarvis._ATENDENDO.acquire(blocking=False):  # um atendimento manual esta em andamento
                    continue
                _vigiar_travamento(threading.get_ident())
                try:
                    with _CICLO:
                        enviar_outbox()
                        ciclo(cfg, so_prioritarios=fora)
                finally:
                    _ronda_fim.set()
                    jarvis._ATENDENDO.release()
            except Exception as e:
                espera = 60  # Chrome do agente fechado etc.: nao martelar
                if _QUEDA.registrar(e):
                    _log(f"ERRO: {e!r}")
                    whatsapp.curar_se_travada(e, _log)      # aba travada: fecha e abre de novo (no maximo 1x por 10 min)
            else:
                if _QUEDA.voltou():
                    _log("WhatsApp do agente voltou a responder")
    t = threading.Thread(target=loop, daemon=True, name="braniac-vigia")
    t.start()
    return t
