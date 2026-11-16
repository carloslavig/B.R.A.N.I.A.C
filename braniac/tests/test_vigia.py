# -*- coding: utf-8 -*-
from datetime import datetime
import pytest
from braniac import atender, contexto, dono, jarvis, power, vigia

CFG = dict(vigia.CFG_PADRAO, estavel_s=15)   # os testes continuam com a espera de 15 s (o padrao real agora e 8 s)
HOJE_18H = datetime.now().replace(hour=18, minute=0, second=0, microsecond=0).timestamp()


def L(nome, hora="17:47", texto="oi", nossa=False, nl=0):
    """Linha da lista do WhatsApp. nl = contador de nao lidas (NAO influencia: o que conta e a ultima mensagem ser dela)."""
    return {"nome": nome, "nl": nl, "nossa": nossa, "resumo": f"{nome} | {hora} | {texto}"}


class Sim:
    """Roda ciclos do vigia com o 'WhatsApp' simulado; 'resolve' diz quem o atendimento conseguiu tratar."""
    def __init__(self, resolve=True):
        self.t = HOJE_18H
        self.chamadas = []
        self.resolve = resolve
        atender.ULTIMO.update(enviados=[], linhas=[], tratados=[])

    def rodar(self, nomes):
        self.chamadas.append(list(nomes))
        ok = list(nomes) if self.resolve else []
        atender.ULTIMO.update(enviados=ok, tratados=ok)

    def ciclo(self, linhas, avanca=0, cfg=None):
        self.t += avanca
        return vigia.ciclo(cfg or CFG, linhas=linhas, rodar=self.rodar, agora=self.t)


@pytest.fixture
def sim():
    return Sim()


def espera_e_atende(sim, linhas, cfg=None):
    sim.ciclo(linhas, cfg=cfg)                  # ve a conversa
    return sim.ciclo(linhas, avanca=20, cfg=cfg)  # estavel ha mais de 15 s


# ---------- o defeito reportado: lida e sem resposta TEM que ser respondida ----------

def test_mensagem_lida_e_sem_resposta_e_respondida(sim):
    linhas = [L("Irmao", "17:47", "me explica o que e uma superficie cinza", nl=0)]    # nl=0: ja foi lida
    r = espera_e_atende(sim, linhas)
    assert r["candidatos"] == ["Irmao"] and sim.chamadas == [["Irmao"]]


def test_nao_precisa_de_foto_inicial_o_primeiro_ciclo_ja_enxerga_o_que_esta_esperando(sim):
    sim.ciclo([L("Ana", "17:50", "tem vaga?"), L("Bia", "17:55", "oi")])
    r = sim.ciclo([L("Ana", "17:50", "tem vaga?"), L("Bia", "17:55", "oi")], avanca=20)
    assert sorted(r["candidatos"]) == ["Ana", "Bia"]


def test_conversa_cuja_ultima_mensagem_e_nossa_nao_entra(sim):
    linhas = [L("Ana", "17:50", "Tem sim!", nossa=True)]
    espera_e_atende(sim, linhas)
    assert sim.chamadas == []


# ---------- idade ----------

def test_conversas_antigas_nao_sao_respondidas_de_repente(sim):
    linhas = [L("Gran", "Ontem", "oi"), L("Zeca", "terça-feira", "oi"), L("Rui", "03:00", "oi"), L("Eva", "17:00", "oi")]
    r = espera_e_atende(sim, linhas)
    assert r["candidatos"] == ["Eva"]                                      # so a de hoje, dentro de 12 h


def test_idade_pela_lista():
    agora = datetime(2026, 10, 1, 18, 0)
    assert atender.idade_linha("Irmao | 17:47 | oi", agora) == pytest.approx(13 / 60, abs=0.01)
    assert atender.idade_linha("Irmao | Ontem | oi", agora) is None and atender.idade_linha("Irmao | terça-feira | oi", agora) is None
    assert atender.idade_linha("+55 86 9000-0003 | +55 86 9000-0003 | 16:04 | oi", agora) == pytest.approx(1.93, abs=0.05)
    assert atender.idade_linha("X | 23:30 | oi", agora) == pytest.approx(18.5, abs=0.05)    # horario 'no futuro' = ontem


def test_esperando_resposta_pega_so_o_que_esta_esperando():
    agora = datetime(2026, 10, 1, 18, 0)
    linhas = [L("Irmao", "18:05"), L("Mainha", "18:09", nossa=True), L("Eu", "18:00"), L("Asaas", "08:06"), L("Ana", "Ontem")]
    assert atender.esperando_resposta(linhas, agora.replace(hour=18, minute=10), 12) == ["Irmao"]


# ---------- quem nunca recebe ----------

def test_chat_do_dono_contas_automaticas_e_empresas_sao_ignorados(sim):
    nomes = ["Eu", "Asaas", "Urbano Norte", "Suporte Cadastro Urbano Norte", "EMPREGA ARAGUAIA 2", "QuiteJá"]
    espera_e_atende(sim, [L(n, "17:50", "mensagem nova") for n in nomes])
    assert sim.chamadas == []


