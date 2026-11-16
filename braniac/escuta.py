# -*- coding: utf-8 -*-
"""Escuta por voz no notebook: o Dono fala 'Jarvis, tá acordado?' e o Jarvis acorda, ouve, responde falando e continua ouvindo
ate ouvir 'pode descansar, Jarvis'.

Tudo LOCAL: o microfone e processado aqui (VAD por energia + Whisper local). Dormindo, so transcreve trechos de fala curtos para procurar a
frase de acordar (nada e gravado em disco nem enviado a lugar nenhum); acordado, o que ele diz vai ao cerebro do Jarvis (origem 'web' = local)
e a resposta sai nos alto-falantes. Enquanto o Jarvis fala, o microfone e ignorado (sem eco).
Estados: parada (nao escuta) | dormindo (espera 'Jarvis, ta acordado') | acordado (conversa por voz)."""
import difflib, queue, re, tempfile, threading, time, unicodedata, wave
from datetime import datetime
from pathlib import Path
from . import mostrar, mudo, power
from .store import DATA

LOG = DATA / "escuta.log"
TAXA = 16000
BLOCO = 1600                     # 100 ms
MIN_FALA_BLOCOS = 4              # < 0,4 s de fala: ruido
SILENCIO_FIM_BLOCOS = 15         # 1,5 s de silencio encerra a frase (03/11: com 0,6 s ele cortava o Dono ao respirar e respondia frase pela metade)
MAX_FALA_BLOCOS = 250            # 25 s: corta
PRE_ROLL_BLOCOS = 3

# alucinacoes tipicas do Whisper com silencio/ruido: frases curtas soltas e creditos de legenda
CURTAS_LIXO = {"tchau", "obrigado", "obrigada", "ate a proxima", "ate mais", "tchau tchau", "valeu", "hum", "ah", "uh"}
LIXO_CONTIDO = ("legendas pela", "amara org", "inscreva se", "www ", "legenda")


def _norm(x):
    s = "".join(c for c in unicodedata.normalize("NFD", str(x).lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", s)).strip()


def _tem_jarvis(texto):
    """'Jarvis' com tolerancia ao que o Whisper costuma escrever (Jarves, Garvis, Charvis, Jarvi...)."""
    for t in _norm(texto).split():
        if t.startswith(("jarv", "garv", "charv", "xarv")) or difflib.SequenceMatcher(None, t, "jarvis").ratio() >= 0.72:
            return True
    return False


ACORDAR = re.compile(r"acord|desperta|ta ai|esta ai|voce esta ai|ta me ouvindo|esta me ouvindo|ta ouvindo|presente|bom dia|boa tarde|boa noite|oi|ola|ei|e ai")
ACORDAR_FORTE = re.compile(r"acord|desperta|ta ai|esta ai|ta me ouvindo|esta me ouvindo|ta ouvindo|"
                           r"por ai|ta na escuta|esta na escuta|ta ligado|esta ligado|ta online|cade voce|ta acordando")
# 15/11: so o chamado ('o Jarvis', 'oi Jarvis', 'fala Jarvis') tambem acorda, mas a frase inteira tem de ser o chamado ('o jarvis e legal' nao)
CHAMADO = re.compile(r"(o|oh|oi|ei|eh|ola|alo|e ai|fala|opa|hey) \S+")
DESCANSAR = re.compile(r"descans|pode dormir|vai dormir|dorme|pode parar de ouvir|chega por hoje")
# 16/11: 'quero falar com a Alma' -> o Jarvis sai de lado e a Alma assume a conversa por voz (voz dela); 'quero falar com o Jarvis' devolve
PEDE_TROCA = re.compile(r"\b(?:falar|conversar|fala|conversa) com\b|\b(?:chama|chame|passa|passe|volta|volte|cade)\b|\bdeixa\b.{0,12}\bfalar\b")
TEM_ALMA = re.compile(r"\b(?:alma|auma)\b")
ALMA_ENTRA = "Oi, meu bem. O Jarvis me passou a vez, tô aqui com você. Me conta."
JARVIS_VOLTA = "Estou de volta, senhor. Em que posso te ajudar?"


def quer_acordar(texto):
    n = _norm(texto)
    return _tem_jarvis(texto) and (bool(ACORDAR_FORTE.search(n)) or bool(CHAMADO.fullmatch(n)))


def quer_descansar(texto):
    """'pode descansar, Jarvis', tolerando o que o Whisper escreve (descassar, descancar, discansar...)."""
    n = _norm(texto)
    if DESCANSAR.search(n):
        return True
    return any(difflib.SequenceMatcher(None, t, "descansar").ratio() >= 0.78 or difflib.SequenceMatcher(None, t, "descansa").ratio() >= 0.8
               for t in n.split() if len(t) >= 6)


def _janela_voz():
    """Handle da janela 'Jarvis · Voz' (a tela de voz aberta no Chrome) ou None."""
    import ctypes
    from ctypes import wintypes as wt
    u = ctypes.windll.user32
    achadas = []

    def cb(h, _):
        if u.IsWindowVisible(h):
            n = u.GetWindowTextLengthW(h)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                u.GetWindowTextW(h, buf, n + 1)
                if buf.value.startswith("Jarvis · Voz"):
                    achadas.append(h)
        return True
    u.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)(cb), 0)
    return achadas[0] if achadas else None


