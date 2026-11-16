# -*- coding: utf-8 -*-
"""Agente de programacao PLUGAVEL do Braniac: quem mexe no codigo, faz tarefas no PC e responde duvidas dificeis.

O Braniac funciona sem nenhum deles (IAs gratis, Ollama local, dev_livre). Quando existe um, ele entra por aqui:
  claude  -> Claude Code (`claude -p`)           codex  -> OpenAI Codex CLI (`codex exec`)
  gemini  -> Gemini CLI (`gemini -p`)            custom -> qualquer CLI, via `comando`
  nenhum  -> sem agente: os pedidos que precisariam dele voltam com uma mensagem clara (nada quebra)

Escolha (a primeira que existir vale): variavel BRANIAC_AGENTE, depois `data/agente_dev.json` {"agente": "codex", "comando": "..."},
senao `claude` (padrao historico). BRANIAC_SEM_CLAUDE=1 continua valendo e significa `nenhum`.
`custom`: `comando` e uma lista de argumentos (ou texto) onde `{prompt}` vira o pedido; sem `{prompt}`, o pedido vai pela entrada padrao.
"""
import json
import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

from .store import DATA

RAIZ = Path(__file__).parent.parent
PASTA = Path(__file__).parent
AGENTES = ("claude", "codex", "gemini", "custom", "nenhum")
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)   # sem janela de cmd piscando no Windows
EXE = {"claude": ("claude", "claude.cmd"), "codex": ("codex", "codex.cmd"), "gemini": ("gemini", "gemini.cmd")}
# agentes que nao leem o CLAUDE.md sozinhos recebem a indicacao do guia generico no inicio do pedido
GUIA = ("Antes de agir, leia o guia do projeto em {guia} e, se existir, o CLAUDE.md ou AGENTS.md da pasta de trabalho; "
        "siga as travas de seguranca deles.\n\n")


def _config():
    try:
        cfg = json.loads((DATA / "agente_dev.json").read_text(encoding="utf-8-sig"))
        return cfg if isinstance(cfg, dict) else {}
    except (OSError, ValueError):
        return {}


def escolhido():
    """Nome do agente em uso: claude | codex | gemini | custom | nenhum."""
    if os.environ.get("BRANIAC_SEM_CLAUDE") == "1":
        return "nenhum"
    nome = (os.environ.get("BRANIAC_AGENTE") or _config().get("agente") or "claude").strip().lower()
    return nome if nome in AGENTES else "claude"


def rotulo():
    """Como chamar o agente nas mensagens ao usuario."""
    return {"claude": "Claude", "codex": "Codex", "gemini": "Gemini CLI", "custom": "o agente configurado",
            "nenhum": "o agente de programação"}[escolhido()]


def _comando_custom():
    c = _config().get("comando") or os.environ.get("BRANIAC_AGENTE_CMD") or ""
    return shlex.split(c, posix=os.name != "nt") if isinstance(c, str) else [str(x) for x in c]


def localizar(nome=None):
    """Caminho do executavel (ou None se o agente nao esta instalado)."""
    nome = nome or escolhido()
    if nome == "nenhum":
        return None
    if nome == "custom":
        cmd = _comando_custom()
        return shutil.which(cmd[0]) or (cmd[0] if cmd and Path(cmd[0]).exists() else None) if cmd else None
    if nome == "claude":   # o monitor ja sabe achar o claude.exe do app (versoes novas, auto-update)
        try:
            from .claude_agent import _carregar_trigger, _config as cfg_monitor
            return _carregar_trigger().resolve_cli(cfg_monitor()["cli"])
        except Exception:
            pass
    for e in EXE.get(nome, ()):
        achou = shutil.which(e)
        if achou:
            return achou
    return None


def disponivel():
    return localizar() is not None


