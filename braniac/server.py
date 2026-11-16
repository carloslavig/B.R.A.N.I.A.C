# -*- coding: utf-8 -*-
"""Interface web do Jarvis (so em 127.0.0.1) + API. Sem dependencias externas."""
import json, os, socket, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from . import airbnb_vigia, b2, escuta, gmail, grupo_ia, jarvis, power, spotify, vigia
from .router import Router

PORTA = int(os.environ.get("BRANIAC_PORTA", "8765"))
HTML = (Path(__file__).parent / "ui" / "index.html").read_bytes()
AVISOS = []  # respostas assincronas (ex.: Claude terminou) que a interface busca em /api/avisos


def montar_handler(router):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, obj, code=200):
            b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def _corpo(self):
            n = int(self.headers.get("Content-Length") or 0)
            try:
                return json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return {}

        def _recusar(self, motivo):
            try:  # diagnostico: o navegador do Dono pode estar mandando Host/Origin inesperados
                with (power.DATA / "web.log").open("a", encoding="utf-8") as f:
                    f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | RECUSADO {motivo} | {self.command} {self.path} | "
                            f"Host={self.headers.get('Host')} Origin={self.headers.get('Origin')} UA={str(self.headers.get('User-Agent'))[:60]}\n")
            except OSError:
                pass
            self._json({"erro": motivo}, 403)

        def _host_ok(self):
            # defesa contra DNS rebinding: so aceita acesso por 127.0.0.1/localhost na nossa porta
            if self.headers.get("Host") not in (f"127.0.0.1:{PORTA}", f"localhost:{PORTA}"):
                self._recusar("host negado")
                return False
            return True

        def do_GET(self):
            if not self._host_ok():
                return
            if self.path == "/api/status":
                return self._json(status(router))
            if self.path.split("?")[0] == "/api/falhas":      # onde o Jarvis mais falha, por tipo (clareza.resumo)
                from . import clareza
                return self._json(clareza.resumo())
            if self.path.split("?")[0] == "/falhas":
                pagina = (Path(__file__).parent / "ui" / "falhas.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(pagina)))
                self.end_headers()
                return self.wfile.write(pagina)
            if self.path == "/api/modulos":
                from . import modulos
                return self._json(modulos.estado())
            if self.path.startswith("/api/banco"):   # consulta local ao banco unificado (camada completa: so o PC alcanca esta porta)
                from urllib.parse import urlparse, parse_qs
                from . import banco
                q = parse_qs(urlparse(self.path).query)
                horas = float((q.get("horas") or [0])[0] or 0) or None
                texto, _ = banco.consultar((q.get("q") or [""])[0], "local", horas, n=int((q.get("n") or [12])[0]))
                return self._json({"resultado": texto})
            if self.path in ("/sala", "/sala.html"):       # sala de conversa Jarvis + A.L.M.A. (so o PC alcanca)
                pagina = (Path(__file__).parent / "ui" / "sala.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(pagina)))
                self.end_headers()
                self.wfile.write(pagina)
                return
            if self.path.startswith("/api/sala"):
                from urllib.parse import urlparse, parse_qs
                from . import sala
                q = parse_qs(urlparse(self.path).query)
                return self._json({"mensagens": sala.mensagens(int((q.get("depois") or [0])[0] or 0)), "estado": sala.estado()})
            if self.path == "/api/mudo":
                from . import mudo
                return self._json(mudo.estado())
            if self.path == "/api/painel":     # status dos bracos + historico de acoes (logs locais; so 127.0.0.1 alcanca)
                from . import painel
                return self._json({"bracos": painel.bracos(status(router)), "historico": painel.historico()})
            if self.path == "/vendor/three.min.js":       # Three.js local (offline), usado pelo escritorio 3D real
                js = (Path(__file__).parent / "ui" / "vendor" / "three.min.js").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript")
                self.send_header("Cache-Control", "max-age=86400")
                self.send_header("Content-Length", str(len(js)))
                self.end_headers()
                return self.wfile.write(js)
            if self.path.split("?")[0] == "/sauraki":       # escritorio virtual: 3D isometrico por padrao; ?plano=1 = versao 2D simples (so o PC alcanca)
                pagina = (Path(__file__).parent / "ui" / ("sauraki.html" if "plano=1" in self.path else "sauraki-real.html" if "real=1" in self.path else "sauraki3d.html")).read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(pagina)))
                self.end_headers()
                return self.wfile.write(pagina)
            if self.path.split("?")[0] in ("/painel", "/painel.html"):      # interface nova (estilo OpenClaw); so o PC e o tunel pareado alcancam
                pagina = (Path(__file__).parent / "ui" / "painel.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(pagina)))
                self.end_headers()
                return self.wfile.write(pagina)
            if self.path.startswith("/claw/fonts/") and self.path.endswith(".woff2"):      # fontes da interface (SIL OFL, copiadas do Control UI do OpenClaw)
                arq = (Path(__file__).parent / "ui" / "claw" / "fonts" / Path(self.path.split("?")[0]).name)
                if arq.is_file() and arq.parent.name == "fonts":
                    dados = arq.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "font/woff2")
                    self.send_header("Cache-Control", "public, max-age=86400")
                    self.send_header("Content-Length", str(len(dados)))
                    self.end_headers()
                    return self.wfile.write(dados)
                return self._json({"erro": "nao encontrado"}, 404)
            if self.path == "/api/painel2":    # dados agregados para o painel novo (so leitura, so locais)
                from . import painel_claw
                return self._json(painel_claw.dados())
            if self.path == "/api/wpp_direto":   # estado do WhatsApp sem Chrome (inclui o QR para parear)
                from . import wpp_direto
                return self._json(wpp_direto.status())
            if self.path.startswith("/api/par/link"):   # registro Aliado (par do LINK) <-> Braniac (so o PC: prefixo /api/par)
                from urllib.parse import urlparse, parse_qs
                from .link import integracao
                q = parse_qs(urlparse(self.path).query)
                return self._json({**integracao.resumo(), "mensagens": integracao.conversa(int((q.get("n") or [300])[0]), float((q.get("depois") or [0])[0]))})
            if self.path.startswith("/api/par/conversa"):   # registro Layla <-> Jarvis (so o PC)
                from urllib.parse import urlparse, parse_qs
                from . import elo_loja
                q = parse_qs(urlparse(self.path).query)
                return self._json({**elo_loja.resumo(), "mensagens": elo_loja.historico(int((q.get("n") or [300])[0]), float((q.get("depois") or [0])[0]))})
            if self.path == "/api/par":   # Braniac pareado (ex.: loja): so o PC; predios = quem esta respondendo agora
                from . import rede_jarvis
                return self._json({"info": rede_jarvis.par().info(), "predios": rede_jarvis.predios()})
            if self.path == "/par/painel" or self.path.startswith("/par/painel/"):   # tela principal do OUTRO Braniac (so leitura, so se ele liberou)
                from . import rede_jarvis
                caminho = self.path[len("/par/painel"):] or "/"
                try:
                    st, ct, corpo = rede_jarvis.par().painel_get(caminho)
                except Exception as e:
                    st, ct, corpo = 502, "text/plain; charset=utf-8", ("Braniac pareado fora do ar: " + str(e)[:80]).encode()
                if ct.startswith("text/html"):   # os links/fetch absolutos do painel dele passam a apontar para este proxy
                    ponte = b"<script>(function(){var P='/par/painel',f=window.fetch;window.fetch=function(u,o){if(typeof u==='string'&&u[0]==='/')u=P+u;return f.call(this,u,o)};var x=XMLHttpRequest.prototype.open;XMLHttpRequest.prototype.open=function(m,u){if(typeof u==='string'&&u[0]==='/')arguments[1]=P+u;return x.apply(this,arguments)}})()</script>"
                    corpo = ponte + corpo
                self.send_response(st if st in (200, 403, 404, 429, 502) else 502)
                self.send_header("Content-Type", ct)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                return self.wfile.write(corpo)
            if self.path in ("/pendencias", "/mapa"):   # painel de pendencias e o mapa mental delas (13/11)
                pagina = (Path(__file__).parent / "ui" / ("mapa.html" if self.path == "/mapa" else "pendencias.html")).read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(pagina)))
                self.end_headers()
                return self.wfile.write(pagina)
            if self.path == "/alma":     # painel "o que a Alma sabe" (ver, corrigir, apagar, pausar)
                pagina = (Path(__file__).parent / "ui" / "alma.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(pagina)))
                self.end_headers()
                return self.wfile.write(pagina)
            if self.path == "/api/alma/sabe":
                from . import alma_aprende
                return self._json({**alma_aprende.sabe(), "pendentes": alma_aprende.pendentes_rotulo()})
            if self.path == "/api/pendencias":
                from . import pendencias
                return self._json(pendencias.painel())
            if self.path == "/api/braincenter":    # painel do Brain Center (so numeros e estados; nenhum texto de memoria)
                from . import braincenter, sauraki
                try:
                    braincenter.avaliar(sauraki.snapshot(status(router))["agentes"])
                except Exception:
                    pass
                return self._json(braincenter.painel())
            if self.path.split("?")[0] == "/api/sauraki":   # retrato dos agentes montado SO com dados locais ja existentes (sem IA); ?demo=1 = sem texto real
                from . import sauraki
                snap = sauraki.snapshot(status(router))
                return self._json(sauraki.demo(snap) if "demo=1" in self.path else snap)
            if self.path.startswith("/api/tela?"):     # aba do Chrome do Braniac ao vivo (so o PC alcanca; dominios fixos)
                from urllib.parse import urlparse, parse_qs
                from . import tela_viva
                try:
                    return self._json(tela_viva.captura((parse_qs(urlparse(self.path).query).get("d") or [""])[0]))
                except tela_viva.TelaErro as e:
                    return self._json({"erro": str(e)}, 409)
                except Exception as e:
                    return self._json({"erro": f"falha na captura: {str(e)[:60]}"}, 500)
            if self.path == "/api/producao":      # banco do processo dos videos do Parceiro (auditoria); so o PC alcanca
                from .link import processo
                return self._json(processo.painel())
            if self.path == "/api/parceiro":         # Lupa: lote dos videos do Parceiro (etapas e pendencias); so o PC alcanca
                from .link import lote_parceiro
                d = lote_parceiro.ler()
                if isinstance(d.get("esteira"), dict):
                    d["esteira"]["slots"] = lote_parceiro.slots(d["esteira"])   # um quadrado por cidade (nome ao passar o mouse)
                return self._json(d)
            if self.path.split("?")[0] == "/parceiro":
                pagina = (Path(__file__).parent / "ui" / "parceiro.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(pagina)))
                self.end_headers()
                return self.wfile.write(pagina)
            if self.path.split("?")[0] == "/producao":
                pagina = (Path(__file__).parent / "ui" / "producao.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(pagina)))
                self.end_headers()
                return self.wfile.write(pagina)
            if self.path.split("?")[0] == "/api/municipios":   # cidades dos videos do Parceiro: ?cidade=X ou resumo
                from urllib.parse import urlparse, parse_qs
                from .link import municipios
                nome = (parse_qs(urlparse(self.path).query).get("cidade") or [""])[0]
                return self._json(municipios.cidade(nome) if nome else municipios.resumo())
            if self.path == "/api/termico":
                from . import termico
                return self._json(termico.atual())
            if self.path == "/api/agentes":     # conversa entre os agentes (barramento) + situacao de cada um (Compasso); so o PC alcanca
                from . import barramento, compasso
                return self._json({"conversa": barramento.historico(60), "agentes": compasso.painel_agentes()})
            if self.path == "/api/escuta-estado":
                return self._json(escuta.ESCUTA.estado_completo() if escuta.ESCUTA else {"estado": "parada", "nivel": 0, "ultimo": "", "historico": []})
            if self.path in ("/email", "/email.html"):      # passo a passo e formulario para conectar o Gmail (so leitura)
                pagina = (Path(__file__).parent / "ui" / "email.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(pagina)))
                self.end_headers()
                return self.wfile.write(pagina)
            if self.path == "/email/login":
                try:
                    destino = gmail.url_login()
                except gmail.GmailErro as e:
                    return self._json({"erro": str(e)}, 400)
                self.send_response(302)
                self.send_header("Location", destino)
                self.end_headers()
                return
            if self.path.startswith("/email/callback"):
                from urllib.parse import urlparse, parse_qs
                q = parse_qs(urlparse(self.path).query)
                try:
                    gmail.concluir_login((q.get("code") or [""])[0], (q.get("state") or [""])[0])
                    msg = "Gmail conectado ao Jarvis (somente leitura). Pode fechar esta janela."
                except Exception as e:
                    msg = "Não consegui conectar: " + str(e)
                corpo = f"<!doctype html><meta charset=utf-8><body style='font:18px system-ui;background:#05070d;color:#f4ead2;padding:40px'>{msg}</body>".encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                return self.wfile.write(corpo)
            if self.path == "/spotify/login":     # abre a tela de aprovacao do Spotify (uma vez)
                try:
                    destino = spotify.url_login()
                except spotify.SpotifyErro as e:
                    return self._json({"erro": str(e)}, 400)
                self.send_response(302)
                self.send_header("Location", destino)
                self.end_headers()
                return
            if self.path.startswith("/spotify/callback"):
                from urllib.parse import urlparse, parse_qs
                q = parse_qs(urlparse(self.path).query)
                try:
                    spotify.concluir_login((q.get("code") or [""])[0], (q.get("state") or [""])[0])
                    msg = "Spotify conectado ao Jarvis. Pode fechar esta janela."
                except Exception as e:
                    msg = "Não consegui conectar: " + str(e)
                corpo = f"<!doctype html><meta charset=utf-8><body style='font:18px system-ui;background:#05070d;color:#f4ead2;padding:40px'>{msg}</body>".encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                return self.wfile.write(corpo)
            if self.path.split("?")[0] in ("/hud", "/hud.html", "/hud-classico"):   # tela de voz (aba Jarvis do B.R.A.N.I.A.C 1); ?demo=1 simula estados; /hud-classico = visual antigo
                pag = (Path(__file__).parent / "ui" / ("hud.classico.html" if self.path.startswith("/hud-classico") else "hud.html")).read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(pag)))
                self.end_headers()
                return self.wfile.write(pag)
            if self.path in ("/vozes", "/vozes.html"):    # 16/11: todos os modelos de voz e as vozes de dentro de cada um; clicar toca a amostra e escolhe
                pagina = (Path(__file__).parent / "ui" / "vozes.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(pagina)))
                self.end_headers()
                return self.wfile.write(pagina)
            if self.path == "/api/vozes":
                from . import vozes_catalogo
                return self._json(vozes_catalogo.catalogo())
            if self.path == "/api/predio":   # 16/11: andares construidos do predio 3D (copia publica comeca com um)
                from . import andares
                return self._json(andares.estado())
            if self.path == "/api/habilidades-terceiros":   # 16/11: catalogo de habilidades de outros autores (baixa do GitHub deles)
                from . import habilidades_terceiros
                return self._json(habilidades_terceiros.status())
            if self.path in ("/voz", "/voz.html"):
                pagina = (Path(__file__).parent / "ui" / "voz.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(pagina)))
                self.end_headers()
                return self.wfile.write(pagina)
            if self.path == "/api/avisos":
                itens = AVISOS[:]
                del AVISOS[:len(itens)]
                return self._json({"avisos": itens})
            if self.path in ("/remoto", "/remoto/"):   # parear o celular (so no PC; o tunel nunca entrega /api/remoto*)
                pag = (Path(__file__).parent / "ui" / "remoto.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(pag)))
                self.end_headers()
                return self.wfile.write(pag)
            if self.path == "/api/remoto":
                from . import remoto
                return self._json(remoto.estado())
            if self.path in ("/b2", "/b2/", "/b2?antigo=1"):   # B.R.A.N.I.A.C 1 (a janela em Rust abre /b2); desde 28/10 o PAINEL NOVO e o layout principal, o antigo fica em /b2?antigo=1
                pag = (Path(__file__).parent / "ui" / ("b2.html" if self.path.endswith("antigo=1") else "painel.html")).read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(pag)))
                self.end_headers()
                return self.wfile.write(pag)
            if self.path == "/api/b2/estado":
                from . import skills as _sk
                return self._json({**b2.estado(), "skills": [{"nome": n, "descricao": d} for n, d, *_ in _sk.listar()], "status": status(router)})
            if self.path == "/api/b2/aparencia":
                return self._json(b2.aparencia())
            if self.path == "/api/b2/chaves":
                return self._json({"chaves": b2.chaves()})
            if self.path == "/api/b2/sinal":   # o app em Rust pergunta a cada 1 s (abre a aba do Jarvis quando ele e chamado por voz)
                return self._json({"aba": b2.ler_sinal()})
            if self.path == "/api/b2/contas":
                return self._json(b2.contas())
            if self.path == "/api/b2/relatorio":
                return self._json({"relatorio": b2.relatorio()})
            if self.path.startswith("/api/b2/conversa?id="):
                try:
                    return self._json({"mensagens": b2.mensagens(router.store, int(self.path.split("=", 1)[1]))})
                except ValueError:
                    return self._json({"erro": "id invalido"}, 400)
            if self.path in ("/", "/index.html"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")  # a interface nunca fica velha no navegador
                self.send_header("Content-Length", str(len(HTML)))
                self.end_headers()
                return self.wfile.write(HTML)
            self._json({"erro": "nao encontrado"}, 404)

        def do_POST(self):
            if not self._host_ok():
                return
            # bloqueia paginas de outros sites de acionar a API (CSRF)
            if self.headers.get("Origin") not in (None, f"http://127.0.0.1:{PORTA}", f"http://localhost:{PORTA}"):
                return self._recusar("origem negada")
            d = self._corpo()
            if self.path == "/api/predio/construir":
                from . import andares
                try:
                    return self._json(andares.construir(str(d.get("andar") or "")))
                except ValueError as e:
                    return self._json({"erro": str(e)}, 400)
            if self.path in ("/api/habilidades-terceiros/instalar", "/api/habilidades-terceiros/recusar"):
                from . import habilidades_terceiros as ht
                if self.path.endswith("/recusar"):
                    return self._json(ht.recusar())
                ids = [str(i) for i in (d.get("ids") or []) if isinstance(i, str)][:100]
                return self._json(ht.instalar(ids))
            if self.path.startswith("/api/vozes/"):    # 16/11: pagina /vozes (amostra falada, escolha, baixar voz do Piper); so o PC alcanca
                from . import vozes_catalogo as vc
                acao = self.path.rsplit("/", 1)[1]
                try:
                    if acao == "amostra":
                        wav, seg = vc.amostra(str(d.get("motor")), str(d.get("voz")), ajustes=d.get("ajustes") if isinstance(d.get("ajustes"), dict) else None)
                        self.send_response(200)
                        self.send_header("Content-Type", "audio/wav")
                        self.send_header("X-Segundos", str(seg))
                        self.send_header("Content-Length", str(len(wav)))
                        self.end_headers()
                        return self.wfile.write(wav)
                    if acao == "escolher":
                        ag_ = str(d.get("agente") or "jarvis")
                        esc_ = vc.escolher(str(d.get("motor")), str(d.get("voz")), ag_, int(d.get("posicao") or 1))
                        if int(d.get("posicao") or 1) != 1:   # reserva: nao mexe nos ajustes da primaria
                            return self._json({"ok": True, "escolha": esc_})
                        if isinstance(d.get("ajustes"), dict):    # combinacao pronta: voz + ajustes de uma vez
                            from . import vozes_agentes
                            esc_ = vozes_agentes.ajustar(ag_, d["ajustes"])
                        return self._json({"ok": True, "escolha": esc_})
                    if acao == "ajustar":
                        from . import vozes_agentes
                        return self._json({"ok": True, "escolha": vozes_agentes.ajustar(str(d.get("agente") or "jarvis"), d.get("ajustes") if isinstance(d.get("ajustes"), dict) else {})})
                    if acao == "tirar_reserva":
                        from . import vozes_agentes
                        return self._json({"ok": True, "escolha": vozes_agentes.tirar_reserva(str(d.get("agente") or "jarvis"), int(d.get("posicao") or 2))})
                    if acao == "limpar":
                        vc.limpar_escolha(str(d.get("agente") or "jarvis"))
                        return self._json({"ok": True})
                    if acao == "baixar":
                        return self._json({"ok": vc.baixar_piper(str(d.get("voz")))})
                except Exception as e:
                    return self._json({"erro": str(e)[:200]}, 400)
                return self._json({"erro": "acao desconhecida"}, 404)
            if self.path == "/api/producao/pausa":     # botao de pausa da producao (congela o render); so o PC alcanca
                from .link import processo
                return self._json(processo.pausar(bool(d.get("ligar"))))
            if self.path in tuple("/api/municipios/" + a for a in ("reservar", "concluir", "aprovar", "reprovar", "postar", "liberar")):   # checklist: Claudes deste PC reservam a cidade antes de produzir
                from .link import municipios
                return self._json(getattr(municipios, self.path.rsplit("/", 1)[1])(str(d.get("cidade") or ""), str(d.get("quem") or "braniac")[:40], str(d.get("nota") or "")))
            if self.path == "/api/par/link/falar":    # o Dono escreve ao par do LINK (Aliado) pelo Terreo; so o PC (prefixo /api/par)
                from .link import integracao
                ok, detalhe = integracao.falar_dono(d.get("texto"))
                return self._json({"ok": ok, "detalhe": detalhe})
            if self.path == "/api/alma/acao":     # so o PC alcanca (host/origem ja conferidos acima)
                from . import alma_aprende
                a = d.get("acao")
                if a == "rotular":
                    return self._json({"ok": alma_aprende.rotular(int(d.get("id") or 0), d.get("tema") or "")})
                if a == "apagar":
                    return self._json({"ok": alma_aprende.apagar(str(d.get("escopo") or ""))})
                if a == "consentimento":
                    return self._json(alma_aprende.definir_consentimento(**{k: v for k, v in d.items() if k != "acao"}))
                return self._json({"erro": "acao desconhecida"}, 400)
            if self.path == "/api/wpp_direto/iniciar":
                from . import wpp_direto
                return self._json({"ok": wpp_direto.iniciar()})
            if self.path == "/api/chat":
                texto = (d.get("texto") or "").strip()
                if not texto:
                    return self._json({"erro": "mensagem vazia"}, 400)
                # mesmo cerebro do Telegram: reconhece WhatsApp/Claude/ligar-desligar antes de ir pra IA
                resp, da_ia = jarvis.processar(router, texto, d.get("conv") or "web", AVISOS.append)
                return self._json({"resposta": resp, "provedor": "Jarvis" if not da_ia else "IA"})
            if self.path == "/api/celular/fala":      # trecho de fala vindo do app do celular (chamar o Jarvis pelo nome)
                from . import celular
                return self._json(celular.fala(router, d.get("audio") or ""))
            if self.path in ("/api/remoto/ligar", "/api/remoto/desligar", "/api/remoto/codigo"):
                from . import remoto
                if self.path.endswith("ligar") and not self.path.endswith("desligar"):
                    return self._json(remoto.ligar(True))
                if self.path.endswith("desligar"):
                    return self._json(remoto.desligar(True))
                remoto.novo_codigo()       # codigo novo: o celular pareado antes deixa de conectar
                return self._json(remoto.estado())
            if self.path in ("/api/b2/anexo", "/api/b2/audio"):    # foto (lida pelo Ollama) e audio (Whisper) enviados em pedacos
                try:
                    dados = b2.juntar_partes(d)
                    if dados is None:
                        return self._json({"ok": True, "faltam": True})
                    if self.path.endswith("anexo"):
                        return self._json(b2.salvar_anexo(dados))
                    return self._json({"texto": b2.transcrever_audio(dados)})
                except (ValueError, KeyError, TypeError) as e:
                    return self._json({"erro": str(e)}, 400)
            if self.path == "/api/b2/chave":    # cola a chave de uma IA gratis (a resposta nunca traz o valor)
                try:
                    return self._json(b2.salvar_chave(d.get("env", ""), d.get("valor", ""), router))
                except ValueError as e:
                    return self._json({"erro": str(e)}, 400)
            if self.path == "/api/b2/acao":
                try:
                    return self._json(b2.acao(d))
                except (ValueError, KeyError, TypeError) as e:
                    return self._json({"erro": str(e)}, 400)
            if self.path == "/api/b2/chat":    # conversa de PROJETO: historico proprio ('b2:<id>') + instrucoes do projeto
                texto = (d.get("texto") or "").strip()
                try:
                    cid = int(d.get("conversa"))
                    extra = b2.contexto_da_conversa(cid)
                except (TypeError, ValueError):
                    return self._json({"erro": "conversa invalida"}, 400)
                if not texto:
                    return self._json({"erro": "mensagem vazia"}, 400)
                from . import delegacao
                liberados = b2.modulos_da_conversa(cid)
                if liberados is not None and not d.get("sem_sugestao"):   # 04/11: pergunta de um modulo nao liberado -> avisa e pergunta antes
                    novos = [n for n in delegacao._escolher(texto, 9) if n not in liberados] if delegacao.eh_consulta(texto) else []
                    if novos:
                        return self._json({"sugere_modulo": novos})
                b2.titulo_inicial(cid, texto)
                delegacao.LIMITE.perm = None if liberados is None else set(liberados)
                try:
                    resp, da_ia = jarvis.processar(router, texto, f"b2:{cid}", AVISOS.append, extra=extra)
                finally:
                    delegacao.LIMITE.perm = None
                return self._json({"resposta": resp, "provedor": "Jarvis" if not da_ia else "IA"})
            if self.path == "/api/tela-acao":   # clique/tecla do Dono na aba mostrada no escritorio
                from . import tela_viva
                try:
                    return self._json({"ok": tela_viva.acao(d.get("d", ""), d.get("tipo"), d.get("x"), d.get("y"), d.get("texto"), d.get("tecla"))})
                except tela_viva.TelaErro as e:
                    return self._json({"erro": str(e)}, 409)
                except Exception as e:
                    return self._json({"erro": f"falha: {str(e)[:60]}"}, 500)
            if self.path == "/api/power":
                power.ligar() if d.get("ligado") else power.desligar("manual", modelo_local=router.cfg.get("modelo_local", "qwen2.5:3b"))
                return self._json(status(router))
            if self.path == "/api/autonomia":  # SO aqui (PC local) se arma a autonomia remota; o Telegram nao alcanca isto
                try:
                    power.armar(int(d.get("minutos", 0)))
                except (TypeError, ValueError):
                    return self._json({"erro": "minutos invalido"}, 400)
                return self._json(status(router))
            if self.path == "/api/modulos":  # SO aqui (PC local) se escolhem os modulos
                from . import modulos
                modulos.definir(d.get("ativos") or [])
                return self._json(modulos.estado())
            if self.path == "/api/atendimento-auto":  # SO aqui (PC local) se LIGA o atendimento automatico
                vigia.ligar() if d.get("ligado") else vigia.desligar()
                return self._json(status(router))
            if self.path == "/api/airbnb-auto":  # SO aqui (PC local) se LIGA o atendimento automatico do Airbnb
                try:
                    airbnb_vigia.ligar() if d.get("ligado") else airbnb_vigia.desligar()
                except RuntimeError as exc:   # modulo Airbnb desligado
                    return self._json({"erro": str(exc)}, 400)
                return self._json(status(router))
            if self.path == "/api/escuta":  # liga/desliga o microfone do Jarvis (so aqui, no PC local)
                if escuta.ESCUTA is None:
                    escuta.iniciar(router, ligada=False)
                escuta.ESCUTA.ligar() if d.get("ligado") else escuta.ESCUTA.desligar()
                return self._json(status(router))
            if self.path == "/api/email":     # guarda o cliente OAuth do Google (so no PC local); sem campos = so devolve o estado
                if d.get("client_id") or d.get("client_secret"):
                    try:
                        gmail.definir_cliente(d.get("client_id", ""), d.get("client_secret", ""))
                    except gmail.GmailErro as e:
                        return self._json({"erro": str(e)}, 400)
                return self._json(gmail.estado())
            if self.path == "/api/spotify":  # guarda o Client ID do app do Spotify (so no PC local)
                spotify.definir_client_id(d.get("client_id", ""))
                return self._json(spotify.estado())
            if self.path == "/api/orbe":  # minimizar (so o orbe flutuante) ou voltar para a interface completa
                from . import orbe
                if d.get("acao") == "mini":
                    escuta.definir_modo_tela("mini")
                    orbe.iniciar_processo()
                elif d.get("acao") == "abrir":      # duplo clique no orbe: abre a interface maximizada, sem mudar o modo (o orbe fica)
                    if escuta.ESCUTA:
                        threading.Thread(target=escuta.ESCUTA._abrir_janela, kwargs={"forcar": True}, daemon=True).start()
                else:
                    escuta.definir_modo_tela("completo")
                    if escuta.ESCUTA:
                        threading.Thread(target=escuta.ESCUTA._abrir_janela, kwargs={"forcar": True}, daemon=True).start()
                return self._json({"modo": escuta.modo_tela()})
            if self.path == "/api/escuta-acao":  # botoes da tela de voz (so no PC local)
                if escuta.ESCUTA is None:
                    escuta.iniciar(router, ligada=False)
                a = d.get("acao")
                if a == "ligar":
                    escuta.ESCUTA.ligar()
                elif a == "desligar":
                    escuta.ESCUTA.desligar()
                elif a == "acordar" and escuta.ESCUTA.estado == "dormindo":
                    threading.Thread(target=escuta.ESCUTA.acordar, daemon=True).start()
                elif a == "descansar" and escuta.ESCUTA.estado == "acordado":
                    threading.Thread(target=escuta.ESCUTA.descansar, daemon=True).start()
                elif a == "frase" and str(d.get("texto") or "").strip():   # 15/11: frase escrita como se fosse falada (teste das frases sem microfone)
                    threading.Thread(target=escuta.ESCUTA.tratar_frase, args=(str(d["texto"])[:300],), daemon=True).start()
                return self._json(escuta.ESCUTA.estado_completo())
            if self.path == "/api/sala":     # controle da sala: enviar, pausar, silenciar, iniciar conversa, propor melhoria (nada altera codigo)
                from . import sala
                return self._json(sala.acao(d))
            if self.path == "/api/mudo":    # MUDO: o Jarvis para de falar em voz alta (texto continua); corta a fala na hora
                from . import mudo
                a = d.get("acao")
                if a == "mutar":
                    try:
                        minutos = int(d.get("minutos") or 0) or None    # 10, 60 ou vazio (= ate desmutar)
                    except (TypeError, ValueError):
                        return self._json({"erro": "minutos invalido"}, 400)
                    if escuta.ESCUTA:
                        escuta.ESCUTA.aplicar_mudo("mutar", minutos)
                    else:
                        mudo.mutar(minutos)
                elif a == "desmutar":
                    escuta.ESCUTA.aplicar_mudo("desmutar") if escuta.ESCUTA else mudo.desmutar()
                if "whatsapp_dono" in d:
                    mudo.definir_whatsapp_dono(d.get("whatsapp_dono"))
                return self._json(mudo.estado())
            if self.path == "/api/panico":   # BOTAO DE PANICO: so desarma/desliga (direcao segura)
                from . import painel
                r = painel.panico("web")
                r["status"] = status(router)
                return self._json(r)
            if self.path == "/api/modo-jogo":
                power.set_modo_jogo_auto(d.get("auto"))
                return self._json(status(router))
            self._json({"erro": "nao encontrado"}, 404)
    return H


def status(router):
    e = power.estado()
    provs = []
    for p in router.cfg["cadeia"]:
        ok, motivo = router.disponivel(p)
        provs.append({"nome": p["nome"], "tipo": p["tipo"], "ok": ok, "motivo": motivo,
                      "hoje": router.store.uso_hoje(p["nome"])})
    return {"ligado": not e["pausado"], "motivo": e["motivo"], "jogo": e["jogo"],
            "modo_jogo_auto": e.get("modo_jogo_auto", True), "provedores": provs,
            "autonomia": {"armada": power.armada(), "restante_min": power.armada_restante_min(), "indefinida": power.armada_indefinida()},
            "atendimento_auto": vigia.resumo(), "airbnb_auto": airbnb_vigia.resumo(),
            "escuta_voz": (escuta.ESCUTA.resumo() if escuta.ESCUTA else {"estado": "parada"}),
            "spotify": spotify.estado(), "email": gmail.estado(), "mudo": _mudo_estado()}


def _mudo_estado():
    from . import mudo
    return mudo.estado()


class _ServidorUnico(ThreadingHTTPServer):
    # 16/11: no Windows o SO_REUSEADDR deixa DOIS Braniac na mesma porta (dois reinicios juntos -> tudo em dobro, WhatsApp travado)
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def main():
    router = Router()
    try:    # ocupa a porta ANTES de ligar as rotinas: se ja tem um Braniac rodando, este sai sem ligar nada
        srv = _ServidorUnico(("127.0.0.1", PORTA), montar_handler(router))
    except OSError as e:
        print(f"Braniac ja esta rodando na porta {PORTA} ({e}); esta copia nao sobe.", flush=True)
        return
    power.vigiar(lambda: router.cfg)
    from . import dono, telegram_bot, vigia
    telegram_bot.iniciar(router)
    dono.iniciar(router)
    from . import rotina
    try:
        from . import assuntos
        assuntos.iniciar_curador()   # assuntos/agentes: sincroniza o banco principal e cura (vence 'so hoje', acha contradicao) a cada 30 min
    except Exception as e:
        print('assuntos nao iniciou:', e, flush=True)
    try:
        from . import organiza_claude
        organiza_claude.iniciar()   # barra lateral do Claude organizada sem IA, a cada 5 min, quando o app está fechado
    except Exception as e:
        print('organiza_claude nao iniciou:', e, flush=True)
    rotina.iniciar()   # 6h: bom dia + relatorio + e-mails; de hora em hora: e-mail de trabalho com prazo (Dono e Parceira)
    try:
        from . import rede_jarvis
        rede_jarvis.iniciar(router)   # rede de Braniacs: so abre porta no IP da Radmin
    except Exception as e:
        print('rede de Braniacs nao iniciou:', e, flush=True)
    try:
        from .link import integracao as _link
        _link.retomar(router)   # BRANIAC LINK: so liga se ja existe par; conecta sozinho ao convite aceito
    except Exception as e:
        print('link nao iniciou:', e, flush=True)
    try:
        from . import painel_rede
        painel_rede.iniciar()   # painel da esteira do Parceiro no celular (rede local, so leitura, porta 8772)
    except Exception as e:
        print('painel da rede local nao iniciou:', e, flush=True)
    try:
        from . import portal
        portal.iniciar()      # portal remoto (login Dono + dispositivos + tunel), porta 8780; so sobe se a senha ja foi definida
    except Exception as e:
        print('portal remoto nao iniciou:', e, flush=True)
    try:
        from . import remoto
        remoto.retomar()     # acesso remoto: so volta sozinho se o Dono deixou ligado
    except Exception as e:
        print('acesso remoto nao iniciou:', e, flush=True)
    from . import alma_cuida
    from . import contexto as _cx, funil, rotina as _rt, vaquinha
    vaquinha.iniciar(lambda m: funil.envolver(_rt._enviar)(_cx.contato("dono") or "Eu", m))   # Vaquinha: so age depois de configurar(); le o banco a cada 5 min
    try:
        from . import taxa_sepique
        taxa_sepique.iniciar(lambda m: _rt._enviar(_cx.contato("dono") or "Eu", m))   # API que confirma a taxa de 3% do app Se Pique (Cofre confere o extrato)
    except Exception as e:
        print('taxa do Se Pique nao iniciou:', e, flush=True)
    alma_cuida.iniciar(router)  # Alma: recebe do Jarvis o que o Dono diz, aprende o jeito dele e cuida (proativa, com tetos)
    grupo_ia.iniciar(router)  # grupo "IA & Tech": so observa; fala so se marcarem o numero do Dono
    airbnb_vigia.iniciar(router)  # Airbnb: so age se ligado na interface local
    from . import airbnb_escalada
    airbnb_escalada.iniciar()      # avisa Mae -> Dono -> Parceira quando o Airbnb fica sem resposta (so le)
    vigia.iniciar(router)  # atendimento automatico (so age se ligado na interface local)  # responde sempre o Dono no WhatsApp ('Eu'), sem precisar de comando
    from . import escuta
    escuta.iniciar(router, ligada=router.cfg.get("escuta_voz", True))  # 'Jarvis, ta acordado?' -> conversa por voz no notebook
    if escuta.modo_tela() == "mini":    # modo minimizado: o orbe flutuante fica sempre na tela
        from . import orbe
        orbe.iniciar_processo()
    print(f"Braniac/Jarvis em http://127.0.0.1:{PORTA}  (Ctrl+C para parar)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
