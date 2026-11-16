# -*- coding: utf-8 -*-
from datetime import datetime
import pytest
from braniac import rotina as R


@pytest.fixture(autouse=True)
def dados(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "ESTADO", tmp_path / "rotina.json")
    monkeypatch.setattr(R, "RELATORIO", tmp_path / "rel.md")
    monkeypatch.setattr(R, "DATA", tmp_path)
    from braniac import guarda
    monkeypatch.setattr(guarda, "verificar", lambda *a, **k: [])        # nunca coleta de verdade nos testes
    monkeypatch.setattr(guarda, "resumo", lambda: "🛡 Segurança: teste")


def test_promissor_precisa_ser_trabalho_e_ter_prazo_e_nao_ser_promocao():
    assert R.promissor("Vaga de desenvolvedor remoto - inscrições até 15/10")[0]
    assert R.promissor("Proposta de freelance, deadline sexta")[0]
    assert not R.promissor("Vaga de desenvolvedor remoto")[0]                    # sem prazo
    assert not R.promissor("Promoção de cupom: oferta até 15/10 - vaga no estacionamento")[0]
    assert not R.promissor("Seu pedido foi enviado")[0]


def test_bom_dia_traz_relatorio_e_pede_para_conectar_email(monkeypatch):
    R.registrar("Varredura de disco feita: 12 GB duplicados")
    monkeypatch.setattr(R, "_gmail", lambda: type("G", (), {"logado": staticmethod(lambda: False)}))
    t = R.bom_dia()
    assert "Bom dia, Dono" in t and "Varredura de disco" in t and "/email" in t


def test_tick_manda_bom_dia_em_AUDIO_uma_vez_por_dia_e_zera_o_relatorio(monkeypatch):
    audios, textos = [], []
    from braniac import financeiro
    monkeypatch.setattr(financeiro, "verificar", lambda *a, **k: None)   # sem Chrome nos testes o Cofre avisaria "sessao caiu" e entraria em textos
    monkeypatch.setattr(R, "_gmail", lambda: type("G", (), {"logado": staticmethod(lambda: False)}))
    R.registrar("algo feito de madrugada, com bastante detalhe para a fala sair inteira.")
    au = lambda nome, fala: audios.append((nome, fala)) or "✅ ok"
    tx = lambda nome, t: textos.append(t) or "✅ ok"
    R.tick(datetime(2026, 10, 8, 5, 59), tx, au)
    assert not audios                                                              # antes das 6h nao manda
    R.tick(datetime(2026, 10, 8, 6, 5), tx, au)
    R.tick(datetime(2026, 10, 8, 6, 15), tx, au)
    assert len(audios) == 1 and "algo feito" in audios[0][1] and "Bom dia, Dono" in audios[0][1] and not textos      # audio, nada por escrito
    assert R.RELATORIO.read_text(encoding="utf-8") == ""


def test_bom_dia_falado_nao_tem_link_emoji_nem_underscore(monkeypatch):
    monkeypatch.setattr(R, "_gmail", lambda: type("G", (), {"logado": staticmethod(lambda: False)}))
    R.registrar("Teste test_pedido_de_reserva_ok falhou 🚨 veja https://exemplo.com/x e C:\pasta\arq.txt para detalhes completos aqui.")
    f = R.bom_dia_falado()
    assert "http" not in f and "🚨" not in f and "_" not in f and "C:" not in f and "agentes" in f


def test_se_o_audio_falhar_manda_so_um_aviso_curto():
    chamadas = []
    ok = R.entregar_bom_dia(lambda n, f: chamadas.append("a") or "falhou", lambda n, t: chamadas.append(t) or "✅ ok")
    assert ok and chamadas[:2] == ["a", "a"] and "não consegui gerar o áudio" in chamadas[2].lower()


def test_alerta_de_email_promissor_vai_para_dono_e_parceira_uma_vez(monkeypatch):
    class G:
        logado = staticmethod(lambda: True)
        _remetente = staticmethod(lambda m: "RH Acme")
        _cabecalho = staticmethod(lambda m, c: "")
        ler = staticmethod(lambda i, max_chars=0: "")
    monkeypatch.setattr(R, "_gmail", lambda: G)
    monkeypatch.setattr(R, "emails_do_dia", lambda horas=24, n=60: [("a1", "RH Acme", "Vaga remota de TI, inscrições até 20/10", True), ("a2", "Loja", "Cupom de desconto", False)])
    c, j = [], []
    assert R.verificar_promissores(c.append, j.append) == 1
    assert R.verificar_promissores(c.append, j.append) == 0                       # nao repete
    assert "Vaga remota" in c[0] and j[0].startswith("Parceira") and "a pedido do Dono" in j[0]


def test_db1_avisa_uma_vez_por_email(monkeypatch, tmp_path):
    from braniac import rotina
    monkeypatch.setattr(rotina, "ESTADO", tmp_path / "rotina.json")

    class G:
        def logado(self): return True
        def _get(self, caminho, **k):
            if caminho == "/messages":
                return {"messages": [{"id": "a1"}]}
            return {"payload": {"headers": [{"name": "From", "value": "DB1 <rh@db1.com.br>"}, {"name": "Subject", "value": "Próximos passos"}]}}
        def _remetente(self, m): return "DB1"
        def _cabecalho(self, m, n): return "Próximos passos"
    monkeypatch.setattr(rotina, "_gmail", lambda: G())
    enviados = []
    assert rotina.verificar_db1(enviados.append) == 1
    assert rotina.verificar_db1(enviados.append) == 0   # nao repete
    assert len(enviados) == 1 and "DB1" in enviados[0] and "Próximos passos" in enviados[0]
