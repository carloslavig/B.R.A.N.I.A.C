from braniac import airbnb_escalada as E

D = {"mae": "Mae", "dono": "Dono", "parceira": "Parceira"}


def test_escada_reserva_e_resolucao(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "ARQ", tmp_path / "e.json")
    monkeypatch.setattr(E, "LOG", tmp_path / "l.log")
    env = []
    p = {"1": {"tipo": "reserva", "hospede": "Ana"}}
    f = lambda n, t: env.append(n)
    E.passo(p, {"1"}, 0, f, D)            # reserva: mae na hora
    E.passo(p, {"1"}, 899, f, D)          # antes de 15 min: nada
    E.passo(p, {"1"}, 901, f, D)          # 15 min: Dono
    E.passo(p, {"1"}, 901 + 899, f, D)    # menos de 15 min depois: nada
    E.passo(p, {"1"}, 901 + 901, f, D)    # 15 min depois: Parceira (total 30 min)
    E.passo(p, {"1"}, 901 + 901 + 901, f, D)   # ciclo (a cada 15 min): mae e Dono (total 45 min)
    assert env == ["Mae", "Dono", "Parceira", "Mae", "Dono"]
    assert [k for k in E.passo({}, {"1"}, 2000, f, D) if k != "_ok"] == []     # alguem respondeu: some


def test_mensagem_30_min_mae_e_dono_um_lembrete(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "ARQ", tmp_path / "e.json")
    monkeypatch.setattr(E, "LOG", tmp_path / "l.log")
    env = []
    f = lambda n, t: env.append((n, t))
    p = {"2": {"tipo": "mensagem", "hospede": "Bia", "anuncio": "Quarto A", "previa": "Tem toalha? meu cartao 4111 1111 1111 1111", "sig": "x"}}
    for t in (0, 60, 900, 1799):
        E.passo(p, {"2"}, t, f, D)
    assert env == []                                   # menos de 30 min: ninguem
    E.passo(p, {"2"}, 1800, f, D)
    E.passo(p, {"2"}, 1830, f, D)                      # ciclo seguinte nao duplica
    assert [n for n, _ in env] == ["Mae", "Dono"]
    mae, dono = env[0][1], env[1][1]
    assert mae.startswith("oh minha tia") and "Bia" in mae and "Quarto A" in mae and "toalha" in mae
    assert dono.startswith("Senhor") and "4111" not in mae + dono
    for t in (2000, 3599):
        E.passo(p, {"2"}, t, f, D)
    assert len(env) == 2
    E.passo(p, {"2"}, 3600, f, D)                      # 1 lembrete 30 min depois
    assert [n for n, _ in env] == ["Mae", "Dono", "Mae", "Dono"] and "lembrete" in env[3][1]
    for t in (5400, 7200, 20000):
        E.passo(p, {"2"}, t, f, D)
    assert len(env) == 4                               # e para
    assert [k for k in E.passo({}, {"2"}, 20100, f, D) if k != "_ok"] == []   # respondido: some


def test_ja_respondi_silencia_ate_mensagem_nova(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "ARQ", tmp_path / "e.json")
    monkeypatch.setattr(E, "LOG", tmp_path / "l.log")
    env = []
    f = lambda n, t: env.append(n)
    p = {"9": {"tipo": "mensagem", "hospede": "Leonardo", "sig": "oi|09:42"}}
    E.passo(p, {"9"}, 0, f, D)
    E.passo(p, {"9"}, 1800, f, D)                      # mae e Dono avisados
    assert "Leonardo" in E.reconhecer("ja respondi o Leonardo no airbnb")
    E.passo(p, {"9"}, 3700, f, D)
    E.passo(p, {"9"}, 5000, f, D)
    assert env == ["Mae", "Dono"]                             # nada mais enquanto a mensagem e a mesma
    p2 = {"9": {"tipo": "mensagem", "hospede": "Leonardo", "sig": "e ai?|10:50"}}
    E.passo(p2, {"9"}, 6000, f, D)
    E.passo(p2, {"9"}, 7800, f, D)
    assert env == ["Mae", "Dono", "Mae", "Dono"]                      # mensagem NOVA volta a escalar


def test_filtra_avisos_do_airbnb_e_reservas_ja_decididas():
    L = lambda meta, previa: {"meta": meta, "previa": previa}
    for meta, previa in [("5 – 14 de jan. de 2027", "A pré-aprovação expirou"), ("Pendente. 14 – 16 de nov.", "O pedido de reserva expirou"),
                         ("Cancelada. 20 – 22 de nov.", "O pedido de reserva foi cancelado"), ("6 – 9 de nov.", "Pré-aprovação enviada"),
                         ("Consulta. 7 – 9 de nov.", "Uma mensagem foi cancelada"), ("Confirmada. 1 – 3 de dez.", "Reserva confirmada")]:
        assert E.ja_resolvido(L(meta, previa)), (meta, previa)
    for meta, previa in [("Consulta. 7 – 9 de nov.", "Vocês aceitam pet?"), ("Pendente. 14 – 16 de nov.", "Pedido de reserva"),
                         ("Consulta. 5 – 7 de nov.", "Preciso cancelar, posso?"), ("11 – 15 de dez.", "Tem vaga na garagem?")]:
        assert not E.ja_resolvido(L(meta, previa)), (meta, previa)


def test_aviso_a_parceira_vem_do_jarvis_nunca_do_claudinho():
    from braniac import airbnb_escalada as e
    t = e._texto("parceira", {"hospede": "Luan", "tipo": "reserva"}, 30)
    assert "Jarvis" in t and "Claudinho" not in t