# ---------- cada situacao e tratada uma vez; falhas tentam de novo, com limite ----------

def test_depois_de_tratada_nao_repete(sim):
    linhas = [L("Ana", "17:50", "tem vaga?")]
    espera_e_atende(sim, linhas)
    for _ in range(3):
        sim.ciclo(linhas, avanca=30)
    assert sim.chamadas == [["Ana"]]


def test_mensagem_nova_depois_da_resposta_e_tratada_de_novo(sim):
    espera_e_atende(sim, [L("Ana", "17:50", "tem vaga?")])
    sim.ciclo([L("Ana", "17:51", "Tem sim", nossa=True)], avanca=20)               # a lista mostra a nossa resposta
    r = espera_e_atende(sim, [L("Ana", "17:58", "e dia 5?")])
    assert r["candidatos"] == ["Ana"] and len(sim.chamadas) == 2


def test_se_o_atendimento_nao_conseguiu_tenta_de_novo_ate_2_vezes_e_desiste():
    sim = Sim(resolve=False)
    linhas = [L("Ana", "17:50", "tem vaga?")]
    sim.ciclo(linhas)
    for _ in range(5):
        sim.ciclo(linhas, avanca=20)
    assert len(sim.chamadas) == 2                                                  # 2 tentativas e para (sem laco)


def test_a_pessoa_continua_digitando_a_espera_recomeca(sim):
    sim.ciclo([L("Ana", "17:50", "oi")])
    sim.ciclo([L("Ana", "17:51", "tem vaga?")], avanca=10)                          # chegou outra: recomeca
    assert sim.ciclo([L("Ana", "17:51", "tem vaga?")], avanca=10)["candidatos"] == []
    assert sim.ciclo([L("Ana", "17:51", "tem vaga?")], avanca=10)["candidatos"] == ["Ana"]


# ---------- limites ----------

def test_limite_por_pessoa_por_hora_nao_marca_como_tratada(sim):
    cfg = dict(CFG, max_por_chat_hora=1)
    espera_e_atende(sim, [L("Ana", "17:50", "oi")], cfg=cfg)                        # 1a: atende
    sim.ciclo([L("Ana", "17:51", "ok", nossa=True)], avanca=5, cfg=cfg)
    r = espera_e_atende(sim, [L("Ana", "17:56", "e sobre o preco?")], cfg=cfg)      # 2a na mesma hora: limite
    assert r["candidatos"] == [] and len(sim.chamadas) == 1


def test_limite_total_por_hora_e_por_dia():
    est = {"envios": [[f"p{i}", 1_000_000.0 - i] for i in range(15)]}
    assert not vigia.limite_ok(est, "novo", 1_000_000.0, CFG)
    assert vigia.limite_ok({"envios": []}, "novo", 1_000_000.0, CFG)


def test_janela_de_horario():
    assert vigia.dentro_da_janela(["07:00", "22:00"], datetime(2026, 10, 1, 9, 30))
    assert not vigia.dentro_da_janela(["07:00", "22:00"], datetime(2026, 10, 1, 23, 10))
    assert not vigia.dentro_da_janela(["07:00", "22:00"], datetime(2026, 10, 1, 6, 59))


# ---------- liga/desliga ----------

def test_padrao_desligado_e_religar_nao_reenvia_o_que_ja_foi_tratado(sim):
    assert power.atendimento_auto() is False
    vigia.ligar()
    espera_e_atende(sim, [L("Ana", "17:50", "oi")])
    vigia.desligar()
    vigia.ligar()                                                                    # religar nao apaga o que foi tratado
    sim.ciclo([L("Ana", "17:50", "oi")], avanca=100)
    sim.ciclo([L("Ana", "17:50", "oi")], avanca=100)
    assert power.atendimento_auto() is True and sim.chamadas == [["Ana"]]


def test_comando_auto_desliga_de_qualquer_canal_mas_so_liga_no_pc(monkeypatch):
    class R:
        cfg = {"cadeia": []}
    monkeypatch.setattr(jarvis.power, "pausado", lambda: False)
    vigia.ligar()
    assert "DESLIGADO" in jarvis.processar(R(), "/auto off", "c", origem="telegram")[0] and power.atendimento_auto() is False
    assert jarvis.processar(R(), "/auto on", "c", origem="telegram")[0].startswith("🔒") and power.atendimento_auto() is False
    assert jarvis.processar(R(), "/auto on", "c", origem="whatsapp")[0].startswith("🔒")
    assert "LIGADO" in jarvis.processar(R(), "/auto on", "c", origem="web")[0] and power.atendimento_auto() is True
    assert "LIGADO" in jarvis.processar(R(), "/auto", "c", origem="telegram")[0]


# ---------- atendimento: grupos, idade das mensagens, resultado ----------

