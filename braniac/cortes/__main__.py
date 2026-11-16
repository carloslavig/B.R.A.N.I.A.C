# -*- coding: utf-8 -*-
"""python -m braniac.cortes <comando>

  vigiar                      roda o vigia (lives, clipes, VODs, publicacao) em primeiro plano
  ligar | desligar            sobe/para o vigia em segundo plano
  status | listar [status]    situacao e fila
  detectar ARQ [--chat X]     so mostra os momentos que viraram corte (nao renderiza)
  processar ARQ|LINK [--chat X] [--canal C]   gera os cortes de um arquivo, VOD ou clipe
  aprovar N|todos · rejeitar N · publicar
  youtube-login [--perfil P]  login OAuth do YouTube (feito pelo Dono, uma vez por canal; P = gringo p/ o canal em ingles)
  youtube-canal --perfil P    aplica Sobre/palavras-chave/playlists de data/cortes/canal_P.json no canal do perfil
  descobrir [--idioma en]     maiores lives agora no idioma (API da Twitch) para escolher canais
"""
import argparse, json, sys
from . import comandos, config, deteccao, youtube


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="python -m braniac.cortes", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("comando")
    ap.add_argument("alvo", nargs="?", default="")
    ap.add_argument("--chat")
    ap.add_argument("--canal")
    ap.add_argument("--perfil", default="")
    ap.add_argument("--idioma", default="en")
    a = ap.parse_args(argv)
    c = a.comando
    if c == "vigiar":
        from .vigia import Vigia
        Vigia().rodar()
    elif c == "detectar":
        print(json.dumps(deteccao.detectar(a.alvo, a.chat, config.carregar()), ensure_ascii=False, indent=2))
    elif c == "processar":
        print(comandos.processar(a.alvo, a.chat, a.canal))
    elif c == "youtube-login":
        print(youtube.login(config.do_perfil(a.perfil).get("youtube_conta", "") if a.perfil else ""))
    elif c == "youtube-canal":
        print(youtube.configurar_canal(a.perfil or "gringo"))
    elif c == "descobrir":
        from . import twitch
        try:
            lives = twitch.descobrir(a.idioma)
        except RuntimeError as e:
            print(e)
            return 1
        for s in lives:
            print(f"{s['espectadores']:>7} espectadores  {s['login']:<22} {s['jogo']}")
    elif c in ("status", "listar", "aprovar", "rejeitar", "publicar", "ligar", "desligar"):
        print(comandos.executar(c, a.alvo))
    else:
        ap.print_help()
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
