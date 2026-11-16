# -*- coding: utf-8 -*-
"""Roteador: online gratis -> Ollama local -> Claude (so em ultimo caso)."""
import json, os, re, time
from pathlib import Path
from . import contexto, latencia, power
from .providers import CHAMADORES, CHAMADORES_TOOLS, ProviderError
from .store import Store

RAIZ = Path(__file__).parent

# Conversa com dado sensivel NUNCA vai para a camada gratuita online (ela pode treinar com os dados).
SENSIVEL = re.compile(
    r"\bpix\b|cart[aã]o|senha|\bcvv\b|\bcpf\b|\bcnpj\b|ag[eê]ncia|conta\s+(banc|corrente)|"
    r"c[oó]digo\s+de\s+(verifica|seguran)|token|\b\d{4}[ .-]?\d{4}[ .-]?\d{4}[ .-]?\d{4}\b|"
    r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b|passaporte|\brg\b", re.I)


def chamada_em_texto(texto, nomes_validos=None):
    """Alguns modelos (principalmente os gratuitos/locais) escrevem a chamada da ferramenta COMO TEXTO, ex.: {"tool": "resumo_whatsapp", "arguments": {...}},
    em vez de usar o recurso de ferramentas. Isso nao pode virar resposta ao Dono: devolve (nome, args) para executar, ou None."""
    t = (texto or "").strip()
    m = re.match(r"^```(?:json)?\s*([\[{].*[\]}])\s*```$", t, re.S) or re.match(r"^([\[{].*[\]}])$", t, re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(1))
    except ValueError:
        return None
    if isinstance(d, list):      # varias chamadas escritas como texto: executa a primeira (o laco chama de novo se faltar)
        d = next((x for x in d if isinstance(x, dict)), None)
    if not isinstance(d, dict):
        return None
    nome = d.get("tool") or d.get("name") or d.get("function") or d.get("tool_name")
    if isinstance(nome, dict):
        nome = nome.get("name")
    args = d.get("arguments") or d.get("parameters") or d.get("args") or {}
    if not isinstance(nome, str) or not isinstance(args, dict):
        return None
    if nomes_validos is not None and nome not in nomes_validos:
        return None
    return nome, args


# DADO REAL (nao o assunto): numero de cartao, CPF, senha/codigo dito com valor, agencia/conta com numero. Serve so para o Jarvis NAO repetir nem
# pedir o dado; NUNCA para deixar de responder (decisao do Dono, 06/10: no WhatsApp dele nao existe assunto sensivel que impeca a resposta).
DADO_REAL = re.compile(r"\b\d{4}[ .-]?\d{4}[ .-]?\d{4}[ .-]?\d{4}\b|\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b|"
                       r"\b(?:senha|cvv|token|c[oó]digo\s+de\s+(?:verifica\w+|seguran\w+))\b\s*(?:[ée]|:|=)\s*\S{3,}|ag[eê]ncia\s*\d|conta\s*(?:corrente\s*)?\d", re.I)
PEDE_DADO = re.compile(r"\b(?:me\s+)?(?:mande|manda|envie|envia|passe|passa|informe|informa|digite|digita)\b[^.!?\n]{0,30}"
                       r"\b(?:cart[aã]o|senha|cvv|cpf|c[oó]digo|token|dados\s+banc\w+)\b", re.I)


def tem_dado_real(texto):
    return bool(DADO_REAL.search(texto or "") or PEDE_DADO.search(texto or ""))


# B.R.A.N.I.A.C 1 (24/10/2026): o Dono pediu que o Jarvis nao invente; fatos so do banco local/dossie/ferramentas
from . import assinatura
REGRA_TRATAMENTO = ("\n\nTRATAMENTO (obrigatorio, decisao do Dono em 16/11/2026): ao falar COM o Dono, chame-o SEMPRE de 'Senhor' ou de 'senhor', com respeito; "
                    "nunca 'Dono' seco, nunca apelido, nunca 'chefe'. Ao falar DELE com outras pessoas, 'o Dono'.")
REGRA_FATOS = ("\n\nREGRA DE FATOS (obrigatoria): sobre pessoas, combinados, precos, datas, negocios e o que alguem disse, use SO o que esta "
               "abaixo (banco/dossie) ou o que uma ferramenta devolver (consultar_banco, consultar_lei...). Se nao estiver la, diga "
               "'nao tenho isso registrado' e ofereca procurar. Nunca complete com suposicao nem invente nome, numero, link ou data. "
               "OPINIAO ('o que acha de X') nao e fato: havendo fatos acima, opine em 1a pessoa e de forma pessoal; sem nenhum, tente consultar_banco e so entao admita que nao conhece. "
               "QUALIDADE: responda a pergunta ATUAL (o historico anexado e so apoio); nao recuse sem tentar outro caminho; nao pergunte o obvio; erro apontado pelo Dono: assuma em 1 frase e corrija (nunca 'falei com o agente X'); so diga 'enviei/respondi' depois da ferramenta confirmar; 'chegou?' sem como checar = 'nao consigo confirmar'; 'qual a mensagem de X?' = leia a caixa e mostre; 'escolha o melhor...' = decida pelo contexto; texto colado nao e desabafo; 'ok' = so leitura; pedido de CRIAR arquivo/documento (rotina, lista, carta): ESCOLHA nome e conteudo voce mesmo (agenda, banco, bom senso), FACA com a ferramenta e so depois conte o que fez; so pergunte se faltar algo que NINGUEM no sistema sabe; "
               "so diga que fez quando a ferramenta confirmar; nao cole fichas internas; nao repita aviso que ele ja resolveu; sem 'Entendi, voce...'.")


class TodosFalharam(Exception):
    pass


class Desligado(Exception):
    pass


def carregar_env(path=None):
    """Chaves no .env ficam criptografadas (DPAPI, 14/10); aqui sao abertas so na memoria do processo."""
    from . import segredos
    for k, v in segredos.ler_env(path or RAIZ / ".env").items():
        os.environ.setdefault(k, v)


def _ferramentas_enxutas(tools, maximo=140):
    """Mesmas ferramentas e parametros (nada some), mas descricoes curtas: a 1a frase de cada uma, sem descricao de parametro."""
    out = []
    for t in tools:
        f = t["function"]
        desc = re.split(r"(?<=[.:])\s", f.get("description", ""), maxsplit=1)[0][:maximo]
        params = json.loads(json.dumps(f.get("parameters", {})))
        for prop in (params.get("properties") or {}).values():
            prop.pop("description", None)
        out.append({"type": "function", "function": {"name": f["name"], "description": desc, "parameters": params}})
    return out


def _historico_enxuto(msgs, anteriores=4):
    """O turno atual inteiro (da ultima fala do usuario em diante, com as chamadas de ferramenta) + poucas falas antes dele, so texto."""
    ult = max((i for i, m in enumerate(msgs) if m.get("role") == "user"), default=0)
    antes = [m for m in msgs[:ult] if m.get("role") in ("user", "assistant") and not m.get("tool_calls") and m.get("content")]
    return [{**m, "content": m["content"][:600]} for m in antes[-anteriores:]] + msgs[ult:]



def resposta_e_json_de_ferramenta(texto):
    """True para '{"name": "x", "arguments": {...}}' (ou lista disso) escrito como resposta de conversa."""
    t = (texto or "").strip()
    return bool(re.match(r'^[\[{]\s*\{?\s*"(?:name|tool|function)"\s*:', t)) and '"arguments"' in t[:300] or t.startswith('{"name"') and '"arguments"' in t


# ---------- 16/11: travas da resposta final (analise do revisor: 236 reprovadas; numero inventado, resultado cru e resposta vazia eram os erros repetidos) ----------
CURTAS_OK = {"sim", "nao", "não", "ok", "oi", "ola", "olá"}
NUMERO = re.compile(r"\d[\d.,]*\d|\d")
FALHAS_SEGUIDAS, FORA_DA_FILA_S = 8, 24 * 3600      # provedor online que falhou 8 vezes seguidas sai da fila por 24 h (depois ganha UMA nova chance)


def resposta_crua(t):
    """Pura. Resposta que nao pode ir ao Dono: vazia/sem sentido ('ia') ou o resultado da ferramenta despejado como veio."""
    t = (t or "").strip()
    if "RESULTADO DE FERRAMENTA" in t or t.startswith("ERRO na ferramenta"):
        return True
    limpo = re.sub(r"[\W_]", "", t.lower())
    return len(limpo) < 4 and limpo not in CURTAS_OK and not limpo.isdigit()


def _inteiro(n):
    return n.replace(".", "").split(",")[0]       # '1.600,00' e '1600' sao o mesmo numero


def numeros_inventados(resposta, base):
    """Pura. Numeros (2+ digitos) que a resposta cita e NAO aparecem em `base` (ferramentas + conversa + contexto). Data e hora de agora valem."""
    agora = time.localtime()
    ok = ({_inteiro(n) for n in NUMERO.findall(base or "")} | {str(x) for x in (agora.tm_year, agora.tm_mday, agora.tm_mon, agora.tm_hour, agora.tm_min)}
          | {f"{agora.tm_mday:02d}", f"{agora.tm_mon:02d}", f"{agora.tm_min:02d}"})
    so_digitos = re.sub(r"[.,\s]", "", base or "")
    fora = []
    for n in NUMERO.findall(resposta or ""):
        i = _inteiro(n)
        if len(i) >= 2 and i not in ok and i.lstrip("0") not in ok and re.sub(r"[.,]", "", n) not in so_digitos and n not in fora:
            fora.append(n)
    return fora


def sem_frases_com(resposta, numeros):
    """Pura. Tira as frases que citam os numeros inventados; se nao sobrar nada, diz que nao tem o numero (em vez de chutar)."""
    frases = [f for f in re.split(r"(?<=[.!?])\s+", (resposta or "").strip()) if not any(n in f for n in numeros)]
    return " ".join(frases).strip() or "Não tenho esse número confirmado agora, senhor. Quer que eu confira?"


def _claudinho():
    """Regras que o Claudinho (gerente) ensinou a partir dos erros reais do Jarvis."""
    try:
        from . import claudinho
        g = claudinho.guia()
        return ("\n\nREGRAS DO CLAUDINHO (gerente do Braniac; obedeca, vieram de erros reais seus):\n" + g) if g else ""
    except Exception:
        return ""


def _voz():
    """Guia de voz do Dono (bloco da Alma): faz o Jarvis escrever e responder no jeito dele."""
    try:
        from . import voz_do_dono
        g = voz_do_dono.guia()
        from . import alma_aprende
        from . import personalidade
        return (("\n\nCOMO O DONO FALA (responda a ele no mesmo tom e, ao redigir mensagens em nome dele, escreva como ele escreveria):\n" + g) if g else "") + alma_aprende.dica_tom() + personalidade.bloco()
    except Exception:
        return ""


class Router:
    def __init__(self, cfg=None, store=None, chamadores=None, chamadores_tools=None, checar_pausa=None):
        if store is None:
            carregar_env()  # testes injetam store e nao devem ler o .env real
        # testes injetam store/chamadores falsos: ai nao consultamos o estado real do PC
        self.checar_pausa = (store is None and chamadores is None) if checar_pausa is None else checar_pausa
        self.cfg = cfg or json.loads((RAIZ / "providers.json").read_text(encoding="utf-8-sig"))
        self._min = {}       # chamadas do ultimo minuto por provedor (limite por minuto dos planos gratis)
        if cfg is None:
            from . import gratis
            gratis.estender(self.cfg)   # FreeLLMAPI: modelos gratis extras dos provedores com chave no .env
        self.store = store or Store()
        self.chamadores = chamadores or CHAMADORES
        self.chamadores_tools = chamadores_tools or CHAMADORES_TOOLS
        self.lat = {}        # latencia media (s) de cada provedor, aprendida nas respostas (ajusta a espera do hedge)
        self.lat_ms = latencia.carregar()   # ms das ultimas 50 chamadas certas de cada provedor (data/latencia.jsonl): a mediana ordena a fila
        self._pk = {}        # cache curto do pacote do banco por camada
        self.falhas = latencia.falhas_seguidas()    # {provedor: [falhas seguidas, hora da ultima]}: quem so falha sai da fila (16/11: 60% das chamadas falhavam)

    def _chave(self, p):
        return os.environ.get(p.get("chave_env", ""), "").strip()

    def disponivel(self, p):
        """(ok, motivo). Online sem chave e ignorado; Claude respeita o teto diario."""
        if p["tipo"] == "online" and not self._chave(p):
            return False, "sem chave"
        if p["tipo"] == "claude" and self.store.uso_hoje("claude") >= self.cfg.get("claude_max_por_dia", 20):
            return False, "teto diario do Claude atingido"
        if p.get("limite_dia") and self.store.uso_hoje(p["nome"]) >= int(p["limite_dia"] * 0.9):
            return False, "limite diario do plano gratis"
        if p.get("limite_min") and self._chamadas_min(p["nome"]) >= p["limite_min"]:
            return False, "limite por minuto do plano gratis"
        n, quando = self.falhas.get(p["nome"], (0, 0))
        if p["tipo"] == "online" and n >= FALHAS_SEGUIDAS and time.time() - quando < FORA_DA_FILA_S:
            return False, f"fora da fila por 24 h ({n} falhas seguidas)"
        espera = self.store.cooldown(p["nome"])
        if espera > 0:
            return False, f"em descanso ({int(espera)}s): {self.store.erro(p['nome'])}"
        return True, ""

    def _chamadas_min(self, nome):
        agora = time.time()
        self._min[nome] = [t for t in self._min.get(nome, []) if agora - t < 60]
        return len(self._min[nome])

    def cadeia_para(self, sensivel):
        return [p for p in self.cfg["cadeia"] if not (sensivel and p["tipo"] == "online")]

    # ---------- roteamento mesclado: o provedor certo para cada pedido (economiza cota gratis e responde mais rapido) ----------

    def _ordenar(self, cadeia, texto="", tools=False):
        """Pedido curto/simples -> modelos RAPIDOS primeiro; pedido longo, com ferramentas ou que exige raciocinio -> modelos FORTES primeiro.
        Dentro de cada classe, passa na frente quem responde mais rapido e foi menos usado hoje (a cota gratis se espalha entre os provedores
        em vez de queimar sempre o mesmo). Ollama e Claude continuam no fim. Sem o bloco 'roteamento' no providers.json, a ordem e a do arquivo."""
        cfg = self.cfg.get("roteamento")
        if not cfg or not cfg.get("ativo"):
            return cadeia
        online = [p for p in cadeia if p["tipo"] == "online"]
        resto = [p for p in cadeia if p["tipo"] != "online"]
        simples = (not tools) and len(texto) <= cfg.get("max_simples", 220) and not re.search(cfg.get("palavras_fortes", r"$^"), texto, re.I)
        pref = "rapido" if simples else "forte"

        def custo(p):
            uso = self.store.uso_hoje(p["nome"])
            med = latencia.mediana_s(self.lat_ms, p["nome"])
            return max(0.3, med if med is not None else self.lat.get(p["nome"], 0.3)) * (1 + uso / float(p.get("limite_dia", cfg.get("limite_dia", 500))))   # provedor ainda nao medido entra na roda
        mesma = sorted((p for p in online if p.get("classe", "forte") == pref), key=custo)
        outra = sorted((p for p in online if p.get("classe", "forte") != pref), key=custo)
        return mesma + outra + resto

    def _aprender_latencia(self, nome, seg):
        ant = self.lat.get(nome)
        self.lat[nome] = seg if ant is None else 0.7 * ant + 0.3 * seg

    def _hedge(self, p):
        """Quanto esperar o provedor atual antes de iniciar o proximo em paralelo: proporcional ao tempo normal dele (menos chamadas
        duplicadas = menos cota gratis gasta)."""
        if not (self.cfg.get("roteamento") or {}).get("ativo"):
            return 2.5
        return min(6.0, max(2.0, 2.0 * self.lat.get(p["nome"], 1.2)))

    # ---------- banco unificado: toda IA le o mesmo contexto antes de responder ----------

    def _msgs_para(self, p, msgs, texto, compacto=False):
        if not self.checar_pausa:
            return msgs
        from . import banco
        camada = banco.camada_do_provedor(p["tipo"])
        texto = texto.split("\n\n[Conversa recente no WhatsApp:")[0].strip() or texto     # 06/11: o contexto anexado citava a Layla e puxava a ficha dela para a fala do Dono
        if len(texto.split()) < 7:     # 04/11: fala curta ('e o preco?', 'e esse projeto?') nao tem palavra para achar nada: junta as 2 falas anteriores dele na busca
            ant = [m["content"][:200] for m in msgs[:-1] if m.get("role") == "user" and isinstance(m.get("content"), str)][-2:]
            texto = (" ".join(ant) + " " + texto).strip() if ant else texto
        chave = (camada, texto, compacto)
        agora = time.time()
        hit = self._pk.get(chave)
        if not hit or agora - hit[0] > 20:
            hit = (agora, banco.pacote(texto, p["tipo"], 1300 if compacto else 3200))
            self._pk = {k: v for k, v in self._pk.items() if agora - v[0] < 20}
            self._pk[chave] = hit
        return [{**msgs[0], "content": msgs[0]["content"] + hit[1]}] + msgs[1:]

    def _add_fala(self, conv, texto):
        """Grava a fala do usuario uma vez so: quando o agente cai e a reserva responde, a mesma fala era gravada 2x (50 pares no historico, 14/10)."""
        ult = self.store.historico(conv, 1)
        if not (ult and ult[0]["role"] == "user" and ult[0]["content"] == texto):
            self.store.add_msg(conv, "user", texto)

    def _tipo_de(self, nome):
        return next((p["tipo"] for p in self.cfg["cadeia"] if p["nome"] == nome), None)

    def responder(self, conv, texto):
        if self.checar_pausa and power.pausado():
            e = power.estado()
            raise Desligado("Braniac desligado" + (f" (jogo: {e['jogo']})" if e["motivo"] == "jogo" else ""))
        sensivel = bool(SENSIVEL.search(texto))
        self._add_fala(conv, texto)
        hist = self.store.historico(conv, self.cfg.get("historico_max_msgs", 20))
        # historico inteiro vai junto: o proximo provedor continua de onde o anterior parou
        sistema = self._sistema(texto)
        msgs = [{"role": "system", "content": sistema}] + hist
        resp, nome = self._disputar(self._ordenar(self.cadeia_para(sensivel), texto),
                                    lambda p: self.chamadores[p["api"]](p, self._msgs_para(p, msgs, texto), self._chave(p), self.cfg.get("timeout_s", 45)))
        if resposta_crua(resp):     # 16/11: 'ia' foi ao Dono como resposta; tenta UMA vez em outro provedor
            try:
                resp, nome = self._disputar([p for p in self._ordenar(self.cadeia_para(sensivel), texto) if p["nome"] != nome],
                                            lambda p: self.chamadores[p["api"]](p, self._msgs_para(p, msgs, texto), self._chave(p), self.cfg.get("timeout_s", 45)))
            except TodosFalharam:
                pass
            if resposta_crua(resp):
                resp = "Não consegui fechar uma resposta agora. Pode me dizer em uma frase o que precisa?"
        if resposta_e_json_de_ferramenta(resp):    # modelo pequeno (local) escreveu a chamada de ferramenta como texto: nunca vai ao Dono nem fica no historico (a IA imitava depois)
            resp = "Agora só consegui uma IA pequena e ela respondeu errado. Tenta de novo em um minuto? (as IAs principais estão em descanso por limite de uso)"
            return resp, nome
        self.store.add_msg(conv, "assistant", resp, nome)
        return resp, nome

    def responder_neutro(self, sistema, texto):
        """Pergunta SEM persona, SEM dossie e SEM banco (usado na conversa com a IA de OUTRO Braniac: so o que vem no texto). Nunca usa o Claude."""
        if self.checar_pausa and power.pausado():
            raise Desligado("Braniac desligado")
        msgs = [{"role": "system", "content": sistema}, {"role": "user", "content": texto}]
        cadeia = [p for p in self.cadeia_para(False) if p["tipo"] in ("online", "local")]
        return self._disputar(self._ordenar(cadeia, texto), lambda p: self.chamadores[p["api"]](p, msgs, self._chave(p), self.cfg.get("timeout_s", 45)))

    def _disputar(self, cadeia, chamar, hedge_s=None, max_paralelo=3):
        """Chama os provedores em ordem, mas SE O ATUAL DEMORA mais que `hedge_s` o proximo ja comeca em paralelo (ate `max_paralelo`);
        vale a 1a resposta valida. Falha rapida -> passa ao proximo na hora. Antes: cada provedor lento/fora era esperado por inteiro
        (6 a 34 s) antes de tentar o seguinte. Devolve (resultado, nome do provedor) ou levanta TodosFalharam."""
        import concurrent.futures as cf
        tentativas, fila = [], []
        for p in cadeia:
            ok, motivo = self.disponivel(p)
            if not ok:
                tentativas.append(f"{p['nome']}: {motivo}")
            else:
                fila.append(p)
        ex = cf.ThreadPoolExecutor(max_workers=max_paralelo)
        ativos = {}

        inicio = {}

        def lancar():
            p = fila.pop(0)
            if p.get("limite_min"):
                self._min.setdefault(p["nome"], []).append(time.time())
            f = ex.submit(chamar, p)
            ativos[f] = p
            inicio[f] = time.time()
        try:
            if fila:
                lancar()
            while ativos:
                espera = hedge_s if hedge_s is not None else self._hedge(next(iter(ativos.values())))
                feitos, _ = cf.wait(list(ativos), timeout=espera, return_when=cf.FIRST_COMPLETED)
                if not feitos:
                    if fila and len(ativos) < max_paralelo:
                        lancar()                       # o atual esta lento: o proximo corre junto
                    continue
                for f in feitos:
                    p = ativos.pop(f)
                    try:
                        res = f.result()
                    except ProviderError as e:
                        latencia.registrar(p["nome"], (time.time() - inicio.get(f, time.time())) * 1000, False)
                        self.falhas[p["nome"]] = [self.falhas.get(p["nome"], (0, 0))[0] + 1, time.time()]
                        if e.cooldown:
                            self.store.set_cooldown(p["nome"], e.cooldown, str(e))
                        tentativas.append(f"{p['nome']}: {e}")
                        if fila:
                            lancar()
                        continue
                    self.store.clear_cooldown(p["nome"])
                    self.falhas.pop(p["nome"], None)
                    self.store.add_uso(p["nome"])
                    seg = time.time() - inicio.get(f, time.time())
                    self._aprender_latencia(p["nome"], seg)
                    latencia.registrar(p["nome"], seg * 1000, True)
                    self.lat_ms.setdefault(p["nome"], latencia.deque(maxlen=latencia.JANELA)).append(int(seg * 1000))
                    return res, p["nome"]
            raise TodosFalharam("; ".join(tentativas))
        finally:
            ex.shutdown(wait=False, cancel_futures=True)

    def _sistema(self, texto="", compacto=False):
        if not self.checar_pausa:  # testes (store injetado) nao leem a base real
            return self.cfg["system"]
        if compacto and self.cfg.get("system_voz"):
            # conversa por VOZ: pedido ~3x menor (3 mil caracteres em vez de 11 mil) = resposta mais rapida e nao estoura o limite de tokens/min dos provedores gratis
            ctx = contexto.dossie_para(texto, 1400, minimo=True)
            return (self.cfg["system_voz"] + REGRA_FATOS + REGRA_TRATAMENTO + assinatura.PROMPT + "\n\nSABE:\n" + contexto.como_texto()[:900]
                    + ("\n\nCONTEXTO:\n" + ctx if ctx else "") + _voz() + _claudinho())
        ctx = contexto.dossie_para(texto)
        return (self.cfg["system"] + REGRA_FATOS + REGRA_TRATAMENTO + assinatura.PROMPT + "\n\nO QUE JA SE SABE (use sem perguntar de novo):\n" + contexto.como_texto()
                + ("\n\nCONTEXTO RECENTE (dossie):\n" + ctx if ctx else "") + _voz() + _claudinho())

    def _passo_com_ferramentas(self, msgs, tools, sensivel, texto="", compacto=False):
        """Um passo do agente: primeiro provedor disponivel (que suporte ferramentas) devolve a mensagem."""
        cadeia = [p for p in self.cadeia_para(sensivel) if p["api"] in self.chamadores_tools]   # Claude CLI nao faz function calling
        return self._disputar(self._ordenar(cadeia, texto, tools=True), lambda p: self._chamar_tools(p, msgs, texto, compacto, tools))

    def _chamar_tools(self, p, msgs, texto, compacto, tools):
        """14/10: o pedido completo (sistema + ~30 ferramentas + historico ~ 11 mil tokens) estourava o limite do Groq gratis (413 'Request too large')
        e o agente ficava so com o Gemini; quando o Gemini caia, nada com ferramenta sobrava. No 413, tenta de novo ENXUTO no mesmo provedor."""
        chamar = self.chamadores_tools[p["api"]]
        timeout = self.cfg.get("timeout_s", 45)
        try:
            return chamar(p, self._msgs_para(p, msgs, texto, compacto), self._chave(p), timeout, tools)
        except ProviderError as e:
            if not str(e).startswith("413"):
                raise
        enxuto = [{**msgs[0], "content": self._sistema(texto, True)}] + _historico_enxuto(msgs[1:])
        return chamar(p, self._msgs_para(p, enxuto, texto, True), self._chave(p), timeout, _ferramentas_enxutas(tools))

    def _fechar_sem_ferramentas(self, msgs, texto, sensivel):
        """15/10: os passos acabaram -> uma ultima chamada SEM ferramentas, com o que ja foi apurado, em vez de mandar o Dono 'pedir ao Claude'."""
        linhas = []
        for m in msgs[1:]:
            if m.get("role") == "tool":
                linhas.append("RESULTADO DE FERRAMENTA: " + str(m.get("content"))[:1500])
            elif m.get("content"):
                linhas.append(("DONO: " if m["role"] == "user" else "VOCE: ") + str(m["content"])[:1500])
        pedido = ("\n".join(linhas[-12:]) + "\n\nResponda AGORA a ultima mensagem do Dono, em portugues, curto, usando so o que esta acima. "
                  "Se faltar algo, diga o que conseguiu e pergunte UMA coisa objetiva. Nunca mande ele procurar o Claude.")
        flat = [msgs[0], {"role": "user", "content": pedido}]
        cadeia = [p for p in self.cadeia_para(sensivel) if p["api"] != "cli"]
        try:
            resp, _ = self._disputar(self._ordenar(cadeia, texto),
                                     lambda p: self.chamadores[p["api"]](p, self._msgs_para(p, flat, texto, True), self._chave(p), self.cfg.get("timeout_s", 45)))
            return (resp or "").strip()
        except Exception:
            return ""

    def _base(self, msgs, texto):
        """Tudo que o modelo teve na mao neste pedido (conversa, ferramentas e o pacote do banco): fonte dos numeros que ele pode citar."""
        def serve(i):      # nem a dica de refazer nem a resposta reprovada (a anterior a dica) contam como fonte: senao o numero inventado se 'confirmava' sozinho
            dica = lambda j: j < len(msgs) and str(msgs[j].get("content")).startswith("[ATENCAO:")
            return not dica(i) and not dica(i + 1)
        return "\n".join([texto] + [str(m.get("content") or "") for i, m in enumerate(msgs) if serve(i)] + [v[1] for v in self._pk.values()])

    def _defeito(self, final, msgs, texto, feitas):
        """Dica para refazer, ou '' se a resposta pode ir. Numero so e conferido quando houve ferramenta (ai a resposta relata dado; conta e conhecimento geral ficam livres)."""
        if resposta_crua(final):
            return "[ATENCAO: sua resposta anterior veio vazia ou com o resultado cru da ferramenta. Responda ao Dono em uma ou duas frases, com suas palavras, dizendo o que foi feito ou o que o dado mostra.]"
        fora = numeros_inventados(final, self._base(msgs, texto)) if feitas else []
        if fora:
            from . import clareza
            clareza._evento("numero_inventado", ", ".join(fora)[:80])
            return (f"[ATENCAO: voce citou {', '.join(fora)} e esse(s) numero(s) NAO aparece(m) no resultado das ferramentas nem na conversa. "
                    "Refaca usando so numeros que estao acima; se nao tiver o numero, diga que nao tem.]")
        return ""

    def _consertar(self, final, msgs, texto, feitas):
        """Ultima barreira, sem IA: resposta crua vira pedido de repeticao; frase com numero inventado sai."""
        if resposta_crua(final):
            return "Não consegui fechar uma resposta agora. Pode me dizer em uma frase o que precisa?"
        fora = numeros_inventados(final, self._base(msgs, texto)) if feitas else []
        return sem_frases_com(final, fora) if fora else final

    def responder_agente(self, conv, texto, tools, executor, max_passos=6, compacto=False):
        """Agente: a IA escolhe ferramentas (executor(nome, args) -> texto) ate dar a resposta final."""
        if self.checar_pausa and power.pausado():
            raise Desligado("Braniac desligado")
        sensivel = bool(SENSIVEL.search(texto))
        self._add_fala(conv, texto)
        msgs = [{"role": "system", "content": self._sistema(texto, compacto)}] + self.store.historico(conv, self.cfg.get("historico_max_msgs", 8 if compacto else 20))
        texto_tentativas = 0
        feitas = {}
        refeita = False
        for _ in range(max_passos):
            m, nome = self._passo_com_ferramentas(msgs, tools, sensivel, texto, compacto)
            calls = m.get("tool_calls")
            if not calls:
                final = (m.get("content") or "").strip()
                em_texto = chamada_em_texto(final, {t["function"]["name"] for t in tools} if tools else None)
                if em_texto and texto_tentativas < 2:        # a IA escreveu a ferramenta como texto: executa de verdade em vez de mandar o JSON ao Dono
                    texto_tentativas += 1
                    calls = [{"id": "txt", "function": {"name": em_texto[0], "arguments": json.dumps(em_texto[1])}}]
                    m = {"role": "assistant", "content": None, "tool_calls": calls}
                elif em_texto or resposta_e_json_de_ferramenta(final) or (final.startswith("{") and '"tool"' in final[:40]):
                    final = "Não consegui concluir isso agora. Pode pedir de novo?"      # nunca manda JSON de ferramenta como resposta
                    self.store.add_msg(conv, "assistant", final, nome)
                    return final, nome
                else:
                    dica = self._defeito(final, msgs, texto, feitas)
                    if dica and not refeita:      # refaz UMA vez, com o defeito dito ao modelo (a dica fica so neste pedido, nao no historico)
                        refeita = True
                        msgs += [{"role": "assistant", "content": final or "(vazio)"}, {"role": "user", "content": dica}]
                        continue
                    final = self._consertar(final, msgs, texto, feitas)
                    self.store.add_msg(conv, "assistant", final, nome)
                    return final, nome
            msgs.append(m)
            for c in calls:
                try:
                    args = json.loads(c["function"].get("arguments") or "{}")
                except ValueError:
                    args = {}
                chave = c["function"]["name"] + json.dumps(args, sort_keys=True, ensure_ascii=False)
                if chave in feitas:   # 15/10: a IA repetia a mesma ferramenta ate esgotar os passos -> devolve o resultado guardado e manda responder
                    msgs.append({"role": "tool", "tool_call_id": c.get("id", ""), "content": feitas[chave][:3500] + "\n(Ja consultado. Responda AGORA ao Dono com o que voce tem.)"})
                    continue
                try:
                    if self.checar_pausa:
                        from . import banco
                        banco.definir_tipo(self._tipo_de(nome))   # a ferramenta consultar_banco respeita a camada de quem esta chamando
                    res = executor(c["function"]["name"], args)
                    if self.checar_pausa and banco.usou_local():
                        sensivel = True       # o resultado trouxe dado local (WhatsApp): dai em diante so Ollama/Claude, nunca IA online
                        banco.limpar_marca()
                except Exception as e:  # ferramenta falhou: o modelo precisa saber, nao o servidor cair
                    res = f"ERRO na ferramenta: {str(e)[:200]}"
                msgs.append({"role": "tool", "tool_call_id": c.get("id", ""), "content": str(res)[:4000]})
                feitas[chave] = str(res)
        final = self._fechar_sem_ferramentas(msgs, texto, sensivel)
        if final:
            final = self._consertar(final, msgs, texto, feitas)
            self.store.add_msg(conv, "assistant", final, "agente")
            return final, "agente"
        final = "Não consegui fechar uma resposta agora. Pode me dizer em uma frase o que precisa?"
        self.store.add_msg(conv, "assistant", final, "agente")
        return final, "agente"

    def status(self):
        linhas = []
        for p in self.cfg["cadeia"]:
            ok, motivo = self.disponivel(p)
            linhas.append(f"{'OK ' if ok else '-- '}{p['nome']:<11} {p['tipo']:<7} "
                          f"hoje={self.store.uso_hoje(p['nome']):<3} {motivo}")
        return "\n".join(linhas)