def test_grupo_e_idade_das_mensagens():
    assert atender.eh_grupo("Ana, Bia, Você") and atender.eh_grupo("Vagas dados do grupo")
    assert not atender.eh_grupo("Maria visto por último hoje às 10:00") and not atender.eh_grupo("online")
    agora = datetime(2026, 10, 1, 19, 0)
    assert atender.idade_horas("[17:00, 01/10/2026] Maria: ", agora) == pytest.approx(2.0)
    assert atender.idade_horas("[10:00, 28/09/2026] Maria: ", agora) > 70
    assert atender.idade_horas("sem data") is None


def test_modo_automatico_pula_grupos_sem_perguntar_a_ninguem(monkeypatch):
    item = {"nome": "Turma", "nl": 1, "msgs": ["oi pessoal"], "ctx": [], "autores": {"A", "B"}, "midia": False, "grupo": True}
    perguntou = []
    monkeypatch.setattr(atender, "coletar", lambda *a, **k: [item])
    monkeypatch.setattr(atender, "decidir", lambda *a, **k: perguntou.append(1) or ("E", "oi"))
    rel = atender.atender(relatar=False, pular_grupos=True, somente=["Turma"])
    assert perguntou == [] and atender.ULTIMO["enviados"] == [] and "ignoradas" in rel
    assert atender.ULTIMO["tratados"] == ["Turma"]                                  # tratada: o vigia nao volta a ela


def test_resposta_longa_demais_e_refeita_mais_curta_em_vez_de_descartada(monkeypatch):
    from braniac import whatsapp
    item = {"nome": "Irmao", "nl": 1, "msgs": ["oi"], "ctx": [], "autores": {"Irmao"}, "midia": False}
    flags_vistas = []

    def decidir(it, fl, esp=0):
        flags_vistas.append(fl)
        return ("E", "x" * 700) if "L" not in fl else ("E", "Fala, Irmao! Aqui é o Jarvis. Em que posso ajudar?")
    monkeypatch.setattr(atender, "coletar", lambda *a, **k: [item])
    monkeypatch.setattr(atender, "decidir", decidir)
    monkeypatch.setattr(whatsapp, "enviar", lambda n, x: "✅ ok")
    atender.atender(relatar=False, espaco_s=(0, 0))
    assert atender.ULTIMO["enviados"] == ["Irmao"] and any("L" in f for f in flags_vistas)


def test_resultado_estruturado_do_atendimento(monkeypatch):
    from braniac import whatsapp
    item = {"nome": "Maria", "nl": 1, "msgs": ["tem vaga?"], "ctx": [], "autores": {"Maria"}, "midia": False}
    monkeypatch.setattr(atender, "coletar", lambda *a, **k: [item])
    monkeypatch.setattr(atender, "decidir", lambda it, fl, esp=0: ("E", "Tem sim, qual a data?"))
    monkeypatch.setattr(whatsapp, "enviar", lambda n, x: "✅ ok")
    atender.atender(relatar=False, espaco_s=(0, 0))
    assert atender.ULTIMO["enviados"] == ["Maria"] and atender.ULTIMO["tratados"] == ["Maria"]
    assert atender.ULTIMO["linhas"][0].startswith("✓ Maria")


# ---------- vigia do chat do Dono: reenvio apos falha / reinicio ----------

def _msgs(txt="me responde essa"):
    return [{"d": "ELE", "t": txt, "c": "[18:00, 01/10/2026] Eu: "}]


def _ler(msgs, sig="s1"):
    return lambda nome, anterior: None if sig == anterior else {"msgs": msgs, "midias": [], "lista_sig": sig}


def test_dono_se_o_envio_falha_tenta_de_novo_no_proximo_ciclo():
    enviados = []
    falhas = {"n": 1}

    def enviar(n, x):
        if falhas["n"] > 0:
            falhas["n"] -= 1
            return "falhou"
        enviados.append(x)
        return "✅"
    kw = dict(ler=_ler(_msgs()), responder=lambda p: "Respondido.", falar=lambda n, t: False, enviar=enviar)
    assert dono.tratar_dono(None, **kw) is None and enviados == []                   # 1a tentativa falhou
    assert dono.tratar_dono(None, **kw) == "Respondido." and enviados == ["Respondido."]   # 2a: reenvia
    assert dono.tratar_dono(None, **kw) is None and len(enviados) == 1                # e nao repete


def test_dono_servidor_reiniciado_no_meio_nao_perde_a_resposta():
    class Cai(Exception):
        pass

    def responder_e_cai(p):
        raise Cai()
    # simula queda DEPOIS de marcar a tentativa: a mensagem nao pode ficar 'tratada' sem ter sido respondida
    try:
        dono.tratar_dono(None, ler=_ler(_msgs()), responder=lambda p: (_ for _ in ()).throw(KeyboardInterrupt()),
                         falar=lambda n, t: True, enviar=lambda n, x: "✅")
    except KeyboardInterrupt:
        pass
    est = dono._estado()
    assert est.get("tratado") is None and est.get("lista_sig") is None               # nada foi dado como tratado
    enviados = []
    dono.tratar_dono(None, ler=_ler(_msgs()), responder=lambda p: "Agora sim.", falar=lambda n, t: False,
                     enviar=lambda n, x: enviados.append(x) or "✅")
    assert enviados == ["Agora sim."]


