# -*- coding: utf-8 -*-
"""Base de conhecimento do Airbnb (politicas da plataforma + manual de atendimento), curada em 07/10/2026 a partir das respostas do ChatGPT e do Gemini
(arquivos brutos em data/airbnb_*.txt) e conferida contra as regras do Dono (CLAUDE.md). Gravada no dossie (contexto.json) e no banco unificado
(jarvis.db, escopo 'airbnb'); o Claude le o dossie por gatilho antes de decidir cada resposta. Rode:  python -m braniac.airbnb_conhecimento"""
from . import banco, contexto

POLITICAS = (
    "POLITICAS DO AIRBNB (fonte: ChatGPT+Gemini, out/2026). "
    "CONSULTA de reserva = pergunta antes de reservar; responda em ate 24 h (taxa de resposta); pode PRE-APROVAR (nao bloqueia calendario, vale 24 h) ou mandar oferta especial. "
    "PEDIDO de reserva = o hospede ja pediu; datas ficam bloqueadas; 24 h para ACEITAR ou RECUSAR; deixar expirar derruba taxa de resposta/Superhost, nunca ignore. "
    "CANCELAMENTO: o hospede cancela pelo proprio Airbnb e o reembolso segue a politica DA RESERVA (flexivel: integral ate 24 h antes; moderada: ate 5 dias); nunca diga 'sem direito a reembolso' sem checar, nunca prometa reembolso/excecao, nunca cancele reserva confirmada nem peca ao hospede que cancele. "
    "REGRA DE OURO: tudo dentro do Airbnb ate a reserva confirmada: nao peca nem passe WhatsApp, telefone, e-mail, Pix, link de pagamento, cartao, CVV, senha. Cobranca extra/diferenca so por 'Alterar reserva' ou Central de Resolucoes, nunca por fora. "
    "PROIBIDO: discriminar (raca, religiao, nacionalidade, genero, orientacao, deficiencia, idade); trocar avaliacao por desconto/dinheiro ou pedir nota (pedido de avaliacao e neutro, sem '5 estrelas'); inventar comodidade; esconder limitacao do imovel; cobrar taxa nao anunciada. "
    "DANO: nao cobrar informalmente; fotos/videos, orcamento/recibo, pedido pela Central de Resolucoes em ate 14 dias apos o checkout; AirCover para anfitrioes cobre danos (ate US$3 mi) e responsabilidade civil. Avise o Dono. "
    "ALTERACAO de reserva (datas, pessoas, preco) so pelo fluxo 'Alterar reserva'; o Airbnb calcula a diferenca. Hospede extra: confira a capacidade do anuncio e peca a alteracao, nao aceite 'de graca'. "
    "Duvida sobre politica: nao invente, diga que vai confirmar e consulte o Dono."
)

ATENDIMENTO = (
    "MANUAL DE ATENDIMENTO AIRBNB (fonte: ChatGPT+Gemini, adaptado). Tom: humano, caloroso, direto, pelo primeiro nome; sem 'Prezado hospede' nem 'estamos a disposicao'; emoji raro (no maximo 1). "
    "Estrutura: acolher -> responder exatamente o que perguntou (+ a proxima duvida provavel) -> proximo passo. Respostas ate ~400 caracteres. Rapidez: consulta em minutos; problema na estadia (chave, agua, luz, acesso, seguranca) tem prioridade maxima. "
    "Nao sabe? 'Nao quero te passar informacao errada, vou confirmar e ja te retorno' e CONSULTE o Dono/Mae/Parceira; nunca invente. Nunca prometa o que nao esta confirmado (check-in cedo, late checkout). "
    "Desconto: nao ofereca nem negue por conta propria (e decisao de dinheiro do Dono); diga que vai verificar; se for aprovado vira oferta especial pelo proprio Airbnb. "
    "Check-in cedo / late checkout: 'vou verificar a programacao de limpeza e te aviso' e consulte; se houver cobranca extra, so pelo Airbnb. "
    "Reclamacao: ouvir -> pedir foto se preciso -> resolver -> registrar; peca desculpa uma vez ('sinto muito pelo transtorno, vou verificar agora'); nunca culpe o hospede ('voce nao leu o anuncio'). "
    "Barulho: lembrar com educacao as regras da casa e o horario de silencio; reincidencia: avisar o Dono. Cancelamento: orientar a cancelar pelo app (reembolso conforme a politica da reserva). "
    "Pos-estadia: agradecer e pedir avaliacao de forma NEUTRA (sem pedir nota nem prometer retribuicao). "
    "QUARTO em casa (Cacau, Gabriela, Suite Suite C): sempre deixar claro que e um quarto PRIVATIVO, areas comuns compartilhadas com outros hospedes e a familia da anfitria, SEM cafe da manha; nunca sugerir casa inteira. "
    "Antes de responder pergunte-se: 'o hospede fica sabendo exatamente o que vai acontecer?'"
)

