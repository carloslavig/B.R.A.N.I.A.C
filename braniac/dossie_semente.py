# -*- coding: utf-8 -*-
"""Dossie inicial do Jarvis: o que ele precisa saber sobre as pessoas e os assuntos do dono.
O conteudo pessoal fica em data/pessoal.json (chave "dossie", fora do Git); aqui so ha o formato e um padrao generico.
Cada entrada: quem/o que e, o que aconteceu recentemente, o que esta pendente. 'gatilhos' = palavras que ativam a entrada.
O Jarvis tambem escreve aqui (ferramenta lembrar)."""
from . import pessoal as _pessoal

_PADRAO = {
    "dono": {
        "gatilhos": ["dono", "eu"],
        "quem": "O dono deste Braniac. Detalhes ficam no banco local; nada pessoal vem junto do programa.",
        "recente": "",
        "pendente": "",
    },
}

DOSSIE = _pessoal.get("dossie") or _PADRAO
