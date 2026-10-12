"""Grafema para fonema em espanhol, via espeak-ng.

O espanhol tem ortografia quase fonemica, entao o espeak-ng e um gerador de
referencia confiavel e deterministico -- nada de pedir fonemas para um LLM.

Duas licoes que vieram da medicao, nao do palpite:

1. **G2P e feito palavra por palavra.** Em frase inteira o espeak atravessa a
   pontuacao e cola palavras vizinhas ("cansado, decidio" -> `kansaðodeθiðjo`).
   Palavra a palavra tambem e o que permite ancorar cada fonema na palavra certa.
2. **O unico fonema multi-caractere que o espanhol usa na pratica e `tʃ`** (ch).
   Conferido contra muchacho, coche, reloj, extra, ciudad e companhia.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache

# Marcas que o espeak adiciona e que nao sao fonemas.
STRESS_MARKS = "ˈˌ"
LENGTH_AND_TIES = ".ːˑ‿|"
PUNCTUATION = "¿?¡!.,;:«»\"'()[]—–…"

# Fonemas de mais de um caractere, em ordem de tentativa.
MULTICHAR_PHONES = ("tʃ", "dʒ")


class G2PError(RuntimeError):
    """espeak-ng ausente ou incapaz de transcrever."""


@dataclass
class WordPhonemes:
    word: str
    """A palavra como aparece no flashcard, sem pontuacao."""

    phonemes: list[str] = field(default_factory=list)
    stressed_index: int | None = None
    """Indice, dentro de `phonemes`, do nucleo da silaba tonica."""


def espeak_path() -> str:
    path = shutil.which("espeak-ng") or shutil.which("espeak")
    if path is None:
        raise G2PError("espeak-ng nao encontrado. Instale o pacote `espeak-ng`.")
    return path


def strip_punctuation(word: str) -> str:
    return word.strip(PUNCTUATION).strip()


def tokenize_ipa(ipa: str) -> tuple[list[str], int | None]:
    """Quebra a string do espeak em fonemas e aponta a vogal tonica.

    Devolve `(fonemas, indice_tonico)`. O acento primario (`ˈ`) marca a silaba
    seguinte, entao o indice aponta para a primeira vogal depois da marca.
    """
    phones: list[str] = []
    stressed_index: int | None = None
    pending_stress = False
    i = 0
    while i < len(ipa):
        ch = ipa[i]
        if ch in STRESS_MARKS:
            pending_stress = ch == "ˈ"
            i += 1
            continue
        if ch in LENGTH_AND_TIES or ch.isspace():
            i += 1
            continue
        for multi in MULTICHAR_PHONES:
            if ipa.startswith(multi, i):
                phones.append(multi)
                i += len(multi)
                break
        else:
            phones.append(ch)
            i += 1
        if pending_stress and phones[-1] in VOWELS:
            stressed_index = len(phones) - 1
            pending_stress = False
    return phones, stressed_index


VOWELS = frozenset("aeiouɛɔəɐʊɪ")


@lru_cache(maxsize=4096)
def _espeak_word(word: str, voice: str) -> str:
    result = subprocess.run(
        [espeak_path(), "-v", voice, "--ipa", "-q", word],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or f"codigo {result.returncode}"
        raise G2PError(f"espeak-ng falhou em {word!r}: {detail}")
    return result.stdout.strip()


def phonemize_word(word: str, voice: str = "es-419") -> WordPhonemes:
    clean = strip_punctuation(word)
    if not clean:
        return WordPhonemes(word="", phonemes=[])
    ipa = _espeak_word(clean, voice)
    phones, stressed = tokenize_ipa(ipa)
    return WordPhonemes(word=clean, phonemes=phones, stressed_index=stressed)


def phonemize_text(text: str, voice: str = "es-419") -> list[WordPhonemes]:
    """Fonemiza palavra por palavra, preservando a ordem do flashcard."""
    out: list[WordPhonemes] = []
    for raw in text.split():
        wp = phonemize_word(raw, voice)
        if wp.phonemes:
            out.append(wp)
    return out


def flatten(words: list[WordPhonemes]) -> list[str]:
    return [p for w in words for p in w.phonemes]


def phoneme_word_map(words: list[WordPhonemes]) -> list[int]:
    """Para cada fonema da sequencia achatada, o indice da palavra que o gerou."""
    return [i for i, w in enumerate(words) for _ in w.phonemes]
