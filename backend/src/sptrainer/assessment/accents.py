"""Legitimate Spanish variation, and model artifacts, that are NOT errors.

Without this layer the assessor fails correct pronunciation. In the M0 spike,
applying these equivalences dropped the PER of correct natural speech from 18.6%
to 3.9%, while heavily accented speech barely moved (60.0% -> 58.7%): it removes
a representation artifact without erasing real error.

**Equivalence here is NOT transitive, and that is deliberate.** The temptation is
to union the groups and work with one canonical representative per class. That
breaks: /s/~/h/ holds (coda aspiration) and /x/~/h/ holds (Caribbean jota), but
chaining the two would make "casa" and "caja" indistinguishable. For the same
reason /n/~/ŋ/ is in and /n/~/m/ is out -- "cama" and "cana" are a real minimal
pair.

Three origins, kept apart because they have different consequences:

1. `ALLOPHONIC`     -- mandatory Spanish allophony. Penalizing it would penalize
                       the learner for speaking Spanish correctly.
2. `REGIONAL`       -- equally valid variants (seseo/distincion, yeismo).
3. `MODEL_ARTIFACT` -- measured limitation of the recognizer, not of the speech.
                       Counts toward the score, but never becomes per-sound
                       feedback.
"""

from __future__ import annotations

from itertools import combinations

# --- 1. Mandatory positional allophony of Spanish -------------------------
ALLOPHONIC: tuple[tuple[str, ...], ...] = (
    ("b", "β"),        # intervocalic: "lobo"
    ("d", "ð"),        # intervocalic: "nada"
    ("ɡ", "ɣ"),        # intervocalic: "lago"
    ("n", "ŋ"),        # velar assimilation: "tengo". /m/ stays OUT (cama != cana)
)

# --- 2. Valid regional variation ------------------------------------------
REGIONAL: tuple[tuple[str, ...], ...] = (
    ("s", "θ"),        # seseo (Americas) vs distincion (Spain): "gracias"
    ("ʝ", "ʎ"),        # yeismo vs lleismo: "llave"
    ("ʝ", "j"),        # approximant realization of /ʝ/: "yo"
    ("s", "h"),        # coda /s/ aspiration: "ehto" for "esto"
    ("x", "h"),        # Caribbean/Andalusian jota: "trabajo"
)

# --- 3. Measured recognizer artifacts -------------------------------------
MODEL_ARTIFACT: tuple[tuple[str, ...], ...] = (
    ("ɾ", "r"),        # the model writes the trill as a doubled tap
    ("x", "k"),        # jota heard as /k/  (see JOTA_CONFUSION)
)


def _pairs(*groups: tuple[tuple[str, ...], ...]) -> frozenset[frozenset[str]]:
    """Unordered pairs. No transitive closure -- see the module docstring."""
    out: set[frozenset[str]] = set()
    for group_set in groups:
        for group in group_set:
            for a, b in combinations(group, 2):
                out.add(frozenset((a, b)))
    return frozenset(out)


ALLOPHONIC_PAIRS = _pairs(ALLOPHONIC)
REGIONAL_PAIRS = _pairs(REGIONAL)
ARTIFACT_PAIRS = _pairs(MODEL_ARTIFACT)
EQUIVALENT_PAIRS = ALLOPHONIC_PAIRS | REGIONAL_PAIRS | ARTIFACT_PAIRS

JOTA_CONFUSION = frozenset({"x", "k"})
"""Pair the recognizer confuses on its own.

It counts toward the score -- otherwise every word with a jota loses points for
no reason -- but never becomes the claim "you said K instead of J": in that
direction there is no way to separate learner error from model error.
"""

GEMINATE_COLLAPSE = frozenset({"ɾ", "r"})
"""Phonemes where adjacent repetition is notation, not an extra sound."""


def equivalent(a: str, b: str) -> bool:
    """True when two phonemes must not count as an error against each other."""
    return a == b or frozenset((a, b)) in EQUIVALENT_PAIRS


def equivalence_reason(a: str, b: str) -> str | None:
    """Why these two phonemes are not an error. None when they genuinely differ."""
    if a == b:
        return "identical"
    pair = frozenset((a, b))
    if pair in ALLOPHONIC_PAIRS:
        return "allophonic"
    if pair in REGIONAL_PAIRS:
        return "regional"
    if pair in ARTIFACT_PAIRS:
        return "model_artifact"
    return None


def is_model_artifact(expected: str, heard: str) -> bool:
    """True when the swap is a known recognizer failure, not the learner's."""
    return frozenset((expected, heard)) in ARTIFACT_PAIRS and expected != heard


def collapse_geminates(phones: list[str]) -> list[str]:
    """Collapses repeated taps/trills: the model writes `r` as `ɾɾ`."""
    out: list[str] = []
    for p in phones:
        if out and out[-1] == p and p in GEMINATE_COLLAPSE:
            continue
        out.append(p)
    return out