def test_dono_desiste_apos_3_tentativas_sem_laco():
    n = {"v": 0}

    def sempre_falha(nome, x):
        n["v"] += 1
        return "falhou"
    for _ in range(8):
        dono.tratar_dono(None, ler=_ler(_msgs()), responder=lambda p: "x", falar=lambda nm, t: False, enviar=sempre_falha)
    assert n["v"] == 4   # 3 tentativas + 1 "to vendo" ao desistir (16/11); depois para, sem laco


# ---------- uma pagina do WhatsApp, uma trava ----------

def test_todos_os_bracos_do_whatsapp_usam_a_mesma_trava():
    import threading
    from braniac import whatsapp, wpp_voz
    for nome in ("listar_nomes", "nao_lidas", "ler_conversa", "enviar"):
        assert hasattr(getattr(whatsapp, nome), "__wrapped__"), nome            # protegida pela trava
    assert wpp_voz._LOCK is whatsapp.LOCK                                       # voz e texto nunca ao mesmo tempo
    ordem = []
    ocupado = threading.Event()

    def uso(nome):
        with whatsapp.LOCK:
            ordem.append(f"{nome}-entra")
            ocupado.wait(0.2)
            ordem.append(f"{nome}-sai")
    a, b = threading.Thread(target=uso, args=("A",)), threading.Thread(target=uso, args=("B",))
    a.start(); b.start(); a.join(); b.join()
    assert ordem[0].endswith("entra") and ordem[1] == ordem[0].replace("entra", "sai")   # um sai antes do outro entrar


# ---------- audio RECEBIDO nao e mensagem nossa (o icone de microfone nao e um tique) ----------

def test_a_lista_so_considera_nossa_a_linha_com_tique_de_entrega():
    import re
    js = dono.JS_LINHAS
    m = re.search(r"test\(x\)", js) and re.search(r"/(\^wds-ic-[^/]+)/i", js)
    assert m, "o JS deve decidir 'nossa' por um padrao de tique"
    padrao = re.compile(m.group(1).replace("\\", "\\"), re.I)
    for ours in ("wds-ic-read", "wds-ic-delivered", "wds-ic-sent", "wds-ic-pending", "wds-ic-phone-call-made-filled"):
        assert padrao.search(ours), ours                      # tique de entrega / ligacao feita = nossa
    for deles in ("ic-keyboard-voice-filled", "ic-push-pin", "ic-person-filled", "ic-expand-more"):
        assert not padrao.search(deles), deles                # microfone (audio recebido) e outros icones NAO sao tique
    assert "svg title" in js and "last-msg-status" not in js.split("nossa=")[1]   # nao depende mais so do wrapper de status


def test_audio_da_parceira_sem_resposta_entra_na_fila(sim):
    linhas = [{"nome": "Parceira 🤍", "nl": 1, "nossa": False, "resumo": "Parceira | 17:55 | 0:03"}]   # so microfone => dela
    r = espera_e_atende(sim, linhas)
    assert r["candidatos"] == ["Parceira 🤍"]


def test_linha_nossa_nunca_vira_tratada_e_uma_mudanca_de_leitura_nao_perde_a_conversa(sim):
    """Se o vigia ja achou que a ultima mensagem era nossa (leitura errada do icone), isso nao pode 'queimar' a conversa."""
    sim.ciclo([L("Ana", "17:55", "0:03", nossa=True)])
    est = vigia._estado()
    assert "Ana" not in est.get("tratados", {})
    r = espera_e_atende(sim, [L("Ana", "17:55", "0:03", nossa=False)])             # agora classificada certo: e DELA
    assert r["candidatos"] == ["Ana"]


# ---------- janela minimizada do Chrome do agente ----------

def test_conexao_ao_whatsapp_restaura_a_janela_minimizada_e_deixa_fora_da_tela(monkeypatch):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(dono.__file__).parent.parent / "local-ia"))
    import cdpwa
    chamadas = []

    class Fake:
        def cmd(self, metodo, params=None):
            chamadas.append((metodo, params))
            if metodo == "Browser.getWindowForTarget":
                return {"windowId": 7, "bounds": {"windowState": "minimized"}}
            return {}
    cdpwa.WA._garantir_janela(Fake())
    metodos = [m for m, _ in chamadas]
    assert metodos == ["Browser.getWindowForTarget", "Browser.setWindowBounds", "Browser.setWindowBounds"]
    assert chamadas[1][1]["bounds"] == {"windowState": "normal"}
    assert chamadas[2][1]["bounds"]["left"] < 0                       # fora da area visivel
    chamadas.clear()

    class Normal(Fake):
        def cmd(self, metodo, params=None):
            chamadas.append((metodo, params))
            return {"windowId": 7, "bounds": {"windowState": "normal"}}
    cdpwa.WA._garantir_janela(Normal())
    assert [m for m, _ in chamadas] == ["Browser.getWindowForTarget"]  # janela normal: nao mexe em nada

    class Quebra(Fake):
        def cmd(self, metodo, params=None):
            raise RuntimeError("sem janela")
    cdpwa.WA._garantir_janela(Quebra())                                # erro nunca derruba o uso do WhatsApp


