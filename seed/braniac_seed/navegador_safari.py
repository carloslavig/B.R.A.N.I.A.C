# -*- coding: utf-8 -*-
"""Navegador do assistente no SAFARI (macOS), sem precisar de Chromium. O Safari nao tem o protocolo de depuracao (CDP) do Chrome/Edge, entao aqui o
controle e por AppleScript (`do JavaScript` em abas) e por eventos de JavaScript na pagina.

Como funciona e o que muda em relacao ao Chromium:
- O assistente SO mexe nas abas que ELE criou (registradas em _donas): nunca adota nem toca numa aba da pessoa. Atencao: no Safari com Grupos de Abas,
  a janela nova COMPARTILHA as abas das outras janelas; entao a aba do assistente e achada de novo pelo endereco quando o indice muda.
- E o Safari de verdade: os logins sao os mesmos que a pessoa ja usa (nao existe perfil separado por script no Safari).
- Exige UMA configuracao da pessoa: Safari > Ajustes > Desenvolvedor > 'Permitir JavaScript de Eventos da Apple' (e o macOS pedir para controlar o Safari).
- Cliques e digitacao sao eventos de JavaScript (nao 'confiaveis' como os do teclado real): funcionam na maioria dos sites, mas um site pode ignora-los.
O texto do AppleScript e sempre fixo; tudo que varia (URLs, JavaScript, indices) vai como ARGUMENTO, nunca dentro do script (nada de injecao)."""
import json, os, subprocess, tempfile, threading, time

from . import navegador

PASSOS_ATIVAR = ("No Safari: Safari › Ajustes › Avançado › marque 'Mostrar recursos para desenvolvedores web'; depois Ajustes › Desenvolvedor › marque "
                 "'Permitir JavaScript de Eventos da Apple' (o Safari pode pedir sua senha). Depois tente de novo.")
MARCA_ERRO = "\x01ERRO:"
LIMITE_ARGV = 150_000            # acima disso o JavaScript vai por arquivo temporario (argumentos de linha de comando tem limite)
_estado = {"wid": None}
_donas = {}          # chave -> {'dominio', 'url', 'temp'}: as abas criadas por este programa
_lock = threading.RLock()


def _traduzir(stderr):
    e = (stderr or "").strip()
    if "Allow JavaScript from Apple Events" in e or "JavaScript from Apple Events" in e or "Permitir JavaScript" in e:
        raise navegador.NavegadorErro("O Safari ainda não deixa o assistente rodar JavaScript. " + PASSOS_ATIVAR)
    if "-1743" in e or "not authorized" in e.lower() or "não está autorizado" in e.lower():
        raise navegador.NavegadorErro("O macOS bloqueou o controle do Safari. Libere em Ajustes do Sistema › Privacidade e Segurança › Automação "
                                      "(marque o Safari para o programa que está rodando o BRANIAC) e tente de novo.")
    raise navegador.NavegadorErro("Erro ao controlar o Safari: " + e[:240])


def _osa(script, *args, timeout=40):
    try:
        r = subprocess.run(["osascript", "-", *[str(a) for a in args]], input=script, capture_output=True, text=True, timeout=timeout, encoding="utf-8")
    except subprocess.TimeoutExpired:
        raise navegador.NavegadorErro("O Safari não respondeu a tempo (pode haver um aviso do macOS esperando a sua resposta).")
    except OSError as e:
        raise navegador.NavegadorErro(f"Não consegui falar com o Safari: {e}")
    if r.returncode != 0:
        _traduzir(r.stderr)
    return r.stdout.rstrip("\n")


