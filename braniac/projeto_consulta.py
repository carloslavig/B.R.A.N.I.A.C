# -*- coding: utf-8 -*-
"""PROJETO SEM REGISTRO (04/11/2026, pedido do Dono): quando ele fala de um projeto e o Jarvis nao acha nada parecido no banco, nem
numa pasta do PC, o Jarvis pergunta ao GPT (aba logada) e ao Claude (le as pastas) em segundo plano, guarda o que voltar como fato
(o banco passa a conhecer o projeto) e avisa o Dono. Cada projeto e consultado no maximo 1x por 24 h."""
import json
import re
import threading
import time
import unicodedata
from pathlib import Path

from .store import DATA

ARQ = DATA / "projetos_consultados.json"
PASTAS = [Path(__file__).resolve().parent.parent.parent, DATA / "empresa_dev" / "projetos"]     # C:\Users\usuario\Projetos e os projetos do NexoDev
DIA = 24 * 3600
PROJETO = re.compile(r"(?i)\b(?:projeto|app|aplicativo|jogo|site|sistema|plataforma|software)\s+(?:(?:d[aeo]s?|chamad[oa]|que\s+se\s+chama|o|a)\s+)?([A-Za-zÀ-ÿ0-9][\wÀ-ÿ-]{2,})")
NAO_NOME = {"novo", "nova", "novos", "novas", "que", "esse", "essa", "isso", "este", "esta", "meu", "minha", "nosso", "nossa", "seu", "sua", "dele", "dela", "atual", "anterior",
            "outro", "outra", "todo", "toda", "aquele", "aquela", "mesmo", "mesma", "pronto", "pronta", "bom", "boa", "legal", "bem", "mais", "menos", "tem", "esta", "esta",
            "para", "com", "sem", "uma", "uns", "umas", "seguinte", "aqui", "ali", "cliente", "clientes", "braniac", "jarvis", "airbnb", "whatsapp", "telegram", "ja", "ainda",
            "projetos", "apps", "sites", "sistemas", "jogos", "software", "tudo", "nada", "algum", "alguma", "qualquer", "funciona", "funcionando", "quebrado", "rodando"}


def _norm(t):
    return "".join(c for c in unicodedata.normalize("NFD", (t or "").lower()) if unicodedata.category(c) != "Mn")


def nome_do_projeto(texto):
    """Nome do projeto citado na frase ('o projeto Taximetro', 'app SePique') ou None."""
    for m in PROJETO.finditer(texto or ""):
        n = m.group(1).strip("-_")
        if _norm(n) not in NAO_NOME and not n.isdigit():
            return n
    return None


def _pasta(nome):
    """Pasta local parecida com o nome (SePique -> SePiqueRS, sepique-api...). Devolve Path ou None."""
    n = re.sub(r"[^a-z0-9]", "", _norm(nome))
    if len(n) < 3:
        return None
    for base in PASTAS:
        try:
            for p in sorted(base.iterdir()):
                q = re.sub(r"[^a-z0-9]", "", _norm(p.name))
                if p.is_dir() and q and (n in q or q in n) and len(q) >= 3:
                    return p
        except OSError:
            continue
    return None


def _resumo_da_pasta(p):
    for arq in ("README.md", "readme.md", "CLAUDE.md", "AGENTS.md", "package.json", "Cargo.toml"):
        try:
            txt = (p / arq).read_text(encoding="utf-8", errors="ignore").strip()
        except OSError:
            continue
        if txt:
            return re.sub(r"\s+", " ", txt)[:420]
    try:
        return "contém: " + ", ".join(sorted(x.name for x in p.iterdir())[:12])
    except OSError:
        return ""


def _no_banco(nome, texto):
    from . import banco
    try:
        r = banco.consultar(nome, n=6)[0]
    except Exception:
        return False
    # so conta como "conhecido" o fato que DESCREVE o projeto (nome seguido de plataforma/app/projeto/sistema...); mencao solta, em curriculo ou conversa, nao (04/11: Okara so aparecia no CV e o Jarvis respondeu com a Loja)
    desc = re.compile(rf"(?i){re.escape(_norm(nome))}\W{{0,3}}(?:e\s+|era\s+)?(?:um|uma|o|a)?\s*(?:plataforma|app|aplicativo|sistema|site|jogo|projeto|software)\b|(?:projeto|app|aplicativo|sistema|jogo|plataforma|site)\s+{re.escape(_norm(nome))}\W{{0,3}}(?:e|era|:|-)")
    return any(desc.search(_norm(l)) and "curriculo" not in _norm(l) and not _norm(l).startswith("[conversa-jarvis]") for l in (r or "").splitlines())


