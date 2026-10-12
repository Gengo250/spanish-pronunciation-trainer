"""Resumo determinístico da tentativa.

It replaced the LLM-generated summary: same facts, instant, with no risk of
inventing an observation that was never measured.
"""

from sptrainer.assessment.summary import summarize
from sptrainer.assessment.types import (
    AssessmentResult,
    Evidence,
    Finding,
    Scores,
    Severity,
    WordScore,
)


def result_with(findings=None, score=82.0, no_speech=False):
    return AssessmentResult(
        expected_text="Me gustaría aprender español",
        recognized_text="Me gustaría aprender español",
        scores=Scores(word_accuracy=1.0, phoneme_accuracy=0.9, fluency=0.9,
                      practice_score=score),
        words=[WordScore(index=i, expected=w, recognized=w, matched=True)
               for i, w in enumerate(["Me", "gustaría", "aprender", "español"])],
        findings=findings or [],
        no_speech_detected=no_speech,
    )


def test_clean_attempt_is_praised():
    text = summarize(result_with(score=97.0))
    assert "97" in text and "Clear all the way through" in text


def test_missing_word_is_named():
    finding = Finding(kind="word_not_recognized", message="…",
                      evidence=Evidence.TRANSCRIPT, severity=Severity.MAJOR,
                      word="aprender")
    assert "aprender" in summarize(result_with([finding]))


def test_weak_sound_points_at_the_word():
    finding = Finding(kind="weak_phoneme", message="…",
                      evidence=Evidence.PHONEME_ACOUSTIC, severity=Severity.MINOR,
                      word="gustaría", expected="ɾ")
    text = summarize(result_with([finding]))
    assert "gustaría" in text and "slowly" in text


def test_silence_asks_to_record_again():
    assert "microphone" in summarize(result_with(no_speech=True))


def test_summary_only_names_words_that_have_findings():
    """Never names a word without an observation — that was the risk the LLM brought."""
    finding = Finding(kind="weak_phoneme", message="…",
                      evidence=Evidence.PHONEME_ACOUSTIC, severity=Severity.MINOR,
                      word="gustaría", expected="ɾ")
    text = summarize(result_with([finding]))
    assert "español" not in text and "aprender" not in text


def test_score_is_always_present():
    assert "55" in summarize(result_with(score=55.0))