S_ABRIR = """on run argv
	set u to item 1 of argv
	set TB to (ASCII character 9)
	tell application "Safari"
		-- 1) preferencia: nova ABA numa janela NORMAL ja aberta (as privadas nao expoem abas ao AppleScript: contam 0)
		repeat with w in windows
			try
				if (count of tabs of w) > 0 then
					make new tab at end of tabs of w with properties {URL:u}
					return ((id of w) as string) & TB & ((count of tabs of w) as string)
				end if
			end try
		end repeat
		-- 2) nenhuma janela normal: abre uma e procura a aba pelo endereco
		make new document with properties {URL:u}
		repeat 24 times
			delay 0.25
			repeat with w in windows
				try
					repeat with i from 1 to (count of tabs of w)
						if (URL of tab i of w) starts with u then return ((id of w) as string) & TB & (i as string)
					end repeat
				end try
			end repeat
		end repeat
		return ""
	end tell
end run"""

S_ABAS = """on run argv
	set wid to (item 1 of argv) as integer
	set TB to (ASCII character 9)
	tell application "Safari"
		try
			set w to window id wid
		on error
			return ""
		end try
		set out to ""
		repeat with i from 1 to (count of tabs of w)
			set t to tab i of w
			set u to ""
			set n to ""
			try
				set u to URL of t
			end try
			try
				set n to name of t
			end try
			if u is missing value then set u to ""
			if n is missing value then set n to ""
			set out to out & i & TB & u & TB & n & linefeed
		end repeat
		return out
	end tell
end run"""

S_ACAO = """on run argv
	set acao to item 1 of argv
	set wid to (item 2 of argv) as integer
	tell application "Safari"
		set w to window id wid
		if acao is "nova" then
			make new tab at end of tabs of w with properties {URL:(item 3 of argv)}
			return (count of tabs of w) as string
		else if acao is "selecionar" then
			set current tab of w to tab ((item 3 of argv) as integer) of w
		else if acao is "fechar" then
			close tab ((item 3 of argv) as integer) of w
		else if acao is "navegar" then
			set URL of tab ((item 3 of argv) as integer) of w to (item 4 of argv)
		else if acao is "mostrar" then
			set index of w to 1
			activate
		end if
		return "ok"
	end tell
end run"""

S_JS = """on run argv
	set wid to (item 1 of argv) as integer
	set ti to (item 2 of argv) as integer
	set js to item 3 of argv
	tell application "Safari" to return do JavaScript js in tab ti of window id wid
end run"""

S_JS_ARQ = """on run argv
	set wid to (item 1 of argv) as integer
	set ti to (item 2 of argv) as integer
	set js to read (POSIX file (item 3 of argv)) as «class utf8»
	tell application "Safari" to return do JavaScript js in tab ti of window id wid
end run"""


def _linhas(wid):
    """[(indice, url, titulo)] das abas visiveis para o AppleScript naquela janela (vazio se a janela sumiu ou e privada)."""
    out = []
    for linha in _osa(S_ABAS, wid).splitlines():
        p = linha.split("\t", 2)
        if len(p) == 3 and p[0].isdigit():
            out.append((int(p[0]), p[1], p[2]))
    return out


def _criar(url, chave, dominio, temp=False):
    """Abre `url` numa aba NOVA que passa a ser do assistente. A aba e achada pelo endereco marcado com um sufixo unico (#braniac-...), em qualquer
    janela do Safari; nenhuma janela e criada, minimizada ou fechada pelo assistente."""
    with _lock:
        wid = _estado["wid"]
        if wid is not None and _linhas(wid):
            n = _osa(S_ACAO, "nova", wid, url)
            idx = int(n)
        else:
            marcado = url if "#" in url else f"{url}#braniac-{time.time_ns()}"
            r = _osa(S_ABRIR, marcado)
            if "\t" not in r:
                raise navegador.NavegadorErro("O Safari não mostrou a aba que o assistente abriu. Se as suas janelas do Safari são privadas, o assistente "
                                              "não consegue controlá-las: abra uma janela normal do Safari e tente de novo.")
            w, idx = (int(x) for x in r.split("\t"))
            _estado["wid"] = w
        _donas[chave] = {"dominio": dominio, "url": url, "temp": temp, "indice": idx}
        return _resolver(chave)