def _recente(nome):
    try:
        d = json.loads(ARQ.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    return time.time() - d.get(_norm(nome), 0) < DIA, d


def _marcar(nome, d):
    d[_norm(nome)] = time.time()
    try:
        ARQ.parent.mkdir(parents=True, exist_ok=True)
        ARQ.write_text(json.dumps(d), encoding="utf-8")
    except OSError:
        pass


def verificar(texto, perguntar_gpt, perguntar_claude, notificar, gravar_fato, sensivel=None):
    """Chamado a cada fala do Dono. Devolve None (nada a fazer) ou uma instrucao curta para o Jarvis incluir na resposta.
    perguntar_gpt(pergunta)->texto; perguntar_claude(tarefa, ao_terminar); notificar(texto); gravar_fato(chave, texto, fonte)."""
    nome = nome_do_projeto(texto)
    if not nome or _no_banco(nome, texto):
        return None
    pasta = _pasta(nome)
    if pasta:                                   # existe no PC: o Jarvis aprende na hora, sem gastar IA
        resumo = _resumo_da_pasta(pasta)
        if resumo:
            gravar_fato(f"projeto {nome}", f"Projeto {nome}: pasta {pasta.name} no PC do Dono. {resumo}", "pasta")
            return f"[PROJETO {nome.upper()}: achei a pasta '{pasta.name}' no PC e aprendi: {resumo[:300]}. Use isso e diga o que sabe.]"
    ja, d = _recente(nome)
    if ja:
        return f"[PROJETO {nome.upper()}: ja perguntei ao GPT e ao Claude nas ultimas 24h; diga que ainda nao tem resposta registrada se nao vier nada acima.]"
    _marcar(nome, d)
    frase = (texto or "").strip()[:250]
    if sensivel and sensivel.search(frase):     # dado sensivel nunca vai a IA online; so o Claude local (le as pastas) e acionado
        frase = ""
    pergunta = (f"Meu dono, Dono (desenvolvedor e fotografo em Cidade), citou o projeto \"{nome}\" ao assistente pessoal de IA dele"
                + (f", assim: \"{frase}\"" if frase else "") + ". O assistente nao tem nada registrado sobre esse projeto. "
                "O que provavelmente e esse projeto e que 3 perguntas curtas o assistente deve fazer ao Dono para entender? Resposta curta, em portugues.")
    tarefa = (f"SOMENTE LEITURA, nao altere arquivo nenhum. O Dono falou do projeto \"{nome}\" e o Jarvis nao tem nada sobre ele. Procure em C:\\Users\\usuario\\Projetos, "
              f"na memoria (C:\\Users\\usuario\\.claude\\projects\\C--Users-usuario\\memory) e em braniac\\data\\empresa_dev quem e esse projeto (o que e, estado, pasta, ultimo trabalho). "
              f"Se nao achar, diga isso. Responda em ate 8 linhas.")

    def gpt():
        try:
            r = (perguntar_gpt(pergunta) or "").strip()
        except Exception as e:
            r = f"nao consegui falar com o GPT ({str(e)[:80]})"
        if r and not r.lower().startswith(("nao consegui", "pergunta barrada", "ia desconhecida")):
            gravar_fato(f"projeto {nome} (gpt)", f"Projeto {nome}: segundo o GPT, {r[:500]}", "gpt")
        notificar(f"🔎 Projeto \"{nome}\" — o que o GPT disse:\n\n{r[:900]}")

    def claude_fim(r):
        r = (r or "").strip()
        if r and "nao achei" not in _norm(r)[:80] and not r.startswith(("⚠", "❌")):
            gravar_fato(f"projeto {nome} (claude)", f"Projeto {nome}: segundo o Claude (que olhou o PC), {r[:600]}", "claude")
        notificar(f"🔎 Projeto \"{nome}\" — o que o Claude achou:\n\n{r[:1200]}")

    threading.Thread(target=gpt, daemon=True, name="braniac-projeto-gpt").start()
    try:
        perguntar_claude(tarefa, claude_fim)
    except Exception as e:
        notificar(f"Não consegui acionar o Claude sobre \"{nome}\": {str(e)[:100]}")
    return (f"[PROJETO {nome.upper()}: NAO ha nada sobre ele no banco nem numa pasta do PC. Diga ao Dono, em 1 frase natural, que ainda nao conhece esse projeto, "
            "que ja perguntou ao GPT e ao Claude e que avisa quando voltarem. Nao invente nada sobre o projeto.]")
