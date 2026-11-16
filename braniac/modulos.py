"""Modulos do Braniac: a base sempre liga; cada andar/rotina opcional so roda se a pessoa escolheu.

Instalacao nova: a pessoa escolhe os modulos (painel > Modulos, ou o instalador) e o arquivo
data/modulos.json passa a existir. Instalacao antiga (sem o arquivo) segue com TUDO ligado,
para nada mudar de uma hora para outra.
"""
import json
from pathlib import Path

ARQUIVO = Path(__file__).parent / "data" / "modulos.json"

CATALOGO = [
    {"id": "programacao", "nome": "Programação (NexoDev)", "andar": "NexoDev",
     "desc": "Empresa de agentes que desenvolve software: tickets, revisão, testes e build. Usa ChatGPT/DeepSeek para o código e o Claude para revisar."},
    {"id": "marketing", "nome": "Marketing (Fornalha)", "andar": "Fornalha",
     "desc": "Agentes de marketing: pauta do dia, imagens e vídeos a partir das suas fotos, legendas e entrega no Drive."},
    {"id": "investimentos", "nome": "Investimentos (Quantix)", "andar": "Quantix",
     "desc": "Agentes que simulam investimentos por perfil (day trade, swing, holding) com limites de risco. Só simulação: ordem real exige o seu OK e não existe integração com corretora."},
    {"id": "cortes_video", "nome": "Cortes de vídeo (Claquete)", "andar": "Claquete",
     "desc": "Agentes que cortam falas de entrevistas/podcasts em vídeos verticais com gameplay e legenda. Nada é publicado sem o seu OK."},
    {"id": "compras", "nome": "Compras (Pechincha)", "andar": "Pechincha",
     "desc": "Agentes que pesquisam o melhor modelo para o seu uso, acham o mais barato nas lojas online e confirmam que é o modelo certo. Só recomenda: nunca compra."},
    {"id": "financeiro", "nome": "Finanças e metas (Cofre)", "andar": "",
     "desc": "Acompanha o saldo da conta (só leitura) e avisa se a meta do mês estiver em risco."},
    {"id": "airbnb", "nome": "Hospedagem (Airbnb, Ilhéu)", "andar": "",
     "desc": "Lê e responde hóspedes do Airbnb pela sua conta (o atendimento automático continua desligado até você ligar) e acompanha reservas."},
    {"id": "exercito", "nome": "Exército e concursos (Cabo Tito)", "andar": "",
     "desc": "Prazos, exames e cronograma do edital militar, com avisos na agenda."},
    {"id": "vaquinha", "nome": "Vaquinha", "andar": "",
     "desc": "Acompanha o valor arrecadado de uma vaquinha e atualiza o site dela, perguntando o saldo a quem cuida da conta."},
    {"id": "email", "nome": "E-mail e vagas (Correio, Garimpeiro)", "andar": "",
     "desc": "Lê o Gmail, resume o que importa e procura vagas de trabalho que combinam com você."},
]
IDS = [m["id"] for m in CATALOGO]


def _ler():
    try:
        return json.loads(ARQUIVO.read_text(encoding="utf-8"))
    except Exception:
        return None


def configurado():
    return _ler() is not None


def ativos():
    """Ids ligados. Sem arquivo (instalacao antiga) = todos."""
    d = _ler()
    if d is None:
        return list(IDS)
    return [i for i in d.get("ativos", []) if i in IDS]


def ativo(id_):
    return id_ in ativos()


def exigir(id_):
    """Levanta se o modulo esta desligado; usado dentro de try/except que ja existe nos ticks."""
    if not ativo(id_):
        raise RuntimeError(f"modulo {id_} desligado")


def definir(ids):
    ids = [i for i in dict.fromkeys(ids or []) if i in IDS]
    ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
    ARQUIVO.write_text(json.dumps({"ativos": ids}, ensure_ascii=False, indent=1), encoding="utf-8")
    return ids


def estado():
    on = set(ativos())
    return {"configurado": configurado(), "modulos": [{**m, "ativo": m["id"] in on} for m in CATALOGO]}