def test_outbox_entrega_recados_ao_dono_e_limpa(tmp_path, monkeypatch):
    out = tmp_path / "outbox_dono.txt"
    out.write_text("Vaga A enviada\n---\nVaga B para decidir\n", encoding="utf-8")
    monkeypatch.setattr(vigia, "OUTBOX", out)
    enviados = []
    assert vigia.enviar_outbox(lambda dest, msg: enviados.append((dest, msg)) or "✅ ok") == 2
    assert len(enviados) == 2 and "Vaga A" in enviados[0][1] and "Vaga B" in enviados[1][1]
    assert not out.exists()


def test_outbox_mantem_o_que_nao_conseguiu_enviar(tmp_path, monkeypatch):
    out = tmp_path / "outbox_dono.txt"
    out.write_text("um\n---\ndois", encoding="utf-8")
    monkeypatch.setattr(vigia, "OUTBOX", out)
    respostas = iter(["✅ ok", "falhou"])
    assert vigia.enviar_outbox(lambda d, m: next(respostas)) == 1
    assert out.read_text(encoding="utf-8").strip() == "dois"
    assert vigia.enviar_outbox(lambda d, m: "✅ ok") == 1 and not out.exists()


def test_outbox_arquivo_sai_como_documento_com_legenda(tmp_path, monkeypatch):
    out = tmp_path / "outbox_dono.txt"
    out.write_text("[arquivo] C:/x/video.mp4\nteste do motor\n---\noi", encoding="utf-8")
    monkeypatch.setattr(vigia, "OUTBOX", out)
    arqs, textos = [], []
    n = vigia.enviar_outbox(lambda d, m: textos.append(m) or "✅ ok", enviar_arquivo=lambda d, c, leg: arqs.append((c, leg)) or "✅ ok")
    assert n == 2 and arqs == [("C:/x/video.mp4", "teste do motor")] and len(textos) == 1
    assert not out.exists()


def test_outbox_inexistente_ou_vazio_nao_faz_nada(tmp_path, monkeypatch):
    monkeypatch.setattr(vigia, "OUTBOX", tmp_path / "nao_existe.txt")
    assert vigia.enviar_outbox(lambda d, m: pytest.fail("nada a enviar")) == 0


def test_anti_laco_no_maximo_4_tentativas_por_hora_na_mesma_conversa(monkeypatch):
    import time as _t
    cfg = dict(vigia.CFG_PADRAO, estavel_s=0, janela=["00:00", "23:59"])
    agora = _t.time()
    linha = {"nome": "Empresa Chata", "resumo": "Empresa Chata | " + _t.strftime("%H:%M") + " | oferta", "nossa": False}
    chamadas = []
    for i in range(7):                       # a conversa nunca e 'resolvida' (envio falha): antes repetia para sempre
        r = vigia.ciclo(cfg, linhas=[linha], rodar=lambda nomes: chamadas.append(nomes), agora=agora + i * 70)
        vigia.ciclo(cfg, linhas=[linha], rodar=lambda nomes: chamadas.append(nomes), agora=agora + i * 70 + 30)
    assert len(chamadas) <= 4


def test_bots_de_empresa_conhecidos_nunca_sao_respondidos():
    from braniac import contexto
    assert contexto.nao_responder("InfinitePay") and contexto.nao_responder("Vivo") and not contexto.nao_responder("Amigo")


def _linha_layla(nome="Loja Esphiraria"):
    import time as _t
    return {"nome": nome, "resumo": f"{nome} | " + _t.strftime("%H:%M") + " | Layla: preciso de ajuda com a impressora", "nossa": False}


def test_layla_e_sempre_atendida_mesmo_com_limites_estourados():
    import time as _t
    cfg = dict(vigia.CFG_PADRAO, estavel_s=0, max_por_chat_hora=0, max_por_hora=0, max_por_dia=0)   # limites zerados: ninguem passaria
    agora = _t.time()
    chamadas = []
    linha = _linha_layla()
    vigia.ciclo(cfg, linhas=[linha], rodar=lambda n: chamadas.append(n), agora=agora)           # 1a vista: espera estabilizar
    vigia.ciclo(cfg, linhas=[linha], rodar=lambda n: chamadas.append(n), agora=agora + 1)
    assert chamadas and chamadas[0] == ["Loja Esphiraria"]


