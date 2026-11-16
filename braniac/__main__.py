# -*- coding: utf-8 -*-
"""Uso:
  python -m braniac chat "mensagem" [--conv nome]
  python -m braniac status
"""
import argparse, sys
from .router import Router, TodosFalharam

sys.stdout.reconfigure(encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(prog="braniac")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("chat")
    c.add_argument("texto")
    c.add_argument("--conv", default="teste")
    sub.add_parser("status")
    a = ap.parse_args()
    r = Router()
    if a.cmd == "status":
        print(r.status())
        return
    try:
        resp, quem = r.responder(a.conv, a.texto)
    except TodosFalharam as e:
        print(f"[ERRO] nenhum provedor respondeu: {e}")
        sys.exit(1)
    print(f"[{quem}] {resp}")


main()
