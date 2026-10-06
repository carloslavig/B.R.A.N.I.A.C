# -*- coding: utf-8 -*-
"""Nome e voz do assistente. O nome e OBRIGATORIO. Quem nao consegue pensar em um recebe perguntas sobre seus gostos e sugestoes."""
import re, unicodedata

VOZES = ("feminina", "masculina")
FRASE = "{nome}, tá acordado?"

PERGUNTAS = [
    "Que tipo de música ou filme você mais curte?",
    "Tem algum personagem, time, animal ou lugar de que você gosta muito?",
    "Prefere um nome curto e forte ou algo mais suave e simpático?",
    "Quer algo sério e profissional, ou divertido e descontraído?",
]

# interesse -> nomes (curtos, faceis de o microfone entender e de falar)
SUGESTOES = {
    "musica": {"feminina": ["Melodia", "Aria", "Lira", "Nina"], "masculina": ["Ritmo", "Jazz", "Blues", "Samba"]},
    "tecnologia": {"feminina": ["Ada", "Nova", "Luna", "Íris"], "masculina": ["Turing", "Atlas", "Orion", "Neo"]},
    "natureza": {"feminina": ["Aurora", "Flora", "Brisa", "Serena"], "masculina": ["Rio", "Cedro", "Vento", "Sol"]},
    "esportes": {"feminina": ["Fênix", "Vitória", "Estrela", "Raio"], "masculina": ["Trovão", "Campeão", "Furacão", "Rocky"]},
    "filmes": {"feminina": ["Trinity", "Leia", "Hermione", "Cleo"], "masculina": ["Jarbas", "Frodo", "Morpheus", "Watson"]},
    "games": {"feminina": ["Zelda", "Samus", "Lara", "Aloy"], "masculina": ["Link", "Mario", "Kratos", "Sonic"]},
    "culinaria": {"feminina": ["Canela", "Menta", "Pimenta", "Baunilha"], "masculina": ["Cravo", "Tempero", "Gengibre", "Mel"]},
    "viagens": {"feminina": ["Bússola", "Jornada", "Aurora", "Luana"], "masculina": ["Marco", "Rumo", "Navegador", "Ulisses"]},
    "animais": {"feminina": ["Pantera", "Aura", "Coruja", "Safira"], "masculina": ["Leão", "Falcão", "Lobo", "Tigre"]},
}
PALAVRAS = {
    "musica": r"m[úu]sic|banda|cant|rock|samba|sertanej|rap|funk|violão|viol[aã]o",
    "tecnologia": r"tecnolog|computad|programa|rob[oô]|ia\b|intelig|inform[aá]tica|ti\b",
    "natureza": r"natur|plant|mar\b|praia|cachoeir|montanha|trilha|campo",
    "esportes": r"esport|futebol|time|corrid|academia|gin[aá]stic|lut|basquet|v[oô]lei",
    "filmes": r"filme|s[eé]rie|cinema|netflix|anime|marvel|star",
    "games": r"game|jogo|videogame|play|xbox|minecraft",
    "culinaria": r"cozinh|comida|receita|churrasc|doce|culin[aá]r",
    "viagens": r"viaj|viagem|turismo|aventura|mochil",
    "animais": r"animal|cachorro|gato|pet|bicho|cavalo",
}
RESERVADOS = {"siri", "alexa", "google", "cortana", "chatgpt", "gemini", "claude", "grok", "windows", "ok"}


def _sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def validar_nome(nome):
    """(ok, motivo). O nome precisa ser curto e falavel: o microfone tem que entender quando a pessoa chamar."""
    n = (nome or "").strip()
    if len(n) < 3:
        return False, "o nome precisa ter pelo menos 3 letras"
    if len(n) > 16:
        return False, "escolha um nome mais curto (até 16 letras), fica mais fácil de chamar"
    if not re.fullmatch(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ '\-]*", n):
        return False, "use só letras no nome"
    if _sem_acento(n) in RESERVADOS:
        return False, "esse nome é de outro assistente e confunde o reconhecimento de voz; escolha outro"
    return True, "ok"


def interesses_de(texto):
    t = _sem_acento(texto or "")
    return [k for k, rx in PALAVRAS.items() if re.search(_sem_acento(rx), t)]


def sugerir(texto_gostos, voz, n=6):
    """Sugere nomes a partir do que a pessoa gosta. Sem pistas, mistura categorias."""
    if voz not in VOZES:
        raise ValueError("voz precisa ser feminina ou masculina")
    cats = interesses_de(texto_gostos) or list(SUGESTOES)
    out = []
    for i in range(4):
        for c in cats:
            nomes = SUGESTOES[c][voz]
            if i < len(nomes) and nomes[i] not in out:
                out.append(nomes[i])
    return out[:n]


def frase_de_acordar(nome):
    return FRASE.format(nome=nome.strip())
