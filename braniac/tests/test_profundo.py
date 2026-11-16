# -*- coding: utf-8 -*-
from braniac import profundo


def test_planeja_executa_confere_e_corrige():
    chamadas, avisos, entregue = [], [], []

    def perguntar(t):
        if t.startswith("Planeje"):
            return '{"etapas":["achar A","achar B"],"pronto_quando":"A e B"}'
        if t.startswith("Confira"):
            return '{"ok": false, "falta": "faltou C"}' if not any("correcao" in c for c in chamadas) else '{"ok": true}'
        return "RESPOSTA FINAL"

    def agente(t):
        chamadas.append(t)
        return "fato"
    out = profundo.executar("descobrir tudo", agente, perguntar, avisos.append, entregue.append)
    assert out.startswith("RESPOSTA FINAL") and entregue == [out]
    assert len([c for c in chamadas if "ETAPA" in c]) == 2 and any("CORRIJA" in c for c in chamadas)
    assert any("corrigindo" in a for a in avisos)


def test_plano_invalido_vira_uma_etapa_e_etapa_que_falha_nao_derruba():
    def agente(t):
        raise RuntimeError("caiu")
    out = profundo.executar("x", agente, lambda t: "nada json", None, None)
    assert "RESPOSTA" in out.upper() or "nada json" in out