def _montar(nome, exe, workdir, editar, navegador, permissao, pular_permissoes, saida):
    """(argumentos, o_pedido_vai_pela_entrada_padrao). Cada agente tem o seu jeito de ficar so leitura x editar."""
    if nome == "claude":
        args = [exe]
        if navegador:
            args.append("--chrome")
        args.append("-p")
        if editar and pular_permissoes:
            args.append("--dangerously-skip-permissions")
        elif editar and permissao:
            args += ["--permission-mode", permissao]
        return args, True
    if nome == "codex":
        # `-` = ler o pedido da entrada padrao; a resposta final vai para o arquivo (stdout traz so o progresso)
        return [exe, "exec", "--skip-git-repo-check", "-C", str(workdir), "-s", "workspace-write" if editar else "read-only",
                "-o", saida, "-"], True
    if nome == "gemini":
        return [exe, "--approval-mode", "auto_edit" if editar else "default", "-p", "Execute o pedido recebido pela entrada padrao."], True
    cmd = _comando_custom()
    if any("{prompt}" in a for a in cmd):
        return cmd, False
    return cmd, True


def rodar(prompt, workdir=None, timeout=600, editar=False, navegador=False, permissao="acceptEdits", pular_permissoes=False):
    """Roda o agente escolhido. Devolve (codigo, texto): 0 = ok; 124 = estourou o tempo; 127 = sem agente/instalacao.
    editar=False: so responde (sem mexer em arquivos). navegador=True so tem efeito no Claude (--chrome)."""
    nome = escolhido()
    exe = localizar(nome)
    if not exe:
        motivo = ("nenhum agente de programação configurado (BRANIAC_AGENTE=nenhum)" if nome == "nenhum"
                  else f"não encontrei o {rotulo()} instalado")
        return 127, f"Sem agente de programação: {motivo}. O Braniac segue funcionando com as IAs grátis/locais."
    workdir = str(workdir or RAIZ)
    if nome != "claude":
        prompt = GUIA.format(guia=PASTA / "AGENTS.md") + prompt
    with tempfile.TemporaryDirectory(prefix="braniac-agente-") as tmp:
        saida = str(Path(tmp) / "resposta.txt")
        args, por_stdin = _montar(nome, exe, workdir, editar, navegador, permissao, pular_permissoes, saida)
        if not por_stdin:
            args = [a.replace("{prompt}", " ".join(prompt.split("\n"))) for a in args]   # CLI .cmd no Windows corta argumento por linha
        try:
            r = subprocess.run(args, input=prompt if por_stdin else None, stdin=None if por_stdin else subprocess.DEVNULL,
                               cwd=workdir, capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=timeout, creationflags=SEM_JANELA)
        except subprocess.TimeoutExpired as e:
            return 124, ((e.stdout or "") if isinstance(e.stdout, str) else "") + f"\n[TIMEOUT] passou de {timeout}s e foi encerrado."
        except (OSError, subprocess.SubprocessError) as e:
            return 1, f"Não consegui acionar {rotulo()}: {str(e)[:200]}"
        final = ""
        if nome == "codex":
            try:
                final = Path(saida).read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                pass
        texto = final or (r.stdout or "")
        if r.returncode != 0 and r.stderr:
            texto += "\n[stderr]\n" + r.stderr
        return r.returncode, texto


def perguntar(prompt, workdir=None, timeout=150):
    """Duvida/decisao em texto (sem editar nada). Devolve o texto ou None se nao ha agente ou ele falhou."""
    cod, texto = rodar(prompt, workdir, timeout, editar=False)
    return texto.strip() if cod == 0 and texto.strip() else None


def status():
    """Retrato para o painel e para o `python -m braniac.agente_dev`."""
    nome = escolhido()
    return {"agente": nome, "instalado": disponivel(), "caminho": localizar(nome),
            "opcoes": list(AGENTES), "sem_agente_o_braniac_funciona": True}


if __name__ == "__main__":
    print(json.dumps(status(), ensure_ascii=False, indent=2))
