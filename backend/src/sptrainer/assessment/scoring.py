"""Scoring formulas. All pure, deterministic and documented.

The project rule: **no number without a reproducible formula**. Every function
here is pure (list in, float out), tested with fixtures, and the arithmetic
appears both in the docstring and in the README.

What these scores are NOT: a proficiency certification. There is no mapping to
CEFR and no claim of equivalence with any official exam. They are a study
instrument -- they let the learner see progress across attempts at the same card.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from .align import align, error_rate
from .types import Scores

# Weights of the practice score. They sum to 1.0 when all three components
# exist; when one is missing the rest are renormalized (see `practice_score`).
WEIGHT_WORD = 0.50
WEIGHT_PHONEME = 0.35
WEIGHT_FLUENCY = 0.15

# Accepted speed range, as a ratio of the ElevenLabs reference.
RATE_COMFORT_LOW = 0.75
RATE_COMFORT_HIGH = 1.30

# Normal pause between words; beyond this it starts weighing on fluency.
PAUSE_BUDGET_S = 0.60

# "ñ" is a letter, not an accented "n". It has to survive diacritic stripping.
_ENYE_SENTINEL = ""


def normalize_word(word: str) -> str:
    """Canonical form for comparing *word identity*.

    Lowercase, no punctuation, no accents. Accents go because Whisper wavers
    between "gustaria" and "gustaría" for the same speech, and that is not a
    pronunciation error. "ñ" is preserved: "ano" and "año" are different words.

    Note: this is only for matching words. G2P always receives the original
    text, accents included, because there the accent defines the stressed
    syllable.
    """
    protected = word.replace("ñ", _ENYE_SENTINEL).replace("Ñ", _ENYE_SENTINEL)
    decomposed = unicodedata.normalize("NFD", protected)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    restored = stripped.replace(_ENYE_SENTINEL, "ñ")
    return "".join(c for c in restored.lower() if c.isalnum() or c == "ñ")


def tokenize_words(text: str) -> list[str]:
    return [w for w in (normalize_word(t) for t in text.split()) if w]


def word_accuracy(expected: str, recognized: str) -> float:
    """`1 - WER`, clamped to [0, 1].

    WER = (substitutions + deletions + insertions) / expected_words,
    computed by Levenshtein alignment over normalized words.
    """
    exp, rec = tokenize_words(expected), tokenize_words(recognized)
    if not exp:
        return 1.0 if not rec else 0.0
    errors = sum(1 for p in align(exp, rec) if p.is_error)
    return max(0.0, min(1.0, 1.0 - errors / len(exp)))


def phoneme_accuracy(expected: list[str], heard: list[str]) -> float:
    """`1 - PER`, after collapsing accent equivalences and geminates."""
    return max(0.0, min(1.0, 1.0 - error_rate(expected, heard)))


def fluency(rate_ratio: float | None, pause_total: float) -> float | None:
    """Fluency score from speed and time spent paused.

    Two components multiplied together:

    - rhythm: 1.0 inside the comfortable range (0.75x to 1.30x of the
      reference), falling off linearly outside it, floored at 0.
    - pauses: `1 - max(0, total_paused - 0.60s) / 3s`, floored at 0.

    Returns `None` when there is no speed reference -- without one the figure
    would be meaningless, and inventing a value would be worse than omitting it.
    """
    if rate_ratio is None:
        return None
    if rate_ratio < RATE_COMFORT_LOW:
        rhythm = max(0.0, rate_ratio / RATE_COMFORT_LOW)
    elif rate_ratio > RATE_COMFORT_HIGH:
        rhythm = max(0.0, 1.0 - (rate_ratio - RATE_COMFORT_HIGH))
    else:
        rhythm = 1.0
    excess = max(0.0, pause_total - PAUSE_BUDGET_S)
    pause_factor = max(0.0, 1.0 - excess / 3.0)
    return max(0.0, min(1.0, rhythm * pause_factor))


def practice_score(
    word: float, phoneme: float | None = None, fluency_score: float | None = None
) -> float:
    """Practice score 0-100: weighted mean of the available components.

    Weights: word 0.50, phoneme 0.35, fluency 0.15. Missing components are
    excluded and the remaining weights renormalized -- an analysis without
    phonemes still produces a score, just one based on what was actually
    measured.
    """
    parts = [(WEIGHT_WORD, word)]
    if phoneme is not None:
        parts.append((WEIGHT_PHONEME, phoneme))
    if fluency_score is not None:
        parts.append((WEIGHT_FLUENCY, fluency_score))
    total_weight = sum(w for w, _ in parts)
    if total_weight <= 0:
        return 0.0
    return round(100.0 * sum(w * v for w, v in parts) / total_weight, 1)


@dataclass
class ScoreInputs:
    expected_text: str
    recognized_text: str
    expected_phonemes: list[str] | None = None
    heard_phonemes: list[str] | None = None
    rate_ratio: float | None = None
    pause_total: float = 0.0


def compute(inputs: ScoreInputs) -> Scores:
    word = word_accuracy(inputs.expected_text, inputs.recognized_text)
    phoneme = (
        phoneme_accuracy(inputs.expected_phonemes, inputs.heard_phonemes)
        if inputs.expected_phonemes is not None and inputs.heard_phonemes is not None
        else None
    )
    flu = fluency(inputs.rate_ratio, inputs.pause_total)
    return Scores(
        word_accuracy=word,
        phoneme_accuracy=phoneme,
        fluency=flu,
        practice_score=practice_score(word, phoneme, flu),
    )