def _resolver(chave):
    """{'id': 'janela:indice', 'url', 'title'} atual da aba do assistente, ou None se ela nao existe mais. Acha de novo pelo endereco se o indice mudou."""
    d, wid = _donas.get(chave), _estado["wid"]
    if not d or wid is None:
        return None
    abas_ = _linhas(wid)
    ref = d.get("indice")
    if ref and ref <= len(abas_) and d["dominio"] in abas_[ref - 1][1]:
        i = ref
    else:
        cand = [t for t in abas_ if d["dominio"] in t[1]]
        if not cand:
            return None
        i = cand[-1][0]               # a do assistente foi aberta depois das da pessoa: e a mais ao fim
    d["indice"] = i
    return {"id": f"{wid}:{i}", "url": abas_[i - 1][1], "title": abas_[i - 1][2], "type": "page", "chave": chave}


def rodando():
    """True se o assistente ainda tem alguma aba aberta no Safari."""
    try:
        return any(_resolver(c) for c in list(_donas))
    except navegador.NavegadorErro:
        return False


def iniciar(url="about:blank"):
    if not rodando():
        _criar(url, "base", url if url != "about:blank" else "about:blank")


def abas():
    """[{id, title, url, type}] SO das abas criadas pelo assistente (nunca as da pessoa)."""
    out = []
    for c, d in list(_donas.items()):
        if d["temp"]:
            continue
        a = _resolver(c)
        if a:
            out.append(a)
        else:
            _donas.pop(c, None)
    return out


def aba_de(dominio):
    return next((a for a in abas() if dominio and dominio in a["url"]), None)


def _indice(alvo):
    return int(alvo["id"].split(":")[1])


def abrir_aba(url):
    """Traz para a frente a aba do assistente para o site; se ainda nao tem uma, cria (nunca usa uma aba que a pessoa abriu)."""
    dom = url.split("/")[2]
    with _lock:
        a = aba_de(dom)
        if not a:
            a = _criar(url, dom, dom)
        _osa(S_ACAO, "selecionar", _estado["wid"], _indice(a))
        return a


def nova_aba(url):
    """Aba nova, temporaria, so para ler uma pagina (pesquisa). Devolve {'id', 'url'}; feche com fechar_aba."""
    chave = f"temp{time.time_ns()}"
    dom = url.split("/")[2] if "://" in url else url[:30]      # nunca vazio: '' casaria com QUALQUER aba, inclusive as da pessoa
    return _criar(url, chave, dom, temp=True)


def fechar_aba(id_):
    try:
        wid, idx = id_.split(":")
        _osa(S_ACAO, "fechar", wid, idx)
        for c, d in list(_donas.items()):
            if d["temp"] and d.get("indice") == int(idx):
                _donas.pop(c, None)
    except Exception:
        pass


def mostrar():
    if _estado["wid"] is not None and rodando():
        _osa(S_ACAO, "mostrar", _estado["wid"])


def esconder():
    """No Safari nao ha janela propria para esconder (as abas do assistente ficam entre as da pessoa): nada a fazer."""
    return None


def encerrar():
    """Fecha as abas que o assistente criou (nunca as da pessoa nem as janelas)."""
    with _lock:
        for c in list(_donas):
            a = _resolver(c)
            if a:
                fechar_aba(a["id"])
        _donas.clear()
        _estado["wid"] = None


