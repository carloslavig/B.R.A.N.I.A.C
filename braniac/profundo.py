# -*- coding: utf-8 -*-
"""MODO PROFUNDO (24/10/2026, pedido do Dono: 'funcionar alem de pergunta e resposta... pode demorar, desde que de a melhor resposta/acao'):
em vez de responder de primeira, o Jarvis PLANEJA, executa cada etapa com as ferramentas (pesquisa, conselho de IAs, PC, notebook, leis...),
CONFERE o resultado contra o objetivo, corrige o que faltar e so entao entrega. Roda em segundo plano; avisa o andamento e manda o final
por texto e em AUDIO no WhatsApp do Dono. Nunca inventa: etapa sem evidencia vira 'nao confirmei'."""
import json
import re
import threading
import time

MAX_ETAPAS = 6
RODADAS_CONFERENCIA = 2
ATIVO = {}


def _json(txt):
    m = re.search(r"\{.*\}", txt or "", re.S)
    try:
        return json.loads(m.group(0), strict=False) if m else {}
    except ValueError:
        return {}


def planejar(perguntar, objetivo):
    r = perguntar(
        "Planeje como cumprir o OBJETIVO do Dono do JEITO MAIS COMPLETO E CONFIAVEL, sem pressa. Responda SO um JSON: "
        '{"etapas":["etapa 1 concreta","etapa 2"],"pronto_quando":"como saber que esta bem feito"} com no maximo %d etapas, cada uma uma acao que '
        "da para fazer com ferramentas (pesquisar na web, ler paginas, consultar IAs/conselho, procurar arquivos, usar o notebook, consultar leis/banco). "
        "Descreva cada etapa pelo QUE descobrir/fazer (nao cite nomes de ferramentas) e NUNCA use o Claude. Evite etapas que dependam so de opiniao sua: busque evidencia.\nOBJETIVO: %s" % (MAX_ETAPAS, objetivo))
    d = _json(r)
    etapas = [str(e) for e in (d.get("etapas") or []) if str(e).strip()][:MAX_ETAPAS]
    return etapas or [objetivo], d.get("pronto_quando") or "o objetivo foi atendido com evidencias"


def executar(objetivo, agente, perguntar, avisar=None, entregar=None):
    """agente(texto) -> resultado de uma etapa com ferramentas; perguntar(texto) -> IA sem ferramentas. Devolve o texto final."""
    t0 = time.time()
    etapas, pronto = planejar(perguntar, objetivo)
    if avisar:
        avisar("🧭 Modo profundo: %d etapa(s): " % len(etapas) + " → ".join(e[:50] for e in etapas))
    notas = []
    for i, e in enumerate(etapas, 1):
        try:
            r = agente("OBJETIVO GERAL: %s\nETAPA %d/%d: %s\nJA APURADO:\n%s\nFaca SO esta etapa, use as ferramentas, e responda com os FATOS achados "
                       "(e o que nao conseguiu confirmar)." % (objetivo, i, len(etapas), e, "\n".join(notas)[-3000:] or "nada ainda"))
        except Exception as ex:
            r = "(etapa falhou: %s)" % str(ex)[:100]
        notas.append("[%d] %s -> %s" % (i, e, str(r)[:1200]))
        if avisar:
            avisar("✔ etapa %d/%d feita" % (i, len(etapas)))
    final = perguntar("OBJETIVO: %s\nPRONTO QUANDO: %s\nRESULTADOS DAS ETAPAS:\n%s\n\nMonte a MELHOR resposta final para o Dono, em portugues simples, curta e "
                      "direta, so com o que as etapas confirmaram (o que nao foi confirmado, diga)." % (objetivo, pronto, "\n".join(notas)))
    for _ in range(RODADAS_CONFERENCIA):
        v = _json(perguntar("Confira com rigor se a RESPOSTA atende o OBJETIVO e se nao tem nada inventado. Responda SO JSON: "
                            '{"ok":true,"falta":"o que falta ou esta sem evidencia"}.\nOBJETIVO: %s\nRESPOSTA:\n%s\nEVIDENCIAS:\n%s'
                            % (objetivo, final, "\n".join(notas)[-6000:])))
        if v.get("ok", True) or not v.get("falta"):
            break
        if avisar:
            avisar("🔁 corrigindo: " + str(v["falta"])[:100])
        extra = agente("OBJETIVO GERAL: %s\nCORRIJA/COMPLETE: %s\nJA APURADO:\n%s" % (objetivo, v["falta"], "\n".join(notas)[-3000:]))
        notas.append("[correcao] %s" % str(extra)[:1200])
        final = perguntar("OBJETIVO: %s\nEVIDENCIAS:\n%s\nRefaca a melhor resposta final, curta, so com fatos confirmados." % (objetivo, "\n".join(notas)))
    final = (final or "").strip() or "Nao consegui concluir com confianca."
    final += "\n\n(feito no modo profundo, %d min)" % max(1, int((time.time() - t0) / 60))
    if entregar:
        entregar(final)
    return final


def em_segundo_plano(objetivo, agente, perguntar, avisar=None, entregar=None):
    if ATIVO.get("rodando"):
        return "Ja estou num trabalho profundo: %s. Aguarde terminar." % ATIVO.get("objetivo", "")[:80]
    ATIVO.update(rodando=True, objetivo=objetivo)

    def _roda():
        try:
            executar(objetivo, agente, perguntar, avisar, entregar)
        except Exception as e:
            if avisar:
                avisar("⚠️ Modo profundo parou: %s" % str(e)[:150])
        finally:
            ATIVO.clear()
    threading.Thread(target=_roda, daemon=True).start()
    return "Comecei a trabalhar nisso a fundo. Pode demorar; te aviso e mando o resultado em audio no WhatsApp quando terminar."


def entregar_no_whatsapp(texto):
    """Audio para o Dono (Eu); se a gravacao falhar, manda o arquivo."""
    try:
        from . import voz, wpp_voz, wpp_arquivo
        w = voz.falar_wav(re.sub(r"\(feito no modo profundo.*?\)", "", texto))
        r = wpp_voz.enviar_voz("Eu", w)
        if not str(r).startswith("✅"):
            wpp_arquivo.enviar_arquivo("Eu", w)
    except Exception:
        pass