def test_layla_nao_tem_anti_laco_nem_desiste():
    import time as _t
    cfg = dict(vigia.CFG_PADRAO, estavel_s=0)
    agora = _t.time()
    chamadas = []
    linha = _linha_layla()
    for i in range(10):                       # o atendimento nunca 'resolve' (como se falhasse): para as outras seria barrado em 4/2 tentativas
        vigia.ciclo(cfg, linhas=[linha], rodar=lambda n: chamadas.append(n), agora=agora + i * 70)
        vigia.ciclo(cfg, linhas=[linha], rodar=lambda n: chamadas.append(n), agora=agora + i * 70 + 30)
    assert len(chamadas) >= 8


def test_fora_do_horario_so_a_layla_e_atendida():
    import time as _t
    cfg = dict(vigia.CFG_PADRAO, estavel_s=0)
    agora = _t.time()
    outra = {"nome": "Fulano", "resumo": "Fulano | " + _t.strftime("%H:%M") + " | oi", "nossa": False}
    chamadas = []
    for i in range(2):
        vigia.ciclo(cfg, linhas=[outra, _linha_layla()], rodar=lambda n: chamadas.append(n), agora=agora + i * 30, so_prioritarios=True)
    assert chamadas and all(c == ["Loja Esphiraria"] for c in chamadas)


def test_layla_nunca_entra_em_nao_responder_e_so_recebe_texto():
    from braniac import contexto
    assert contexto.prioritario("Loja Esphiraria") and contexto.prioritario("Layla") and not contexto.prioritario("Amigo")
    assert not contexto.nao_responder("Loja Esphiraria")
    assert contexto.preferencia("Loja Esphiraria") == "texto" and contexto.deve_falar("Loja Esphiraria", "oi") is False


# ---------- saudacao automatica do WhatsApp Business nao esconde contato novo (Dono, 06/10) ----------

def test_saudacao_automatica_nao_conta_como_resposta_nossa():
    from braniac import atender, contexto
    assert contexto.saudacao_automatica("C. Exemplo agradece seu contato. Como posso ajudar?")
    assert not contexto.saudacao_automatica("Oi, Ana! Eu sou o Jarvis, assistente do Dono. Como posso te ajudar?")
    msgs = [{"d": "ELE", "t": "Oi, queria um orcamento"}, {"d": "EU", "t": "C. Exemplo agradece seu contato. Como posso ajudar?"}]
    assert [m["t"] for m in atender._finais_deles(msgs)] == ["Oi, queria um orcamento"]       # a mensagem da pessoa continua 'sem resposta'
    # resposta de verdade nossa depois da pessoa: ai sim esta respondida
    assert atender._finais_deles(msgs + [{"d": "EU", "t": "Oi! Aqui e o Jarvis, assistente do Dono."}]) == []
    # e uma mensagem nossa de verdade antes da saudacao automatica continua cortando a lista
    assert atender._finais_deles([{"d": "ELE", "t": "a"}, {"d": "EU", "t": "resposta real"}, {"d": "ELE", "t": "b"}]) == [{"d": "ELE", "t": "b"}]


def test_conversa_cuja_ultima_e_a_saudacao_automatica_e_atendida(monkeypatch):
    import time as _t
    from braniac import vigia
    hora = _t.strftime("%H:%M")
    linha = {"nome": "+55 66 8126-5428", "resumo": f"+55 66 8126-5428 | {hora} | C. Exemplo agradece seu contato. Como posso ajudar?", "nossa": True}
    chamadas = []
    cfg = {**vigia.CFG_PADRAO, "estavel_s": 0}
    agora = _t.time()
    vigia.ciclo(cfg, linhas=[linha], rodar=lambda n: chamadas.append(n), agora=agora)           # 1a vez so marca (espera estabilizar)
    vigia.ciclo(cfg, linhas=[linha], rodar=lambda n: chamadas.append(n), agora=agora + 30)
    assert chamadas == [["+55 66 8126-5428"]]
    normal = {**linha, "resumo": f"+55 66 9999-0000 | {hora} | Oi! Aqui e o Jarvis, como posso ajudar?", "nome": "+55 66 9999-0000"}
    chamadas.clear()
    vigia.ciclo(cfg, linhas=[normal], rodar=lambda n: chamadas.append(n), agora=agora + 60)
    vigia.ciclo(cfg, linhas=[normal], rodar=lambda n: chamadas.append(n), agora=agora + 90)
    assert chamadas == []                                                                       # resposta nossa de verdade: nada a fazer


def test_esperando_resposta_inclui_a_saudacao_automatica():
    import time as _t
    from braniac import atender
    hora = _t.strftime("%H:%M")
    linhas = [{"nome": "Novo Contato", "resumo": f"Novo Contato | {hora} | C. Exemplo agradece seu contato.", "nossa": True},
              {"nome": "Outro", "resumo": f"Outro | {hora} | Combinado!", "nossa": True}]
    assert atender.esperando_resposta(linhas) == ["Novo Contato"]