def mostrar_janela(hwnd, maximizar=True):
    """Traz a tela de voz para a FRENTE (o Windows barra roubo de foco: o truque da tecla Alt libera) e, se pedido, MAXIMIZA."""
    import ctypes
    u = ctypes.windll.user32
    u.ShowWindow(hwnd, 3 if maximizar else 9)     # 3 = maximizar, 9 = restaurar (se estava minimizada)
    u.keybd_event(0x12, 0, 0, 0)                   # Alt para baixo/cima: permite SetForegroundWindow
    u.keybd_event(0x12, 0, 2, 0)
    u.BringWindowToTop(hwnd)
    u.SetForegroundWindow(hwnd)


ANIMACAO_FALA = 1.0   # intensidade (0 a 1) da animacao do orbe enquanto o Jarvis fala (o Dono queria a VOZ mais seria, nao o orbe mais calmo)
MODO_ARQ = DATA / "ui_voz.json"


def modo_tela():
    """'completo' (janela com o orbe grande e a conversa) ou 'mini' (so o orbe transparente flutuante). Fica salvo."""
    try:
        import json
        return "mini" if json.loads(MODO_ARQ.read_text(encoding="utf-8")).get("modo") == "mini" else "completo"
    except Exception:
        return "completo"


def definir_modo_tela(modo):
    import json
    DATA.mkdir(exist_ok=True)
    MODO_ARQ.write_text(json.dumps({"modo": "mini" if modo == "mini" else "completo"}), encoding="utf-8")


DEPURAR = True   # registra o que ouviu enquanto dorme (calibracao); mude para False depois de afinar


def dividir_em_frases(texto, minimo=70, maximo=260):
    """Quebra o texto em frases para falar em pipeline; junta as muito curtas e quebra as muito longas."""
    frases = [f.strip() for f in re.split(r"(?<=[.?!…])\s+", texto.strip()) if f.strip()]
    partes, atual = [], ""
    for f in frases:
        if atual and len(atual) + 1 + len(f) > maximo:
            partes.append(atual)
            atual = f
        else:
            atual = (atual + " " + f).strip()
        if len(atual) >= minimo:
            partes.append(atual)
            atual = ""
    if atual:
        partes.append(atual)
    return partes or [texto]


def envelope(wav_bytes, passo_s=0.05):
    """Envelope de volume (0..1 a cada passo_s) de um WAV, para animar a tela no ritmo da fala."""
    import io
    import numpy as np
    try:
        with wave.open(io.BytesIO(wav_bytes)) as w:
            taxa, canais = w.getframerate(), w.getnchannels()
            x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)
    except Exception:
        return []
    if canais > 1:
        x = x.reshape(-1, canais).mean(axis=1)
    n = max(1, int(taxa * passo_s))
    k = len(x) // n
    if k == 0:
        return []
    rms = np.sqrt((x[:k * n].reshape(k, n) ** 2).mean(axis=1))
    pico = float(rms.max()) or 1.0
    return [round(float(v) / pico, 3) for v in rms]


