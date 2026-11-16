import json
import time
from pathlib import Path

from braniac import barramento as B, sauraki as S


def test_descobre_agentes_do_registro_e_so_afirma_estado_com_dado():
    snap = S.snapshot({})
    nomes = {a["nome"] for a in snap["agentes"]}
    assert {"Jarvis", "Sultão", "Alma", "Cabo Tito", "Forja", "Ada", "Ilhéu"} <= nomes
    ada = next(a for a in snap["agentes"] if a["nome"] == "Ada")
    assert ada["estado"] is None and "não disponível" in ada["motivo"]           # sem fonte de atividade: nao inventa estado
    assert snap["simulado"] is False and snap["tokens"] is None
    assert snap["total"] == len(snap["agentes"])


def test_estado_executando_e_consultando_vem_do_barramento_e_arquivos():
    S.DATA.mkdir(exist_ok=True)
    (S.DATA / "correio.json").write_text("{}")
    s1 = {a["nome"]: a for a in S.snapshot({})["agentes"]}
    assert s1["Correio"]["estado"] == "executando"                                # arquivo de estado mexido agora
    B.enviar("Forja", "Ada", "pedido", "revisar o modulo X")
    s2 = {a["nome"]: a for a in S.snapshot({})["agentes"]}
    assert s2["Forja"]["estado"] == "consultando" and "Ada" in s2["Forja"]["motivo"]


def test_vaquinha_desconectada_ate_ligar_e_erro_quando_deploy_falha():
    assert {a["nome"]: a for a in S.snapshot({})["agentes"]}["Vaquinha"]["estado"] == "desconectado"
    (S.DATA / "vaquinha.json").write_text(json.dumps({"ativo": True, "ultimo_erro": "x"}))
    assert {a["nome"]: a for a in S.snapshot({})["agentes"]}["Vaquinha"]["estado"] == "erro"


def test_aguardando_autorizacao_do_airbnb_e_nao_vaza_fala_do_dono():
    (S.DATA / "airbnb_estado.json").write_text(json.dumps({"consultas": {"1": {"hospede": "David", "estado": "consulta"}}}))
    ilheu = {a["nome"]: a for a in S.snapshot({})["agentes"]}["Ilhéu"]
    assert ilheu["estado"] == "aguardando_autorizacao" and "David" not in json.dumps(ilheu)
    B.enviar("Jarvis", "Alma", "dono_disse", "segredo pessoal do dono")
    assert "segredo" not in json.dumps(S.snapshot({}))


def test_autonomia_e_servicos_refletem_o_status():
    snap = S.snapshot({"autonomia": {"armada": True, "restante_min": 30, "indefinida": False}, "airbnb_auto": {"ligado": False}, "atendimento_auto": {"ligado": True}})
    assert snap["autonomia"]["armada"] is True
    assert {s["nome"]: s["ok"] for s in snap["servicos"]}["Airbnb"] is False


def test_consulta_real_do_jarvis_aos_agentes_vai_para_o_barramento():
    from braniac import assuntos as A
    A._ULT_CONSULTA.clear()
    assert A._registrar_consulta([("Alma", "Família e saúde", 2), ("Cabo Tito", "Exército", 3)], agora=1000.0)
    msgs = [(m["de"], m["para"], m["tipo"]) for m in B.historico(10)]
    assert msgs == [("Jarvis", "Alma", "pedido"), ("Alma", "Cabo Tito", "pedido"), ("Cabo Tito", "Alma", "resposta"), ("Alma", "Jarvis", "resposta")]
    assert not A._registrar_consulta([("Alma", "Família e saúde", 2), ("Cabo Tito", "Exército", 3)], agora=1010.0)     # limite de 30 s
    assert A._registrar_consulta([("Vaquinha", "Vaquinha online", 0)], agora=1100.0)                                  # agente novo tambem fala no barramento



def test_contexto_anexado_nao_dispara_atalhos_nem_ferramentas():
    from braniac import jarvis
    txt = "66999990001\n\n[Conversa recente no WhatsApp: Dono: Jarvis, mostra a agenda de hoje ¦ Jarvis: ok]"
    nomes = {f["function"]["name"] for f in jarvis.ferramentas_para(txt)}
    assert "agenda" not in nomes
    assert "agenda" in {f["function"]["name"] for f in jarvis.ferramentas_para("me lembra amanhã às 9 de ligar pra Parceira")}


def test_fala_do_dono_nao_vira_fato_nem_volta_no_contexto():
    from braniac import alma_cuida as A, banco
    A.observar("vou mandar o link do site da vaquinha pro grupo da família", "web")
    A.ciclo(lambda n, t: None)
    assert "Dono disse em" not in banco.consultar("link do site vaquinha família", "local")[0]


def test_demo_nao_vaza_texto_real():
    snap = S.snapshot({})
    snap["conversa"] = [{"id": 9, "ts": 0, "de": "Cofre", "para": "Compasso", "tipo": "status", "texto": "saldo R$ 1.068,87"}]
    d = S.demo(snap)
    assert d["simulado"] and "1.068" not in str(d)


def test_esteira_do_parceiro_no_predio(monkeypatch):
    """Andar da esteira: uma estacao por etapa com o agente dela, cidades do resumo publico e nada privado."""
    from braniac.link import lote_parceiro
    agora = 1000.0
    lote = {"cidades": {"196": {"numero": "196", "cidade": "Antas", "etapa": "baixando_tcm", "desde": agora - 30},
                        "141": {"numero": "141", "cidade": "Irecê", "etapa": "voz", "desde": agora - 9000, "detalhe": "/Users/parceiro/x"},
                        "152": {"numero": "152", "cidade": "Cidade B", "etapa": "pendencia", "desde": 1.0}},
            "pendencias": [{"numero": "152", "cidade": "Cidade B", "motivo": "x", "contato": "5573999"}],
            "esteira": {"meta": 50, "prontos": [{"numero": "093", "cidade": "Cidade"}], "atual": {"numero": "196", "cidade": "Antas", "etapa": "baixando_tcm"}}}
    monkeypatch.setattr(lote_parceiro, "ler", lambda: lote)
    e = S._esteira(agora)
    por = {s["chave"]: s for s in e["estacoes"]}
    assert [s["agente"] for s in e["estacoes"]] == ["Busca", "Fiscal", "Pena", "Eco", "Prisma", "Lupa", "Entrega"]
    assert por["busca"]["estado"] == "executando" and por["eco"]["estado"] == "aguardando_servico" and por["prisma"]["estado"] == "ocioso"
    assert e["prontos"] == 1 and e["pendencias"] == 1 and e["atual"]["cidade"] == "Antas"
    assert "5573999" not in json.dumps(e) and "/Users" not in json.dumps(e)
    h = (Path(S.__file__).parent / "ui" / "sauraki-real.html").read_text(encoding="utf-8")
    assert '"esteira"' in h and "function construirEsteira" in h
    # telão: um estado por vídeo do lote (só o estado, sem nome) e a função que desenha
    assert e["quadrados"][:2] == ["pronto", "agora"] and all(isinstance(q, str) for q in e["quadrados"])
    assert "function telaoEsteira" in h