# ---------- a "aba" com a mesma interface do adapter CDP (ias_web._AbaCDP) ----------
class Aba:
    tipo = "safari"

    def __init__(self, alvo):
        self.id = alvo["id"]
        self.wid, self.idx = (int(x) for x in alvo["id"].split(":"))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def close(self):
        pass

    def js(self, expr):
        """Avalia `expr` como programa (como o Runtime.evaluate do CDP) e devolve o valor ja convertido (bool, numero, texto, lista, None)."""
        codigo = ("(function(){try{var v=(0,eval)(" + json.dumps(expr) + ");return v===undefined?'null':JSON.stringify(v)}"
                  "catch(e){return '" + MARCA_ERRO + "'+e}})()")
        if len(codigo) > LIMITE_ARGV:
            with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
                f.write(codigo)
            try:
                bruto = _osa(S_JS_ARQ, self.wid, self.idx, f.name, timeout=120)
            finally:
                os.unlink(f.name)
        else:
            bruto = _osa(S_JS, self.wid, self.idx, codigo)
        if bruto.startswith(MARCA_ERRO):
            raise navegador.NavegadorErro("JavaScript na página: " + bruto[len(MARCA_ERRO):][:200])
        return json.loads(bruto) if bruto and bruto != "missing value" else None

    def navegar(self, url):
        _osa(S_ACAO, "navegar", self.wid, self.idx, url)

    def ativar(self):
        _osa(S_ACAO, "selecionar", self.wid, self.idx)

    def inserir_texto(self, texto):
        """Digita no elemento em foco (contenteditable, textarea ou input) pelo comando de edicao do navegador."""
        ok = self.js("(function(t){var el=document.activeElement; if(!el) return false;"
                     " while(el.shadowRoot && el.shadowRoot.activeElement) el=el.shadowRoot.activeElement;"
                     " return document.execCommand('insertText', false, t)})(" + json.dumps(texto) + ")")
        if not ok:
            raise navegador.NavegadorErro("não consegui digitar na página (nenhum campo em foco)")

    def enter(self):
        self.js("(function(){var el=document.activeElement||document.body;"
                " ['keydown','keypress','keyup'].forEach(function(tp){el.dispatchEvent(new KeyboardEvent(tp,"
                "{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true,cancelable:true}))}); return true})()")

    def clicar(self, x, y, pausa=0.0):
        """Clique por eventos de mouse no elemento que esta naquele ponto da janela (mesmas coordenadas do getBoundingClientRect)."""
        if pausa:
            time.sleep(pausa)
        ok = self.js("(function(x,y){var el=document.elementFromPoint(x,y); if(!el) return false;"
                     " var o={bubbles:true,cancelable:true,clientX:x,clientY:y,view:window,button:0};"
                     " ['pointerdown','mousedown','pointerup','mouseup'].forEach(function(tp){"
                     "el.dispatchEvent(new (tp.indexOf('pointer')===0&&window.PointerEvent?PointerEvent:MouseEvent)(tp,o))}); el.click(); return true})(%s,%s)" % (json.dumps(x), json.dumps(y)))
        if not ok:
            raise navegador.NavegadorErro("não achei nada para clicar naquele ponto")

    def anexar_arquivo(self, caminho, seletor, mime="application/octet-stream", limite_mb=15):
        """Coloca um arquivo num <input type=file> da pagina (sem janela de seletor): le o arquivo e o entrega como File pelo DataTransfer."""
        import base64
        from pathlib import Path
        p = Path(caminho)
        if p.stat().st_size > limite_mb * 1048576:
            raise navegador.NavegadorErro(f"No Safari o envio de arquivo vai até {limite_mb} MB (o arquivo precisa ir embutido no script).")
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        ok = self.js("(function(b64,nome,mime,sel){var inp=document.querySelector(sel); if(!inp) return false;"
                     " var bin=atob(b64), u=new Uint8Array(bin.length); for(var i=0;i<bin.length;i++) u[i]=bin.charCodeAt(i);"
                     " var dt=new DataTransfer(); dt.items.add(new File([u],nome,{type:mime})); inp.files=dt.files;"
                     " inp.dispatchEvent(new Event('change',{bubbles:true})); return true})(%s,%s,%s,%s)"
                     % (json.dumps(b64), json.dumps(p.name), json.dumps(mime), json.dumps(seletor)))
        if not ok:
            raise navegador.NavegadorErro("não achei o campo de arquivo da página")