def _amplificar(pcm_bytes, alvo=0.7, ganho_max=40.0):
    """Microfone baixo: normaliza o trecho para pico ~0,7 (ganho limitado) antes do Whisper, que erra muito com audio fraco."""
    import numpy as np
    x = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
    if x.size == 0:
        return pcm_bytes
    pico = float(np.abs(x).max()) / 32768.0
    if pico < 1e-4:
        return pcm_bytes
    ganho = min(ganho_max, alvo / pico)
    return np.clip(x * ganho, -32768, 32767).astype(np.int16).tobytes()


def _duracao_wav(wav_bytes):
    import io
    try:
        with wave.open(io.BytesIO(wav_bytes)) as w:
            return w.getnframes() / float(w.getframerate() or 1)
    except Exception:
        return 0.0


def _tocar_interrompivel(wav, winsound):
    """Toca o WAV e devolve True se a fala foi CORTADA pelo mudo. Assincrono (arquivo temporario) para poder parar na hora;
    se o modo assincrono falhar, toca do jeito antigo (sincrono, sem corte)."""
    caminho = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav)
            caminho = f.name
        winsound.PlaySound(caminho, winsound.SND_FILENAME | winsound.SND_ASYNC)
        if mudo.CORTAR.wait(_duracao_wav(wav) + 0.15):
            winsound.PlaySound(None, 0)          # None = para o som que esta tocando
            return True
        return False
    except RuntimeError:
        winsound.PlaySound(wav, winsound.SND_MEMORY)
        return False
    finally:
        if caminho:
            try:
                Path(caminho).unlink()
            except OSError:
                pass


