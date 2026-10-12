"""One-sentence summary of the attempt's result.

It lives here, and not in an LLM module, because this is what the learner
actually reads: deterministic text, instant and always faithful to what was
measured. There is no "smart" version of this — a language model could only
restate the same facts, more slowly and with a risk of inventing.
"""

from __future__ import annotations

from .types import AssessmentResult, Evidence


def summarize(result: AssessmentResult) -> str:
    """One sentence about the attempt, assembled from the measured observations."""
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
