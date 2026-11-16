# -*- coding: utf-8 -*-
"""Chamadas aos provedores. Cada uma devolve texto ou levanta ProviderError(cooldown)."""
import shutil, subprocess
from pathlib import Path
import requests

RAIZ_AGENTE = Path(__file__).parent.parent
_S = requests.Session()   # reaproveita a conexao (keep-alive): sem novo aperto de mao TLS a cada chamada


class ProviderError(Exception):
    def __init__(self, msg, cooldown=60):
        super().__init__(msg)
        self.cooldown = cooldown


def _status_error(r, p):
    s = r.status_code
    if s == 429:
        try:
            espera = int(float(r.headers.get("retry-after", "")))
        except ValueError:
            espera = 900  # cota estourada: tenta de novo em 15 min
        return ProviderError("429 limite de uso", max(espera, 30))
    if s in (401, 402, 403, 404):
        return ProviderError(f"{s} chave/modelo/acesso: {r.text[:120]}", 6 * 3600)
    if s >= 500:
        return ProviderError(f"{s} servidor fora", 300)   # 5xx: nao insiste por 5 min (cada tentativa falha custava 6 a 34 s)
    return ProviderError(f"{s} {r.text[:120]}", 0)


def chamar_openai(p, messages, chave, timeout):
    try:
        r = _S.post(p["url"], headers={"Authorization": f"Bearer {chave}"},
                          json={"model": p["modelo"], "messages": messages}, timeout=timeout)
    except requests.RequestException as e:
        raise ProviderError(f"rede: {e}", 60)
    if r.status_code != 200:
        raise _status_error(r, p)
    try:
        txt = r.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError):
        raise ProviderError("resposta sem conteudo", 0)
    if not (txt or "").strip():
        raise ProviderError("resposta vazia", 0)
    return txt.strip()


def chamar_ollama(p, messages, chave, timeout):
    try:
        r = _S.post(p["url"], json={"model": p["modelo"], "messages": messages,
                          "stream": False, "keep_alive": p.get("keep_alive", "2m")},
                          timeout=max(timeout, 120))  # CPU/GPU fraca: 1a resposta demora
    except requests.RequestException as e:
        raise ProviderError(f"ollama indisponivel: {e}", 60)
    if r.status_code != 200:
        raise _status_error(r, p)
    txt = (r.json().get("message") or {}).get("content", "")
    if not txt.strip():
        raise ProviderError("resposta vazia", 0)
    return txt.strip()


def chamar_claude(p, messages, chave, timeout):
    from . import agente_dev
    if not agente_dev.disponivel():
        raise ProviderError("agente de programacao (claude/codex/...) nao encontrado", 3600)
    linhas = []
    for m in messages:
        quem = {"system": "INSTRUCOES", "user": "USUARIO", "assistant": "ASSISTENTE"}[m["role"]]
        linhas.append(f"{quem}: {m['content']}")
    prompt = ("\n\n".join(linhas) + "\n\nResponda apenas a ultima mensagem do USUARIO, "
              "sem usar ferramentas.")
    cod, saida = agente_dev.rodar(prompt, RAIZ_AGENTE, 300)
    out = saida.strip()
    if cod == 124:
        raise ProviderError("agente de programacao demorou demais", 300)
    if cod != 0 or not out:
        raise ProviderError(f"agente de programacao falhou: {out[:150]}", 3600)
    return out


CHAMADORES = {"openai": chamar_openai, "ollama": chamar_ollama, "cli": chamar_claude}


# ---------- chamadas com ferramentas (function calling) ----------

def _limpar_msg(m):
    """Mantem so o que o proximo passo precisa (alguns provedores rejeitam campos extras como 'reasoning')."""
    out = {"role": "assistant", "content": m.get("content")}
    if m.get("tool_calls"):
        out["tool_calls"] = m["tool_calls"]
    if m.get("extra_content"):
        out["extra_content"] = m["extra_content"]
    return out


def chamar_openai_tools(p, messages, chave, timeout, tools):
    """Devolve a mensagem do assistente (dict com content e/ou tool_calls)."""
    try:
        r = _S.post(p["url"], headers={"Authorization": f"Bearer {chave}"},
                          json={"model": p["modelo"], "messages": messages, "tools": tools, "tool_choice": "auto"},
                          timeout=timeout)
    except requests.RequestException as e:
        raise ProviderError(f"rede: {e}", 60)
    if r.status_code != 200:
        raise _status_error(r, p)
    try:
        m = r.json()["choices"][0]["message"]
    except (KeyError, IndexError, ValueError):
        raise ProviderError("resposta sem conteudo", 0)
    if not (m.get("content") or "").strip() and not m.get("tool_calls"):
        raise ProviderError("resposta vazia", 0)
    return _limpar_msg(m)


def chamar_ollama_tools(p, messages, chave, timeout, tools):
    """Ollama nativo: argumentos vem como dict e sem id; normaliza para o formato OpenAI."""
    import json as _json
    msgs = []
    for m in messages:  # ollama quer arguments como objeto
        m = dict(m)
        if m.get("tool_calls"):
            m["tool_calls"] = [{"function": {"name": c["function"]["name"],
                                             "arguments": _json.loads(c["function"]["arguments"] or "{}")}}
                               for c in m["tool_calls"]]
        msgs.append(m)
    try:
        r = _S.post(p["url"], json={"model": p["modelo"], "messages": msgs, "tools": tools, "stream": False,
                                          "keep_alive": p.get("keep_alive", "2m")}, timeout=max(timeout, 180))
    except requests.RequestException as e:
        raise ProviderError(f"ollama indisponivel: {e}", 60)
    if r.status_code != 200:
        raise _status_error(r, p)
    m = r.json().get("message") or {}
    calls = [{"id": f"call_{i}", "type": "function",
              "function": {"name": c["function"]["name"], "arguments": _json.dumps(c["function"].get("arguments") or {})}}
             for i, c in enumerate(m.get("tool_calls") or [])]
    if not (m.get("content") or "").strip() and not calls:
        raise ProviderError("resposta vazia", 0)
    out = {"role": "assistant", "content": m.get("content") or ""}
    if calls:
        out["tool_calls"] = calls
    return out


CHAMADORES_TOOLS = {"openai": chamar_openai_tools, "ollama": chamar_ollama_tools}