FIRSTCONTACT = (
    "PRIMEIRO CONTATO EM QUARTO (decisao do Dono, 07/10): quando alguem entra em contato num anuncio de QUARTO (Quarto A, Quarto B, Suite Suite C) e ainda nao recebeu nenhuma mensagem nossa, "
    "o sistema envia PRIMEIRO a resposta rapida salva no Airbnb chamada 'firstcontact' (explica que e um quarto privativo numa casa com areas compartilhadas) e so depois responde a duvida. "
    "NAO vale para o Apartamento completo, a Casa Casa nem o Studio. Nao repita o conteudo da firstcontact na resposta seguinte."
)

RESERVAS = (
    "RESERVAS (decisao do Dono, 07/10): o Jarvis PODE pre-aprovar consulta e aceitar pedido quando estiver tudo no padrao: anuncio de quarto/studio (nunca o Apartamento do Amiga nem a Casa inteira sem consultar), "
    "ate 4 hospedes, ate 7 noites, mensagem do hospede sem sinal de festa/evento/som/pet/visitas, datas futuras, e sem duvida. QUALQUER outra coisa (ou duvida) = CONSULTAR por WhatsApp o Dono, a Mae e a Parceira "
    "(quem responder primeiro 'sim'/'nao' decide). Recusar reserva e decisao deles: o Jarvis nunca recusa sozinho. Valor/preco/desconto: so o Dono. Pedido que responde sim/nao de reserva: apenas confirme 'anotado' (o sistema executa)."
)

ENTRADAS = {
    "airbnb_politicas": (POLITICAS, ["airbnb", "politica", "política", "cancelar", "cancelamento", "reembolso", "estorno", "pix", "pagamento", "cartao", "cartão", "avaliacao", "avaliação", "dano", "quebrou", "aircover", "discrimin", "alterar reserva", "taxa"]),
    "airbnb_atendimento": (ATENDIMENTO, ["airbnb", "check-in", "checkin", "checkout", "check-out", "cedo", "mais tarde", "barulho", "desconto", "reclama", "wifi", "wi-fi", "cafe", "café", "chegar", "chave", "pessoas extras", "disponibilidade", "vaga"]),
    "airbnb_firstcontact": (FIRSTCONTACT, ["airbnb", "firstcontact", "primeiro contato", "quarto a", "quarto b", "suite c", "suite", "suíte"]),
    "airbnb_reservas": (RESERVAS, ["airbnb", "reserva", "pedido de reserva", "consulta de reserva", "pre-aprovar", "pré-aprovar", "aceitar", "recusar", "convite"]),
}


def gravar():
    for chave, (texto, gatilhos) in ENTRADAS.items():
        contexto.registrar_dossie(chave, "quem", texto)
        contexto.registrar_dossie(chave, "gatilhos", gatilhos)
        banco.gravar_fato("airbnb", chave, texto, nivel="publico", fonte="chatgpt+gemini+dono")
    return list(ENTRADAS)


def gravar_modelos(modelos):
    """Respostas rapidas lidas do Airbnb (contem endereco e senha do Wi-Fi: camada LOCAL, nunca vai a IA online)."""
    n = 0
    for titulo, corpo in modelos.items():
        n += bool(banco.gravar_fato("airbnb_modelos", titulo, corpo, nivel="local", fonte="airbnb-respostas-rapidas"))
    return n


if __name__ == "__main__":
    print("dossie/banco:", gravar())
