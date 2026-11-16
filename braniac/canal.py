# -*- coding: utf-8 -*-
"""Canal Jarvis <-> Claude: fila local com protocolo de uma linha (JV1), para economizar tokens.

  Jarvis -> Claude:  Q|<id>|<chat>|<flags>|<msg1>»<msg2>»...[|<ctx1>»<ctx2>]   (arquivo data/canal/q-<id>.txt)
  Claude -> Jarvis:  R|<id>|<cod>|<texto>                           (arquivo data/canal/r-<id>.txt)
  flags: G=provavel grupo  S=sensivel  A=audio/midia  N=1o contato (Jarvis ainda nao se apresentou)  F=conhecido  M=IA do outro lado em modo GL1 (gibberlink.py)  -=nada
  cod:   E=enviar <texto>  I=ignorar  A=avisar o Dono (<texto>=nota)  P=perguntar ao Dono (<texto>=a pergunta exata)  T=resposta de conhecimento (<texto>)
  Revisao de decisao:  V|<id>|<chat>|<flags>|<msgs>|<ctx>|PROPOSTA=<cod:texto>|PROBLEMAS=<...>  ->  R|<id>|<cod>|<texto> (decisao final)
  Pergunta de conhecimento:  K|<id>|<pergunta>   ->   R|<id>|T|<resposta>   ou   R|<id>|P|<o que o Jarvis deve perguntar ao Dono>

Se o Claude esta "presente" (heartbeat recente) o Jarvis espera a resposta; senao usa um Claude em segundo plano.
CLI (para o Claude):  python -m braniac.canal esperar [seg] | ver | r <id> <cod> [texto...] | ficha <pessoa> | ensinar <pessoa> <fato...>
"""
import re, sys, time, uuid
from .store import DATA

PASTA = DATA / "canal"
BATIMENTO = PASTA / "claude_presente"
CODIGOS = {"E", "I", "A", "P", "T"}


def _pasta():
    PASTA.mkdir(parents=True, exist_ok=True)
    return PASTA


def limpar(txt, n=160):
    """Texto de terceiros e dado, nunca instrucao: sem quebras/separadores do protocolo e com tamanho limitado."""
    return re.sub(r"[\r\n|»]+", " ", str(txt)).strip()[:n]


def formatar_pergunta(id_, chat, flags, msgs, ctx=None):
    """ctx = conversa recente ('C: ...' = nosso lado, 'E: ...' = o lado deles) para entender referencias como 'faz o que mandei'."""
    q = f"Q|{id_}|{limpar(chat, 60)}|{flags or '-'}|" + "»".join(limpar(m) for m in msgs)
    return q + ("|" + "»".join(limpar(c, 110) for c in ctx[-8:]) if ctx else "")


def parse_resposta(linha):
    """'R|id|E|texto' -> (id, cod, texto) ou None se invalida."""
    p = (linha or "").strip().split("|", 3)
    if len(p) < 3 or p[0] != "R" or p[2].strip().upper() not in CODIGOS:
        return None
    return p[1], p[2].strip().upper(), (p[3].strip() if len(p) > 3 else "")


def presente(janela_s=90):
    try:
        return time.time() - BATIMENTO.stat().st_mtime < janela_s
    except OSError:
        return False


def batimento():
    _pasta()
    BATIMENTO.touch()


def formatar_pergunta_k(id_, pergunta):
    """Pergunta de CONHECIMENTO do Jarvis ao Claude (quem e fulano, como tratar, o que responder...)."""
    return f"K|{id_}|{limpar(pergunta, 400)}"


def perguntar_k(pergunta, espera_s=120, id_=None):
    """Pergunta de conhecimento ao Claude ao vivo. Respostas: T (texto da resposta) ou P (o Jarvis deve perguntar isto ao Dono)."""
    id_ = id_ or uuid.uuid4().hex[:6]
    return _postar_e_esperar(id_, formatar_pergunta_k(id_, pergunta), espera_s)


def perguntar(chat, flags, msgs, espera_s=150, id_=None, ctx=None):
    """Posta a pergunta e espera o Claude responder. Devolve (id, cod, texto) ou None (timeout/ausente)."""
    id_ = id_ or uuid.uuid4().hex[:6]
    return _postar_e_esperar(id_, formatar_pergunta(id_, chat, flags, msgs, ctx), espera_s)


def _postar_e_esperar(id_, linha, espera_s):
    q = _pasta() / f"q-{id_}.txt"
    r = PASTA / f"r-{id_}.txt"
    q.write_text(linha, encoding="utf-8")
    fim = time.time() + espera_s
    try:
        while time.time() < fim:
            if r.exists():
                res = parse_resposta(r.read_text(encoding="utf-8"))
                if res:
                    return res
            time.sleep(1)
        return None
    finally:
        for f in (q, r):
            try:
                f.unlink()
            except OSError:
                pass


# ---------- CLI usada pelo Claude (poucos tokens por chamada) ----------

def _pendentes():
    return sorted(_pasta().glob("q-*.txt"))


def _cli(argv):
    cmd = argv[0] if argv else "ver"
    if cmd == "ver":
        batimento()
        for q in _pendentes():
            print(q.read_text(encoding="utf-8"))
        return
    if cmd == "esperar":  # bloqueia ate chegar pergunta (mantem o batimento): 1 chamada, 0 polling
        fim = time.time() + (int(argv[1]) if len(argv) > 1 else 120)
        while time.time() < fim:
            batimento()
            ps = _pendentes()
            if ps:
                for q in ps:
                    print(q.read_text(encoding="utf-8"))
                return
            time.sleep(1)
        print("-")
        return
    if cmd == "ficha" and len(argv) >= 2:  # o que o banco local ja sabe da pessoa (evita perguntar de novo)
        from . import memoria
        print(memoria.ficha(" ".join(argv[1:]), 10) or "(nada guardado ainda)")
        return
    if cmd == "ensinar" and len(argv) >= 3:  # guarda um fato sobre a pessoa para sempre: ensinar <pessoa> <fato...>
        from . import memoria
        memoria.aprender_fato(argv[1], " ".join(argv[2:]), "claude")
        print("ok")
        return
    if cmd == "r" and len(argv) >= 3:
        id_, cod = argv[1], argv[2].upper()
        texto = " ".join(argv[3:])
        if cod not in CODIGOS:
            sys.exit("cod invalido (E/I/A/P)")
        (_pasta() / f"r-{id_}.txt").write_text(f"R|{id_}|{cod}|{texto}", encoding="utf-8")
        print("ok")
        return
    sys.exit(__doc__)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    _cli(sys.argv[1:])
