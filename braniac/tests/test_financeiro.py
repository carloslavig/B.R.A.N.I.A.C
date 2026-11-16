from datetime import date, datetime

from braniac import financeiro as F

HOME = """Seu saldo é de

R$ 634,33
Cobrar
Extrato

Hoje • 27 Out, 2026

R$ 634,33

Pix BARATAO COMBUSTIVEIS

-R$ 95,13

09:19 • Enviado

Vendas

+R$ 14,01

01:10 • Depósito InfinitePay

Ontem • 26 Out, 2026

R$ 715,45

Pix JAVIANNY

+R$ 1.025,00

17:48 • Recebido
"""


def test_quinto_dia_util():
    assert F.quinto_dia_util(2026, 10) == date(2026, 10, 7)      # 1(qui) 2 5 6 7
    assert F.quinto_dia_util(2026, 11) == date(2026, 11, 9)      # 2/11 feriado: 3 4 5 6 9
    assert F.prazo_atual(date(2026, 10, 27)) == date(2026, 11, 9)
    assert F.prazo_atual(date(2026, 11, 9)) == date(2026, 11, 9)


def test_parsear():
    saldo, movs = F.parsear(HOME, date(2026, 10, 27))
    assert saldo == 634.33
    assert [(m["desc"], m["valor"], m["data"]) for m in movs] == [("Pix BARATAO COMBUSTIVEIS", -95.13, "2026-10-27"), ("Vendas", 14.01, "2026-10-27"), ("Pix JAVIANNY", 1025.0, "2026-10-26")]


def test_avaliar_niveis():
    movs = [{"data": "2026-10-20", "desc": "x", "valor": 700.0, "hora": ""}, {"data": "2026-10-25", "desc": "y", "valor": -100.0, "hora": ""}]
    assert F.avaliar(1700, movs, date(2026, 11, 3))["nivel"] == "batida"
    assert F.avaliar(300, movs, date(2026, 11, 6))["nivel"] == "critico"          # 1 dia util restante
    assert F.avaliar(634, [], date(2026, 10, 27))["nivel"] in ("atencao", "critico")
    assert "faltam" in F.texto(F.avaliar(634, movs, date(2026, 11, 5)))


def test_verificar_alerta_uma_vez_por_dia(monkeypatch):
    enviados = []
    ler = lambda h: (300.0, [])
    manha = datetime(2026, 11, 5, 10, 0)
    assert F.verificar(enviados.append, manha, ler)["nivel"] == "critico" and len(enviados) == 1
    F.ESTADO.write_text(F.ESTADO.read_text().replace('"ts"', '"x"'))               # libera a leitura horaria
    F.verificar(enviados.append, manha, ler)
    assert len(enviados) == 1                                                        # mesmo dia, mesmo nivel: nada
    F.ESTADO.write_text(F.ESTADO.read_text().replace('"ts"', '"x"'))
    F.verificar(enviados.append, datetime(2026, 11, 5, 23, 0), ler)
    assert len(enviados) == 1                                                        # fora do horario


def test_sessao_caida_avisa_uma_vez():
    enviados = []
    def ler(h):
        raise RuntimeError("sessao do InfinitePay caiu")
    F.verificar(enviados.append, datetime(2026, 11, 5, 10, 0), ler)
    assert len(enviados) == 1 and "logue" in enviados[0]


def test_parsear_saldo_pelo_extrato_quando_o_numero_nao_carrega():
    sem = HOME.replace("Seu saldo é de\n\nR$ 634,33", "Seu saldo é de\n\n")
    saldo, movs = F.parsear(sem, date(2026, 10, 27))
    assert saldo == 634.33 and len(movs) == 3


def test_parsear_espaco_nao_separavel():
    assert F.parsear(HOME.replace("R$ 634,33", "R$ 634,33"), date(2026, 10, 27))[0] == 634.33
