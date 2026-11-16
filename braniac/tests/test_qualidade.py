from braniac import qualidade


def test_regex_pega_correcoes_e_ignora_conversa_normal():
    assert qualidade.CORRECAO.search("Não foi isso que eu perguntei")
    assert qualidade.CORRECAO.search("nada a ver")
    assert not qualidade.CORRECAO.search("ok, obrigado, pode mandar")


def test_medir_roda_sem_quebrar():
    t, e, lst = qualidade.medir(1)
    assert t >= 0 and e == len(lst)
