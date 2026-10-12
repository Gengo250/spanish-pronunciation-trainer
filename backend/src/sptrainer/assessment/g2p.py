"""Grapheme to phoneme for Spanish, via espeak-ng.

Spanish spelling is near-phonemic, so espeak-ng is a reliable, deterministic
reference generator -- no asking an LLM for phonemes.

Two lessons that came from measurement, not from guessing:

1. **G2P is done word by word.** Given a whole sentence, espeak runs through the
   punctuation and glues neighbouring words together ("cansado, decidio" ->
   `kansaðodeθiðjo`). Word by word is also what lets each phoneme be anchored to
   the right word.
2. **The only multi-character phoneme Spanish uses in practice is `tʃ`** (ch).
   Checked against muchacho, coche, reloj, extra, ciudad and company.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache

# Marks espeak adds that are not phonemes.
STRESS_MARKS = "ˈˌ"
LENGTH_AND_TIES = ".ːˑ‿|"
PUNCTUATION = "¿?¡!.,;:«»\"'()[]—–…"

# Phonemes longer than one character, in the order they are tried.
MULTICHAR_PHONES = ("tʃ", "dʒ")


class G2PError(RuntimeError):
    """espeak-ng missing or unable to transcribe."""


@dataclass
class WordPhonemes:
    word: str
    """The word as it appears on the flashcard, without punctuation."""

    phonemes: list[str] = field(default_factory=list)
    stressed_index: int | None = None
    """Index, within `phonemes`, of the nucleus of the stressed syllable."""


def espeak_path() -> str:
    path = shutil.which("espeak-ng") or shutil.which("espeak")
    if path is None:
        raise G2PError("espeak-ng not found. Install the `espeak-ng` package.")
    return path


def strip_punctuation(word: str) -> str:
    return word.strip(PUNCTUATION).strip()


def tokenize_ipa(ipa: str) -> tuple[list[str], int | None]:
    """Splits the espeak string into phonemes and points at the stressed vowel.

    Returns `(phonemes, stressed_index)`. Primary stress (`ˈ`) marks the syllable
    that follows, so the index points at the first vowel after the mark.
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
        detail = result.stderr.strip() or f"exit code {result.returncode}"
        raise G2PError(f"espeak-ng failed on {word!r}: {detail}")
    return result.stdout.strip()


def phonemize_word(word: str, voice: str = "es-419") -> WordPhonemes:
    clean = strip_punctuation(word)
    if not clean:
        return WordPhonemes(word="", phonemes=[])
    ipa = _espeak_word(clean, voice)
    phones, stressed = tokenize_ipa(ipa)
    return WordPhonemes(word=clean, phonemes=phones, stressed_index=stressed)


def phonemize_text(text: str, voice: str = "es-419") -> list[WordPhonemes]:
    """Phonemizes word by word, preserving the flashcard's order."""
    out: list[WordPhonemes] = []
    for raw in text.split():
        wp = phonemize_word(raw, voice)
        if wp.phonemes:
            out.append(wp)
    return out


def flatten(words: list[WordPhonemes]) -> list[str]:
    return [p for w in words for p in w.phonemes]


def phoneme_word_map(words: list[WordPhonemes]) -> list[int]:
    """For each phoneme in the flattened sequence, the index of the word it came from."""
    return [i for i, w in enumerate(words) for _ in w.phonemes]
