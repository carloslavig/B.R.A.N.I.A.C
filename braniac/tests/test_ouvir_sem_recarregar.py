from braniac import wpp_voz


class _Aba:
    def __init__(self, blobs):
        self.blobs, self.cmds, self.jss = blobs, [], []

    def js(self, expr):
        self.jss.append(expr)
        return self.blobs if "length" in expr else None

    def cmd(self, *a, **k):
        self.cmds.append(a)
        return {}


def test_pega_audio_sem_recarregar_e_zera_a_lista_antes(monkeypatch):
    monkeypatch.setattr(wpp_voz, "_abrir_chat", lambda W, w, nome: ("Pai", None))
    monkeypatch.setattr(wpp_voz.time, "sleep", lambda s: None)
    monkeypatch.setattr(wpp_voz, "_log_voz", lambda t: None)
    aba = _Aba(1)
    assert wpp_voz._audios_sem_recarregar(None, aba, "Pai")
    assert "window.__aud=[]" in aba.jss and not any("Page.reload" in str(c) for c in aba.cmds)


def test_sem_audio_novo_devolve_false_para_recarregar(monkeypatch):
    monkeypatch.setattr(wpp_voz, "_abrir_chat", lambda W, w, nome: ("Pai", None))
    monkeypatch.setattr(wpp_voz.time, "sleep", lambda s: None)
    assert not wpp_voz._audios_sem_recarregar(None, _Aba(0), "Pai")
    monkeypatch.setattr(wpp_voz, "_abrir_chat", lambda W, w, nome: (None, "nao achei"))
    assert not wpp_voz._audios_sem_recarregar(None, _Aba(1), "Pai")