def test_anti_laco_deixa_rastro_no_log(monkeypatch, tmp_path):
    import time as _t
    from braniac import vigia
    monkeypatch.setattr(vigia, "LOG", tmp_path / "vigia.log")
    hora = _t.strftime("%H:%M")
    linha = {"nome": "Chato", "resumo": f"Chato | {hora} | oi de novo", "nossa": False}
    agora = _t.time()
    est = vigia._estado()
    est["atendidos"] = [["Chato", agora - 60 * i] for i in range(8)]
    vigia._salvar(est)
    cfg = {**vigia.CFG_PADRAO, "estavel_s": 0}
    vigia.ciclo(cfg, linhas=[linha], rodar=lambda n: None, agora=agora)
    vigia.ciclo(cfg, linhas=[linha], rodar=lambda n: None, agora=agora + 30)
    assert "anti-laco" in (tmp_path / "vigia.log").read_text(encoding="utf-8")


def test_espera_acima_de_5_min_fura_o_limite_uma_vez(sim):
    cfg = dict(CFG, max_por_chat_hora=0)                                           # limite zerado: normalmente ninguem passa
    espera_e_atende(sim, [L("Ana", "17:50", "oi")], cfg=cfg)
    r = sim.ciclo([L("Ana", "17:50", "oi")], avanca=310, cfg=cfg)                  # 5 min depois e nada foi respondido
    assert r["candidatos"] == ["Ana"]
    r2 = sim.ciclo([L("Ana", "17:50", "oi")], avanca=10, cfg=cfg)                  # so uma vez por mensagem: sem laco
    assert r2["candidatos"] == []


def test_gravando_audio_ou_digitando_nao_e_mensagem_nova(sim):
    for estado in ("gravando áudio...", "digitando..."):
        r = espera_e_atende(sim, [L("mainha", texto=estado)])
        assert r["candidatos"] == []


def test_comando_do_dono_se_apresentar_manda_audio_so_uma_vez(tmp_path, monkeypatch):
    from braniac import monitor_dono, vigia
    monkeypatch.setattr(vigia, "ARQ", tmp_path / "v.json")
    monkeypatch.setattr(vigia, "LOG", tmp_path / "v.log")
    assert monitor_dono.pedido_de_apresentacao("Fulano | 10:00 | Jarvis, se apresente") and monitor_dono.pedido_de_apresentacao("x | jarvis apresente-se")
    assert not monitor_dono.pedido_de_apresentacao("Fulano | 10:00 | o Jarvis já se apresentou ontem") and not monitor_dono.pedido_de_apresentacao("Eu | oi")
    dados = []
    linhas = [{"nome": "Beltrano", "nl": 0, "nossa": True, "resumo": "Beltrano | 10:00 | Jarvis, se apresente"}]
    cfg = dict(vigia.CFG_PADRAO)
    r1 = vigia.ciclo(cfg, linhas=linhas, rodar=lambda c: None, agora=1_800_000_000.0, apresentar_fn=lambda n: dados.append(n) or "✅")
    r2 = vigia.ciclo(cfg, linhas=linhas, rodar=lambda c: None, agora=1_800_000_100.0, apresentar_fn=lambda n: dados.append(n) or "✅")
    assert dados == ["Beltrano"] and r1["comando_dono"] == ["Beltrano"] and r2["comando_dono"] == []


def test_comando_por_voz_do_dono_ouve_audio_curto_e_ignora_audio_do_jarvis(tmp_path, monkeypatch):
    from braniac import monitor_dono, vigia
    monkeypatch.setattr(vigia, "ARQ", tmp_path / "v.json")
    monkeypatch.setattr(vigia, "LOG", tmp_path / "v.log")
    monkeypatch.setattr(monitor_dono, "ARQ_ENVIOS", tmp_path / "envios.json")
    agora = 1_800_000_000.0
    cfg = dict(vigia.CFG_PADRAO)
    from datetime import datetime
    hora = datetime.fromtimestamp(agora).strftime("%H:%M")
    audio = lambda nome: {"nome": nome, "nl": 0, "nossa": True, "resumo": f"{nome} | {hora} | 0:05"}
    ouvidos, ditos = [], []
    r = vigia.ciclo(cfg, linhas=[audio("Beltrano")], rodar=lambda c: None, agora=agora,
                    apresentar_fn=lambda n: ditos.append(n) or "✅", ouvir_fn=lambda n: ouvidos.append(n) or "Jarvis, se apresente.")
    assert ouvidos == ["Beltrano"] and ditos == ["Beltrano"] and r["comando_dono"] == ["Beltrano"]
    monitor_dono.registrar_envio("Ciclano", agora)             # audio que o proprio Jarvis mandou: nao ouve
    vigia.ciclo(cfg, linhas=[audio("Ciclano")], rodar=lambda c: None, agora=agora + 5,
                apresentar_fn=lambda n: ditos.append(n) or "✅", ouvir_fn=lambda n: ouvidos.append(n) or "")
    assert ouvidos == ["Beltrano"]
    assert not monitor_dono.audio_curto_do_dono({"nome": "X", "nossa": True, "resumo": "X | 10:00 | 2:30"}, agora)   # longo: nao e comando


