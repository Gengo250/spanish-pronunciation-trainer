"""Resumo em uma frase do resultado da tentativa.

Vive aqui, e não num módulo de LLM, porque é isto que o aluno lê de verdade: um
texto determinístico, instantâneo e sempre fiel ao que foi medido. Não há versão
"inteligente" disto — um modelo de linguagem só poderia reescrever os mesmos
fatos, mais devagar e com risco de inventar.
"""

from __future__ import annotations

from .types import AssessmentResult, Evidence


def summarize(result: AssessmentResult) -> str:
    """Uma frase sobre a tentativa, montada a partir das observações medidas."""
    if result.no_speech_detected:
        return "We did not hear anything. Check your microphone and record again."

    score = result.scores.practice_score
    if not result.findings:
        return f"Clear all the way through — {score:.0f} out of 100."

    sounds = [f for f in result.findings if f.evidence is Evidence.PHONEME_ACOUSTIC]
    missing = [f for f in result.findings if f.kind == "word_not_recognized"]

    parts = [f"{score:.0f} out of 100."]
    if missing:
        words = ", ".join(f"“{f.word}”" for f in missing if f.word)
        parts.append(f"{words} did not come through.")
    if sounds:
        words = ", ".join(f"“{f.word}”" for f in sounds if f.word)
        parts.append(f"Worth repeating {words} slowly.")
    if not missing and not sounds:
        parts.append("Adjust your pacing and try again.")
    return " ".join(parts)
