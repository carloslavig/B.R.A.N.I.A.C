from braniac import correio, vagas


def test_classifica_email():
    c = correio.classificar
    assert c("Maria Souza", "maria@gmail.com", "Oi, tudo bem?", {}, ["INBOX"]) == "pessoa"
    assert c("Loja X", "no-reply@loja.com", "Seu pedido", {}, ["INBOX"]) == ""
    assert c("Maria", "maria@x.com", "Oi", {"list-unsubscribe": "<x>"}, []) == ""
    assert c("Recrutador", "rh@empresa.com", "Vaga de suporte remoto", {"list-unsubscribe": "<x>"}, ["INBOX"]) == "trabalho"
    assert c("Cupom", "a@b.com", "Vaga com desconto black friday", {}, ["CATEGORY_PROMOTIONS"]) == ""


def test_filtra_vagas():
    jobs = [{"id": 1, "candidate_required_location": "USA only", "salary": ""}, {"id": 2, "candidate_required_location": "Worldwide", "salary": ""},
            {"id": 3, "candidate_required_location": "Brazil", "salary": "$50k"}, {"id": 4, "candidate_required_location": "Worldwide", "salary": ""}]
    assert [j["id"] for j in vagas.filtrar(jobs, {"4"})] == [3, 2]