def test_comandos_do_dono_silenciar_liberar_e_repassar(tmp_path, monkeypatch):
    from braniac import contexto, monitor_dono as m, vigia
    monkeypatch.setattr(contexto, "SILENCIADOS", tmp_path / "sil.json")
    monkeypatch.setattr(vigia, "ARQ", tmp_path / "v.json")
    monkeypatch.setattr(vigia, "LOG", tmp_path / "v.log")
    for t in ("Jarvis, pare de falar nessa conversa agora", "jarvis não quero que você responda nessa conversa", "Jarvis, fique quieto"):
        assert m.interpretar(t)[0] == "silenciar", t
    assert m.interpretar("Jarvis, pode voltar a responder")[0] == "liberar"
    assert m.interpretar("Jarvis, se apresente")[0] == "apresentar"
    assert m.interpretar("Jarvis, fale isso daqui: a reunião é amanhã às 9") == ("falar", "a reunião é amanhã às 9")
    assert m.interpretar("Jarvis, passe essa informação para a pessoa: chego às 8h") == ("falar", "chego às 8h")
    assert m.interpretar("Jarvis, fale isso")[0] is None and m.interpretar("oi tudo bem, o Jarvis é legal")[0] is None
    agora, falas = 1_800_000_000.0, []
    from datetime import datetime
    hora = datetime.fromtimestamp(agora).strftime("%H:%M")
    cfg = dict(vigia.CFG_PADRAO)
    def ciclo(txt, t):
        l = [{"nome": "Beltrano", "nl": 0, "nossa": True, "resumo": f"Beltrano | {hora} | {txt}"}]
        return vigia.ciclo(cfg, linhas=l, rodar=lambda c: None, agora=agora + t, falar_fn=lambda n, x: falas.append((n, x)) or "✅")
    ciclo("Jarvis, pare de falar nessa conversa", 0)
    assert contexto.silenciado("Beltrano") and contexto.nao_responder("Beltrano")
    ciclo("Jarvis, fale isso daqui: chego às 8h", 60)                     # silenciado, mas o comando de repassar vale
    assert falas == [("Beltrano", "chego às 8h")] and contexto.silenciado("Beltrano")
    ciclo("Jarvis, pode voltar a responder", 120)
    assert not contexto.silenciado("Beltrano")


def test_outbox_bloco_audio_sai_em_audio_e_o_resto_em_texto(tmp_path, monkeypatch):
    out = tmp_path / "outbox.txt"
    monkeypatch.setattr(vigia, "OUTBOX", out)
    out.write_text("texto normal\n---\n[audio] Oi Dono, resumo falado.", encoding="utf-8")
    textos, audios = [], []
    n = vigia.enviar_outbox(lambda d, m: textos.append(m) or "✅ ok", lambda d, f: audios.append(f) or "✅ ok")
    assert n == 2 and len(textos) == 1 and textos[0].startswith("Claudinho (via Braniac): texto normal") and audios == ["Oi Dono, resumo falado."]
    assert not out.exists()


def test_outbox_bloco_voz_manda_o_wav_indicado_como_voz(tmp_path, monkeypatch):
    out, wav = tmp_path / "outbox.txt", tmp_path / "v.wav"
    wav.write_bytes(b"RIFFx")
    monkeypatch.setattr(vigia, "OUTBOX", out)
    out.write_text(f"[voz] {wav}\nlegenda\n---\n[voz] {tmp_path / 'nao_existe.wav'}", encoding="utf-8")
    vozes = []
    n = vigia.enviar_outbox(enviar_voz=lambda d, b: vozes.append(b) or "✅ ok")
    assert n == 2 and vozes == [b"RIFFx"] and not out.exists()


def test_outbox_bloco_alma_manda_texto_e_audio_na_voz_dela(tmp_path, monkeypatch):
    from braniac import alma_cuida
    out = tmp_path / "outbox.txt"
    monkeypatch.setattr(vigia, "OUTBOX", out)
    audios = []
    monkeypatch.setattr(alma_cuida, "_audio_da_alma", lambda t, *a, **k: audios.append(t))
    out.write_text("[alma] Oi, querido, tô pensando em você.", encoding="utf-8")
    textos = []
    n = vigia.enviar_outbox(lambda d, m: textos.append(m) or "✅ ok")
    assert n == 1 and textos == ["Oi, querido, tô pensando em você."] and audios == textos   # texto sem o prefixo do Claudinho, e o audio sai junto
