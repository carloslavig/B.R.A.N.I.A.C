# -*- coding: utf-8 -*-
"""Linha de comando do BRANIAC LINK (uso: python -m link COMANDO ...). Pasta dos dados: variavel BLINK_PASTA (padrao ./dados-link).
Comandos: id | convidar | aceitar CONVITE | conectar PAR | pares | sas PAR | confirmar PAR | revogar PAR | permitir PAR AGENTE ACAO NIVEL
          rede | escutar | msg PAR TEXTO | caps PAR | tarefa PAR AGENTE PEDIDO | arquivo PAR CAMINHO | pendencias | aprovar ID | recusar ID"""
import os
import sys
import time
from pathlib import Path

from . import confianca
from .identidade import Identidade
from .no import LinkErro, No

PASTA = Path(os.environ.get("BLINK_PASTA", "dados-link"))


def montar(executor=None, agentes=None, ao_msg=None):
    ident = Identidade(PASTA / "identidade", os.environ.get("BLINK_NOME", os.environ.get("COMPUTERNAME", "assistente")))
    return ident, confianca.Pares(PASTA), No(ident, confianca.Pares(PASTA), PASTA / "no", executor=executor, agentes=agentes, ao_msg=ao_msg)


def _par(pares, ref):
    achados = [i for i, p in pares.listar().items() if i == ref or p["nome"].lower() == ref.lower() or i.startswith(ref)]
    if len(achados) != 1:
        raise LinkErro(f"par '{ref}' nao encontrado ou ambiguo (use 'pares')")
    return achados[0]


def diagnostico_rede():
    """Mostra como a rede deste computador aparece para a internet (dois servidores STUN): mesma porta nos dois = bom para conexao direta;
    portas diferentes = NAT simetrico (conexao direta nao abre, precisa de TURN)."""
    import socket
    import struct
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(4)
    sock.bind(("0.0.0.0", 0))
    vistos = []
    for host, porta in (("stun.l.google.com", 19302), ("stun.cloudflare.com", 3478)):
        try:
            tid = os.urandom(12)
            sock.sendto(struct.pack(">HHI", 1, 0, 0x2112A442) + tid, (socket.gethostbyname(host), porta))
            d, _ = sock.recvfrom(2048)
            i = 20
            while i < len(d):
                t, n = struct.unpack(">HH", d[i:i + 4])
                if t == 0x0020:
                    p = struct.unpack(">H", d[i + 6:i + 8])[0] ^ 0x2112
                    ip = socket.inet_ntoa(bytes(x ^ y for x, y in zip(d[i + 8:i + 12], struct.pack(">I", 0x2112A442))))
                    vistos.append((ip, p))
                    print(f"{host}: visto como {ip}:{p}")
                    break
                i += 4 + n + (-n % 4)
        except OSError as e:
            print(f"{host}: sem resposta ({e})")
    if len(vistos) == 2:
        print("Resultado:", "BOM para conexao direta (NAT estavel)" if vistos[0] == vistos[1] else "NAT SIMETRICO: a conexao direta nao abre; use TURN")


def main(a):
    ident, pares, no = montar(ao_msg=lambda p, t: print(f"\n[mensagem de {p}] {t}", flush=True))
    cmd, args = (a[0] if a else "id"), a[1:]
    try:
        if cmd == "id":
            print(f"nome: {ident.nome}\nid:   {ident.id}")
        elif cmd == "convidar":
            print("Entregue este convite ao outro dono (vale 15 min, uso unico) e deixe 'escutar' rodando:\n\n" + pares.convidar(ident))
        elif cmd == "aceitar":
            c = pares.aceitar_convite(args[0])
            no.iniciar()
            no.conectar(c["id"], convite=True, timeout=60)
            print(f"Conectado a {c['nome'] or c['id']}. Codigo para conferir por voz/WhatsApp (SAS): {confianca.sas(ident.pub, c['pub'])}\n"
                  f"Se for igual nos dois lados: python -m link confirmar {c['id']}")
        elif cmd == "pares":
            for i, p in pares.listar().items():
                print(f"{i}  {p['nome']:<20} {p['estado']:<10} SAS {confianca.sas(ident.pub, p['pub'])}  perm {p.get('perm') or '-'}")
        elif cmd == "sas":
            print(confianca.sas(ident.pub, pares.get(_par(pares, args[0]))["pub"]))
        elif cmd == "confirmar":
            pares.confirmar(_par(pares, args[0]))
            print("Par confirmado.")
        elif cmd == "revogar":
            pares.revogar(_par(pares, args[0]))
            print("Par revogado.")
        elif cmd == "permitir":
            pares.permitir(_par(pares, args[0]), args[1], args[2], args[3])
            print("Permissao registrada.")
        elif cmd == "rede":
            diagnostico_rede()
        elif cmd == "escutar":
            no.iniciar()
            print(f"Escutando como {ident.nome} ({ident.id}). Ctrl+C para parar.")
            while True:
                time.sleep(3600)
        else:
            no.iniciar()
            par = _par(pares, args[0]) if args else ""
            if cmd == "msg":
                no.enviar_msg(par, " ".join(args[1:]))
                print("Entregue.")
            elif cmd == "caps":
                for ag in no.capacidades(par):
                    print(f"- {ag.get('nome')}: {ag.get('descricao', '')} {ag.get('capacidades', '')}")
            elif cmd == "tarefa":
                print(*no.pedir_tarefa(par, args[1], " ".join(args[2:])))
            elif cmd == "arquivo":
                no.enviar_arquivo(par, args[1])
                print("Arquivo entregue e conferido.")
            elif cmd == "pendencias":
                for p in no.pendencias():
                    print(p["id"], p["par"], p["agente"], p["pedido"][:80])
            elif cmd in ("aprovar", "recusar"):
                print(no.aprovar(args[0]) if cmd == "aprovar" else no.recusar(args[0]) or "Recusada.")
            else:
                print(__doc__)
    except (LinkErro, confianca.ConviteErro, IndexError) as e:
        print("Nao deu:", e or "faltou argumento")
    except KeyboardInterrupt:
        pass
    finally:
        no.parar()


if __name__ == "__main__":
    main(sys.argv[1:])
