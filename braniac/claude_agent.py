# -*- coding: utf-8 -*-
"""Delega tarefas no PC ao agente de programacao escolhido (padrao: Claude Code, `claude -p --chrome`; ver agente_dev.py).

Usa a assinatura do Dono (unico custo permitido) e as travas do CLAUDE.md da pasta Agente.
So roda apos confirmacao do dono; respeita o teto diario de acionamentos do Claude.
"""
import configparser, importlib.util, threading, time
from pathlib import Path
from .store import DATA

RAIZ = Path(__file__).parent.parent
_trigger = None


def _carregar_trigger():
    global _trigger
    if _trigger is None:
        spec = importlib.util.spec_from_file_location("monitor_trigger", RAIZ / "monitor" / "lib" / "trigger.py")
        _trigger = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_trigger)
    return _trigger


def _config():
    cp = configparser.ConfigParser(inline_comment_prefixes=("#",))
    cp.read(RAIZ / "monitor" / "config.ini", encoding="utf-8-sig")
    c = cp["claude"] if cp.has_section("claude") else {}
    return {
        "cli": c.get("CLI_PATH", "auto"),
        "workdir": c.get("WORKDIR", str(RAIZ)),
        "mode": c.get("PERMISSION_MODE", "acceptEdits"),
        "skip": str(c.get("DANGEROUS_SKIP_PERMISSIONS", "false")).strip().lower() == "true",
    }


def montar_prompt(tarefa):
    return ("O Dono pediu esta tarefa pelo Jarvis (Telegram): " + tarefa.strip() +
            " | Siga o CLAUDE.md desta pasta e todas as travas de seguranca (nada de pagamento, senha ou dados "
            "bancarios; nunca alterar o anuncio do Amiga; nao invente informacao). Para enviar mensagens "
            "no WhatsApp so faca o que a tarefa pedir explicitamente. Ao terminar, responda com um resumo "
            "curto em portugues do Brasil do que foi feito.")


def _log(linha):
    """Toda delegacao (inicio e fim) fica registrada: antes o resultado sumia quando nao havia canal aberto para avisar."""
    try:
        DATA.mkdir(exist_ok=True)
        with (DATA / "delegacoes.log").open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {linha}\n")
    except OSError:
        pass


def _avisar_dono(texto):
    from . import telegram_bot
    return telegram_bot.avisar_dono(texto)


def executar_em_segundo_plano(tarefa, ao_terminar, timeout=600):
    """Roda o Claude numa thread; chama ao_terminar(texto) com o resumo (ou o erro).
    Sem ninguem para ouvir (ao_terminar None, ex.: chamada pela API local), o resultado vai ao Dono no Telegram."""
    _log("INICIO | " + tarefa.strip()[:300].replace(chr(10), " "))
    destino = ao_terminar or (lambda r: _avisar_dono("🤖 Claude terminou:" + chr(10)*2 + r))

    def ao_terminar(r, _d=destino):
        _log("FIM | " + r[:500].replace(chr(10), " "))
        _d(r)

    def trabalho():
        try:
            from . import agente_dev
            c = _config()
            code, saida = agente_dev.rodar(montar_prompt(tarefa), c["workdir"], timeout, editar=True, navegador=True,
                                           permissao=c["mode"], pular_permissoes=c["skip"])
            quem = agente_dev.rotulo()
            if code == 0 and saida.strip():
                ao_terminar(saida.strip()[-3500:])
            elif code == 127:
                ao_terminar(saida.strip())
            elif code == 124:
                ao_terminar(f"{quem} passou do tempo limite e foi encerrado. Confira o que ficou pela metade.")
            else:
                ao_terminar(f"{quem} terminou com erro (código {code}):\n{saida.strip()[-800:]}")
        except Exception as e:
            ao_terminar(f"Não consegui acionar o agente de programação: {str(e)[:200]}")
    th = threading.Thread(target=trabalho, daemon=True, name="braniac-claude")
    th.start()
    return th
