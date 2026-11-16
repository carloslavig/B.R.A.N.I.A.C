# -*- coding: utf-8 -*-
"""Convites, pares conhecidos e permissoes (SPEC.md secoes 3 e 7). Nada e confiavel por padrao: par novo fica 'pendente' ate o dono
conferir o codigo curto (SAS) com a outra pessoa e chamar confirmar(). Revogar apaga o segredo do canal e bloqueia o dispositivo."""
import hashlib
import hmac
import json
import secrets
import time
from pathlib import Path

from .identidade import b64, id_de, unb64

PREFIXO = "BLINK1."
VALIDADE_CONVITE_S = 900
ACOES = ("msg", "tarefa", "arquivo")
NIVEIS = ("recusar", "perguntar", "aceitar")
PADRAO = {"msg": "aceitar", "tarefa": "recusar", "arquivo": "perguntar"}   # tarefa remota nunca roda sem o dono liberar


class ConviteErro(ValueError):
    pass


def sas(pub_a, pub_b):
    """Codigo de 6 digitos igual nos dois lados, para conferir por voz/WhatsApp (detecta homem no meio)."""
    a, b = sorted((unb64(pub_a), unb64(pub_b)))
    n = int.from_bytes(hashlib.sha256(b"blink-sas" + a + b).digest()[:4], "big") % 1_000_000
    return f"{n:06d}"


def prova(seg_b64, id_convidante, id_convidado):
    """Prova de que o convidado leu o convite (HMAC do segredo de uso unico)."""
    return b64(hmac.new(unb64(seg_b64), f"{id_convidante}|{id_convidado}".encode(), hashlib.sha256).digest())


class Pares:
    """Arquivo pares.json: {pares: {id: {nome, pub, estado: pendente|confiavel|revogado, seg, perm}}, convites: {seg: {exp}}}."""

    def __init__(self, pasta):
        self.arq = Path(pasta) / "pares.json"
        self.arq.parent.mkdir(parents=True, exist_ok=True)

    def _ler(self):
        try:
            return json.loads(self.arq.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"pares": {}, "convites": {}}

    def _gravar(self, d):
        self.arq.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")

    # ---- convite ----
    def convidar(self, ident, agora=None):
        """Texto do convite para entregar ao outro dono (uso unico, vale 15 min)."""
        agora = int(agora or time.time())
        seg = b64(secrets.token_bytes(16))
        d = self._ler()
        d["convites"] = {k: v for k, v in d["convites"].items() if v["exp"] > agora}
        d["convites"][seg] = {"exp": agora + VALIDADE_CONVITE_S}
        self._gravar(d)
        corpo = {"v": 1, "id": ident.id, "pub": ident.pub, "nome": ident.nome, "seg": seg, "exp": agora + VALIDADE_CONVITE_S}
        return PREFIXO + b64(json.dumps(corpo, separators=(",", ":")).encode())

    @staticmethod
    def ler_convite(texto, agora=None):
        texto = (texto or "").strip()
        if not texto.startswith(PREFIXO):
            raise ConviteErro("nao e um convite do BRANIAC LINK")
        try:
            c = json.loads(unb64(texto[len(PREFIXO):]))
            if id_de(c["pub"]) != c["id"] or not isinstance(c["seg"], str) or not isinstance(c["exp"], int):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            raise ConviteErro("convite corrompido")
        if c["exp"] < (agora or time.time()):
            raise ConviteErro("convite vencido")
        return c

    def aceitar_convite(self, texto, agora=None):
        """Lado convidado: guarda o convidante como pendente. Devolve o convite lido (para conectar usando seg)."""
        c = self.ler_convite(texto, agora)
        self._salvar_par(c["id"], str(c.get("nome", "")), c["pub"], c["seg"])
        d = self._ler()
        d["pares"][c["id"]]["conectar_ate"] = c["exp"]      # o Braniac tenta conectar sozinho ate o convite vencer
        self._gravar(d)
        return c

    def consumir_convite(self, seg, ident, id_convidado, pub_convidado, nome, prova_recebida, agora=None):
        """Lado convidante: o convidado apareceu com a prova. O convite e queimado (uso unico) e o par entra como pendente."""
        agora = int(agora or time.time())
        d = self._ler()
        c = d["convites"].get(seg)
        if not c or c["exp"] < agora:
            raise ConviteErro("convite desconhecido, usado ou vencido")
        if id_de(pub_convidado) != id_convidado or not hmac.compare_digest(prova(seg, ident.id, id_convidado), str(prova_recebida)):
            raise ConviteErro("prova do convite nao confere")
        del d["convites"][seg]
        self._gravar(d)
        self._salvar_par(id_convidado, nome, pub_convidado, seg)

    # ---- pares ----
    def _salvar_par(self, pid, nome, pub, seg):
        d = self._ler()
        atual = d["pares"].get(pid, {})
        if atual.get("estado") == "revogado":
            raise ConviteErro("dispositivo revogado")
        d["pares"][pid] = {"nome": nome[:60], "pub": pub, "seg": seg, "estado": atual.get("estado", "pendente"),
                           "perm": atual.get("perm", {}), "desde": atual.get("desde", int(time.time()))}
        if "conectar_ate" in atual:
            d["pares"][pid]["conectar_ate"] = atual["conectar_ate"]
        self._gravar(d)

    def marcar_conectado(self, pid):
        d = self._ler()
        if pid in d["pares"]:
            d["pares"][pid].pop("conectar_ate", None)
            self._gravar(d)

    def get(self, pid):
        return self._ler()["pares"].get(pid)

    def listar(self):
        return {k: {c: v for c, v in p.items() if c != "seg"} for k, p in self._ler()["pares"].items()}

    def convites_abertos(self, agora=None):
        return {k: v for k, v in self._ler()["convites"].items() if v["exp"] > (agora or time.time())}

    def confirmar(self, pid):
        """O dono conferiu o SAS com a outra pessoa."""
        d = self._ler()
        if pid not in d["pares"] or d["pares"][pid]["estado"] == "revogado":
            raise ConviteErro("par desconhecido ou revogado")
        d["pares"][pid]["estado"] = "confiavel"
        self._gravar(d)

    def revogar(self, pid):
        d = self._ler()
        if pid in d["pares"]:
            d["pares"][pid].update(estado="revogado", seg="", perm={})
            self._gravar(d)

    # ---- permissoes ----
    def permitir(self, pid, agente, acao, nivel):
        if acao not in ACOES or nivel not in NIVEIS:
            raise ConviteErro("acao ou nivel invalido")
        d = self._ler()
        if pid not in d["pares"] or d["pares"][pid]["estado"] != "confiavel":
            raise ConviteErro("so par confiavel recebe permissoes")
        d["pares"][pid]["perm"].setdefault(agente, {})[acao] = nivel
        self._gravar(d)

    def decidir(self, pid, acao, agente="*"):
        """aceitar | perguntar | recusar. Desconhecido, pendente ou revogado: recusar."""
        p = self.get(pid)
        if not p or p["estado"] != "confiavel":
            return "recusar"
        perm = p.get("perm", {})
        return perm.get(agente, {}).get(acao) or perm.get("*", {}).get(acao) or PADRAO.get(acao, "recusar")
