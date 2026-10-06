# -*- coding: utf-8 -*-
"""Permissoes em CASCATA, GRANULARES e REVOGAVEIS.

- Cada recurso tem um pai (ex.: 'arquivos') e filhos (ex.: 'arquivos.ler', 'arquivos.escrever', 'arquivos.apagar').
- Um filho so vale se o pai estiver liberado; revogar o pai revoga os filhos.
- Nada vem liberado: a pessoa escolhe 'total', 'granular' ou 'nenhum' na instalacao (e pode mudar depois, por voz ou pelo painel).
- Toda mudanca fica num registro (auditoria) que a pessoa pode ler. 'revogar_tudo' e o botao de emergencia.
"""
import json, time
from . import paths, perfil


class PermissaoNegada(Exception):
    pass


# chave -> (titulo, o que o assistente consegue fazer, risco)
CATALOGO = {
    "microfone": ("Microfone", "Ouvir você para conversar por voz. Nada é gravado em disco.", "baixo"),
    "ias_nuvem": ("IAs na nuvem", "Consultar ChatGPT/Gemini e outras IAs que você liberar (nunca envia suas mensagens privadas).", "baixo"),
    "arquivos": ("Arquivos", "Acessar arquivos do PC.", "alto"),
    "arquivos.ler": ("Ler arquivos", "Abrir e ler arquivos e pastas.", "medio"),
    "arquivos.escrever": ("Criar e editar arquivos", "Criar e alterar arquivos.", "alto"),
    "arquivos.apagar": ("Apagar arquivos", "Mover para a lixeira ou apagar.", "alto"),
    "programas": ("Programas", "Controlar programas do PC.", "alto"),
    "programas.abrir": ("Abrir programas", "Abrir aplicativos e sites.", "baixo"),
    "programas.executar": ("Executar comandos", "Rodar comandos e scripts no PC.", "alto"),
    "navegador": ("Navegador", "Usar o navegador do assistente.", "medio"),
    "navegador.ler": ("Ler páginas", "Ler o conteúdo de páginas abertas.", "medio"),
    "navegador.agir": ("Agir em páginas", "Clicar, preencher e enviar em páginas.", "alto"),
    "email": ("E-mail", "Acessar seu e-mail.", "medio"),
    "email.ler": ("Ler e-mails", "Ler e resumir e-mails.", "medio"),
    "email.enviar": ("Enviar e-mails", "Enviar e-mails em seu nome.", "alto"),
    "whatsapp": ("WhatsApp", "Usar o WhatsApp.", "alto"),
    "whatsapp.ler": ("Ler conversas", "Ler e resumir conversas.", "alto"),
    "whatsapp.enviar": ("Enviar mensagens", "Enviar mensagens em seu nome.", "alto"),
    "spotify": ("Spotify", "Tocar músicas e controlar o volume.", "baixo"),
    "sistema": ("Sistema", "Volume, janelas, modo jogo e lembretes.", "baixo"),
    "sistema.tela": ("Ver a tela", "Tirar prints da tela do PC (usado no controle remoto).", "alto"),
    "sistema.status": ("Ver o estado do PC", "Memória, disco e hora do PC.", "baixo"),
}

PERFIS = {   # atalhos para a tela de instalacao (a pessoa ainda pode ajustar item por item)
    "nenhum": [],
    "basico": ["microfone", "ias_nuvem", "spotify", "sistema", "programas", "programas.abrir"],
    "granular": [],   # a pessoa marca um a um
    "total": list(CATALOGO),
}


def pai_de(chave):
    return chave.split(".")[0] if "." in chave else None


def filhos_de(chave):
    return [c for c in CATALOGO if c.startswith(chave + ".")]


def _arq():
    return paths.arquivo("permissoes.json")


def _ler():
    try:
        return json.loads(_arq().read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {"liberadas": [], "registro": []}


def _gravar(d):
    d["registro"] = d["registro"][-500:]
    _arq().write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def _log(d, acao, chave):
    d["registro"].append([time.strftime("%Y-%m-%d %H:%M:%S"), acao, chave])


def liberadas():
    return set(_ler()["liberadas"])


def permitido(chave):
    """True so se a permissao E o pai dela estiverem liberados."""
    if chave not in CATALOGO:
        return False
    lib = liberadas()
    pai = pai_de(chave)
    return chave in lib and (pai is None or pai in lib)


def exigir(chave):
    if not permitido(chave):
        titulo = CATALOGO.get(chave, (chave,))[0]
        raise PermissaoNegada(f"Você ainda não liberou '{titulo}' para o assistente.")


def conceder(chave, com_filhos=False):
    if chave not in CATALOGO:
        raise KeyError(chave)
    d = _ler()
    alvo = {chave, *(filhos_de(chave) if com_filhos else [])}
    pai = pai_de(chave)
    if pai:
        alvo.add(pai)                      # filho precisa do pai liberado para valer
    for c in alvo:
        if c not in d["liberadas"]:
            d["liberadas"].append(c)
            _log(d, "liberou", c)
    _gravar(d)


def revogar(chave):
    """Revoga a permissao e, em cascata, todos os filhos."""
    d = _ler()
    for c in {chave, *filhos_de(chave)}:
        if c in d["liberadas"]:
            d["liberadas"].remove(c)
            _log(d, "revogou", c)
    _gravar(d)


def revogar_tudo():
    """Botao de emergencia."""
    d = _ler()
    d["liberadas"] = []
    _log(d, "revogou", "TUDO")
    _gravar(d)


def aplicar_modo(modo):
    """Aplica o modo escolhido na instalacao e registra o consentimento (inclusive 'nenhum': ai o assistente so conversa)."""
    if modo not in PERFIS:
        raise ValueError(modo)
    d = _ler()
    d["liberadas"] = list(PERFIS[modo])
    _log(d, "modo", modo)
    _gravar(d)
    perfil.registrar_consentimento("granular" if modo == "basico" else modo)


def resumo():
    return [{"chave": c, "titulo": t, "descricao": desc, "risco": r, "liberada": permitido(c)} for c, (t, desc, r) in CATALOGO.items()]