def _log(txt):
    DATA.mkdir(exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {txt}\n")


class Escuta:
    def __init__(self, router=None, falar=None, responder=None, transcrever=None, abrir=None):
        self.router = router
        self._abrir_ext = abrir            # injetavel: abre a janela do Jarvis ao acordar
        self.historico = []                # [('u'|'j'|'s', texto)] para a tela de voz
        self.estado = "parada"
        self.agente = "jarvis"             # quem conversa por voz agora: 'jarvis' ou 'alma' (16/11)
        self._falar_ext = falar            # injetaveis (testes)
        self._responder_ext = responder
        self._transcrever_ext = transcrever
        self._parar = threading.Event()
        self._thread = None
        self._falando_ate = 0.0
        self._links = []                   # links da ultima resposta, esperando 'aqui' ou 'no celular'
        self.ultimo = ""                   # ultima frase ouvida enquanto acordado (diagnostico)
        self.nivel = 0.0
        self.atividade = "idle"            # idle | ouvindo (voce falando) | pensando | falando (Jarvis) -- para a tela animada
        self._fala = None                  # {"ini": t0, "env": [0..1 a cada 50 ms]} da voz que esta tocando

    # ---------- maquina de estados (testavel sem microfone) ----------

    def tratar_frase(self, texto):
        """Recebe o texto de uma frase ouvida e age conforme o estado. Devolve o que o Jarvis falou (ou None)."""
        n = _norm(texto)
        if not n or len(n) < 2 or n in CURTAS_LIXO or any(a in n for a in LIXO_CONTIDO):
            return None
        cmd = mudo.comando(texto)
        if cmd and (self.estado == "acordado" or (self.estado == "dormindo" and _tem_jarvis(texto))):
            return self.aplicar_mudo(cmd)    # 'Jarvis, silencio' / 'cala a boca' / 'mudo' (e 'pode falar' para desmutar)
        if self.estado in ("dormindo", "acordado") and quer_acordar(texto):
            return self.acordar()   # tambem acordado: se a janela foi fechada, 'Jarvis, ta acordado?' reabre a tela e cumprimenta de novo
        if self.estado == "dormindo" and _tem_jarvis(texto) and mostrar.intencao(texto):
            self.estado = "acordado"      # 'Jarvis, como ta o NexoDev?' direto: acorda e ja mostra, sem o cumprimento
            _log("ACORDOU (pergunta de situacao)")
        if self.estado == "dormindo":
            if DEPURAR and re.search(r"\b(?:j|ch|g)[ae]r?v|\bjar", texto, re.I):
                # 14/10: so registra QUASE-acertos (algo parecido com 'Jarvis') -- antes gravava toda conversa da casa (12 mil linhas)
                _log(f"(dormindo) quase acordei: {texto[:60]!r}")
            return None
        if self.estado == "acordado":
            self.ultimo = texto
            self._anotar("u", texto)
            if quer_descansar(texto):
                return self.descansar()
            _log(f"OUVIU: {texto[:120]}")
            if PEDE_TROCA.search(n) and len(n.split()) <= 12:     # frase curta de troca; frase longa que cita a Alma segue como conversa
                para = "alma" if TEM_ALMA.search(n) else ("jarvis" if _tem_jarvis(texto) else "")
                if para and para != self.agente:
                    self.agente = para
                    _log(f"TROCA: agora fala {para}")
                    self._anotar("s", "A Alma assumiu a conversa." if para == "alma" else "O Jarvis voltou.")
                    return self._falar_anotado(ALMA_ENTRA if para == "alma" else JARVIS_VOLTA)
            if self.agente == "alma":        # com a Alma nao ha telas nem ferramentas: so conversa, no modelo local
                return self._falar_anotado(self._alma(texto))
            if self._links:                 # respondendo 'abro aqui ou mando no celular?'
                como, urls = mostrar.escolha(texto), self._links
                self._links = []
                if como:
                    return self._falar_anotado(mostrar.entregar_link(urls, como))
            resp = mostrar.mostrar(texto)     # 'como ta a esteira/o NexoDev?': abre a tela dentro do Braniac e fala o estado
            if resp:
                return self._falar_anotado(resp)
            resp = self._responder(texto)
            if not resp:
                return None
            urls = mostrar.links(resp)
            if urls:                         # link: nao abre sozinho; pergunta onde (o Chrome ja vive cheio de abas)
                self._links = urls
                resp = (re.sub(r"https?://\S+", "", resp).strip() + " " + mostrar.PERGUNTA_LINK).strip()
            return self._falar_anotado(resp)
        return None

    def _falar_anotado(self, resp):
        self._anotar("j", resp)
        return self._dizer(resp)

    SAUDACAO = "Estou acordado, senhor. Em que posso te ajudar?"
    DESPEDIDA = "Tudo bem, vou descansar. Me chama quando precisar."

    def aplicar_mudo(self, cmd, minutos=None):
        """Muta (corta a fala na hora; o texto continua aparecendo) ou desmuta. Nao fala nada ao mutar."""
        if cmd == "mutar":
            mudo.mutar(minutos)
            _log(f"MUDO ligado ({minutos or 'ate desmutar'} min)")
            self._anotar("s", "🔇 Mudo: não vou falar em voz alta (o texto continua aqui). Diga “pode falar” ou aperte M para desmutar.")
            return None
        mudo.desmutar()
        _log("MUDO desligado")
        self._anotar("s", "🔊 Som de volta: voltei a falar.")
        return None

    def _anotar(self, papel, texto):
        self.historico.append((papel, texto))
        del self.historico[:-60]

    def acordar(self):
        """Acorda (pela frase ou pelo botao): abre a janela do Jarvis e cumprimenta falando."""
        self.estado = "acordado"
        self.agente = "jarvis"       # 'Jarvis, ta acordado?' sempre traz o Jarvis
        _log("ACORDOU")
        self._anotar("s", "Acordei: estou ouvindo.")
        # 'Jarvis, ta acordado?' abre a tela INTEIRA (maximizada, na frente), mesmo com o orbe minimizado (Dono, 05/10)
        threading.Thread(target=self._abrir_janela, kwargs={"forcar": True}, daemon=True).start()
        self._anotar("j", self.SAUDACAO)
        return self._dizer(self.SAUDACAO)

    def descansar(self):
        self.estado = "dormindo"
        self.agente = "jarvis"
        _log("DORMIU")
        self._anotar("s", "Voltei a dormir.")
        r = self._dizer(self.DESPEDIDA)
        self._minimizar_janela()      # mandou descansar: a tela vai para a barra de tarefas ('Jarvis, ta acordado?' traz de volta, maximizada)
        return r

    def _minimizar_janela(self):
        try:
            import ctypes
            hwnd = _janela_voz()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 6)    # 6 = SW_MINIMIZE
        except Exception as e:
            _log(f"ERRO ao minimizar a janela: {e!r}")

    def _abrir_janela(self, forcar=False):
        """Abre a tela de voz (janela do Chrome sem barra) se ela ainda nao estiver aberta (a pagina avisa que esta aberta consultando o estado).
        No modo MINI o que aparece e so o orbe flutuante (janelinha transparente); 'forcar' abre a interface completa mesmo assim."""
        try:
            if self._abrir_ext:
                return self._abrir_ext()
            if forcar:   # 24/10: chamado por voz, o Jarvis abre na aba dele DENTRO do B.R.A.N.I.A.C 1 (programa em Rust), nao no Chrome
                from . import b2
                if b2.abrir_no_app("jarvis"):
                    return
            if modo_tela() == "mini" and not forcar:
                from . import orbe
                return orbe.iniciar_processo()
            hwnd = _janela_voz()
            if hwnd:                                    # ja existe (talvez minimizada ou escondida atras de outras): traz para a frente
                return mostrar_janela(hwnd, maximizar=forcar)
            if time.time() - ULTIMA_CONSULTA[0] < 4 and not forcar:
                return
            import subprocess, webbrowser
            url = "http://127.0.0.1:8765/voz"
            for chrome in (r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"):
                if Path(chrome).exists():
                    args = [chrome, f"--app={url}", "--window-size=520,780", "--window-position=60,60"]
                    subprocess.Popen(args + (["--start-maximized"] if forcar else []))
                    for _ in range(40):                 # espera a janela aparecer e a traz para a frente (maximizada se foi duplo clique)
                        time.sleep(0.25)
                        h = _janela_voz()
                        if h:
                            mostrar_janela(h, maximizar=forcar)
                            break
                    return
            webbrowser.open(url)
        except Exception as e:
            _log(f"ERRO ao abrir a janela: {e!r}")

    def _alma(self, texto):
        """Resposta da Alma na conversa por voz: modelo LOCAL com a checagem anti-invencao (alma_mente.compor); o que ele diz entra na memoria dela."""
        from . import alma_mente
        try:
            est = alma_mente.registrar(texto)
            resp = alma_mente.compor("dono", texto, est["estado"])
        except Exception as e:
            _log(f"ERRO da Alma ao responder: {e!r}")
            resp = "Tô aqui com você, meu bem. Pode repetir pra mim?"
        return re.sub(r"[^\w\s.,!?;:()'\"-]", "", resp).strip()    # emoji nao se fala

    def _responder(self, texto):
        if self._responder_ext:
            return self._responder_ext(texto)
        from . import jarvis
        try:
            resp, _ = jarvis.processar(self.router, texto, "voz", None, origem="web")
        except Exception as e:
            _log(f"ERRO ao responder: {e!r}")
            return "Tive um problema pra responder isso agora. Pode repetir?"
        return resp

    def _dizer(self, texto):
        texto = re.sub(r"https?://\S+", "", texto or "").strip()
        if len(texto) > 700:
            texto = texto[:700].rsplit(" ", 1)[0] + "... o resto eu mando por escrito."
        if mudo.ativo():      # MUDO: nao fala em voz alta; o texto ja esta no historico da tela
            return texto
        mudo.CORTAR.clear()
        self._falando_ate = time.time() + 600   # enquanto toca, o microfone e ignorado
        self.atividade = "pensando"
        try:
            if self._falar_ext:
                self._falar_ext(texto)
            else:
                self._tocar_em_partes(texto)
        except Exception as e:
            _log(f"ERRO ao falar: {e!r}")
        finally:
            self._fala = None
            self.atividade = "idle"
            self._falando_ate = time.time() + 0.7   # cauda: o eco do alto-falante some
        return texto

    def _tocar_em_partes(self, texto):
        """Fala por FRASES em pipeline: a 1a frase comeca a tocar assim que fica pronta enquanto as seguintes sao sintetizadas (menos espera)."""
        from . import voz
        import winsound
        fila = queue.Queue()

        def produzir():
            for parte in dividir_em_frases(texto):
                if mudo.CORTAR.is_set():
                    break
                try:
                    fila.put(voz.falar_wav(parte, rapido=True, agente=self.agente))
                except Exception as e:
                    _log(f"ERRO ao sintetizar: {e!r}")
            fila.put(None)
        threading.Thread(target=produzir, daemon=True).start()
        while True:
            wav = fila.get()
            if wav is None:
                break
            if mudo.CORTAR.is_set():
                break
            self._fala = {"ini": time.time() + 0.05, "env": envelope(wav)}   # a tela anima o orbe no ritmo da voz
            self.atividade = "falando"
            cortada = _tocar_interrompivel(wav, winsound)
            self._fala = None
            self.atividade = "pensando"
            if cortada:
                _log("fala CORTADA (mudo)")
                break

    def nivel_fala(self):
        """Volume (0 a 1) da voz do Jarvis AGORA, lido do envelope do audio que esta tocando."""
        f = self._fala
        if not f:
            return 0.0
        i = int((time.time() - f["ini"]) / 0.05)
        return f["env"][i] if 0 <= i < len(f["env"]) else 0.0

    # ---------- captura ----------

    def ligar(self):
        if self._thread and self._thread.is_alive():
            return "ja estava ligada"
        self._parar.clear()
        self.estado = "dormindo"
        self._thread = threading.Thread(target=self._loop, daemon=True, name="braniac-escuta")
        self._thread.start()
        if not self._transcrever_ext:       # carrega o Whisper (GPU) ja, para a 1a frase nao esperar
            def _pre():
                try:
                    from . import voz
                    voz.preaquecer_whisper()
                    _log(f"Whisper pronto ({voz.MOTOR_WHISPER})")
                except Exception as e:
                    _log(f"ERRO ao preaquecer o Whisper: {e!r}")
            threading.Thread(target=_pre, daemon=True).start()
        _log("LIGADA (dormindo)")
        return "ligada"

    def desligar(self):
        self._parar.set()
        self.estado = "parada"
        _log("DESLIGADA")
        return "desligada"

    def resumo(self):
        return {"estado": self.estado, "nivel": round(self.nivel, 4), "ultimo": self.ultimo[:80]}

    def estado_completo(self):
        ULTIMA_CONSULTA[0] = time.time()    # a tela de voz consulta isto varias vezes por segundo: sabemos que ela esta aberta
        d = self.resumo()
        d["historico"] = list(self.historico[-40:])
        d["atividade"] = self.atividade
        d["agente"] = self.agente
        d["entrada"] = round(min(1.0, self.nivel * 55.0), 3)     # microfone do notebook e baixo: escala para 0..1
        d["fala"] = round(self.nivel_fala() * ANIMACAO_FALA, 3)
        d["mudo"] = mudo.estado()
        d["tela"] = mostrar.tela_atual()   # 'me mostra': a pagina troca para esta tela (uma vez por id)
        return d

    def _transcrever(self, pcm_bytes):
        if self._transcrever_ext:
            return self._transcrever_ext(pcm_bytes)
        from . import voz
        pcm_bytes = _amplificar(pcm_bytes)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            caminho = f.name
        try:
            with wave.open(caminho, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(TAXA)
                w.writeframes(pcm_bytes)
            return voz.transcrever(caminho, rapido=True)
        finally:
            try:
                Path(caminho).unlink()
            except OSError:
                pass

    def _loop(self):
        import numpy as np
        import sounddevice as sd
        fila = queue.Queue(maxsize=400)

        def cb(indata, frames, tinfo, status):
            try:
                fila.put_nowait(bytes(indata))
            except queue.Full:
                pass

        recentes = []          # rms dos ultimos blocos (ruido ambiente)
        pre = []
        fala, silencio, seg = 0, 0, []
        try:
            stream = sd.InputStream(samplerate=TAXA, channels=1, dtype="int16", blocksize=BLOCO, callback=cb)
            stream.start()
        except Exception as e:
            _log(f"ERRO ao abrir o microfone: {e!r}")
            self.estado = "parada"
            return
        _log("microfone aberto")
        try:
            while not self._parar.is_set():
                if power.pausado():            # modo jogo/desligado: nao escuta
                    time.sleep(1)
                    while not fila.empty():
                        fila.get_nowait()
                    continue
                try:
                    bruto = fila.get(timeout=0.5)
                except queue.Empty:
                    continue
                x = np.frombuffer(bruto, dtype=np.int16).astype(np.float32) / 32768.0
                rms = float(np.sqrt((x ** 2).mean()))
                self.nivel = rms
                if time.time() < self._falando_ate:     # o Jarvis esta falando (ou acabou de falar)
                    fala, silencio, seg, pre = 0, 0, [], []
                    continue
                recentes.append(rms)
                del recentes[:-150]
                ruido = float(np.percentile(recentes, 20)) if len(recentes) >= 20 else 0.0008   # (era 0,01: ficava SURDO por ~2 s depois de cada resposta)
                limiar = max(0.0035, ruido * 3.0)   # o microfone do notebook e MUITO baixo (voz normal ~0,01 de RMS): piso baixo + ruido adaptativo
                if rms > limiar:
                    fala += 1
                    silencio = 0
                    if fala >= 2 and not seg:
                        seg = list(pre)
                    if seg or fala >= 2:
                        seg.append(bruto)
                else:
                    if seg:
                        silencio += 1
                        seg.append(bruto)
                    else:
                        fala = 0
                        pre.append(bruto)
                        del pre[:-PRE_ROLL_BLOCOS]
                if seg:
                    self.atividade = "ouvindo"          # voce esta falando: a tela reage ao seu volume
                elif self.atividade == "ouvindo":
                    self.atividade = "idle"
                fim = seg and (silencio >= SILENCIO_FIM_BLOCOS or len(seg) >= MAX_FALA_BLOCOS)
                if fim:
                    pcm = b"".join(seg)
                    falados = len(seg) - silencio
                    fala, silencio, seg, pre = 0, 0, [], []
                    if falados < MIN_FALA_BLOCOS:
                        self.atividade = "idle"
                        continue
                    self.atividade = "pensando"         # transcrevendo/decidindo a resposta
                    try:
                        texto = self._transcrever(pcm)
                    except Exception as e:
                        _log(f"ERRO ao transcrever: {e!r}")
                        self.atividade = "idle"
                        continue
                    if texto:
                        self.tratar_frase(texto)
                    # enquanto o Jarvis falava, o microfone captou a PROPRIA voz dele e ela ficou na fila: descarta, senao ele se ouve e responde a si mesmo
                    while not fila.empty():
                        try:
                            fila.get_nowait()
                        except queue.Empty:
                            break
                    if self.atividade == "pensando":
                        self.atividade = "idle"
        finally:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
            _log("microfone fechado")


ESCUTA = None
ULTIMA_CONSULTA = [0.0]   # quando a tela de voz consultou o estado pela ultima vez


def iniciar(router, ligada=True):
    global ESCUTA
    ESCUTA = Escuta(router)
    if ligada:
        ESCUTA.ligar()
    return ESCUTA
