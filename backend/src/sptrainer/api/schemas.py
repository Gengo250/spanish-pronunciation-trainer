"""API response formats.

Kept apart from the internal models because what the browser needs is not what
the pipeline produces. The important case is `AssessmentResponse`: it carries
`capabilities` and `limitations` all the way to the screen, so the interface can
say what was actually measured instead of showing a bare score.
"""

from __future__ import annotations

from pydantic import BaseModel

from ..assessment.g2p import phoneme_word_map, phonemize_text
from ..assessment.types import AssessmentResult
from ..content.models import Flashcard


def _expected_phonemes(text: str, voice: str) -> list[PhonemeResponse]:
    words = phonemize_text(text, voice)
    mapping = phoneme_word_map(words)
    flat = [p for w in words for p in w.phonemes]
    return [
        PhonemeResponse(index=i, phone=p, word_index=mapping[i])
        for i, p in enumerate(flat)
    ]


class PhonemeResponse(BaseModel):
    index: int
    phone: str
    word_index: int
    gop: float | None = None
    status: str = "unknown"


class CardResponse(BaseModel):
    id: str
    text: str
    translation: str
    level: int
    card_type: str
    category: str
    grammar_note: str | None = None
    pronunciation_focus: str | None = None
    example: str | None = None
    example_translation: str | None = None
    tags: list[str] = []
    attempts: int = 0
    best_score: float | None = None
    phonemes: list[PhonemeResponse] = []
    """Expected pronunciation, sound by sound. The interface draws the strip from
    this even before the first attempt."""

    @classmethod
    def of(cls, card: Flashcard, attempts: int = 0, best: float | None = None,
           voice: str = "es-419"):
        return cls(
            id=card.id, text=card.text, translation=card.translation,
            level=card.level.value, card_type=card.card_type.value,
            category=card.category.value, grammar_note=card.grammar_note,
            pronunciation_focus=card.pronunciation_focus, example=card.example,
            example_translation=card.example_translation, tags=card.tags,
            attempts=attempts, best_score=best,
            phonemes=_expected_phonemes(card.text, voice),
        )


class FindingResponse(BaseModel):
    kind: str
    message: str
    evidence: str
    severity: str
    word: str | None = None
    word_index: int | None = None
    score: float | None = None


class WordResponse(BaseModel):
    index: int
    expected: str
    recognized: str | None
    matched: bool
    mean_gop: float | None = None


class ScoresResponse(BaseModel):
    word_accuracy: float
    phoneme_accuracy: float | None
    fluency: float | None
    practice_score: float


class AssessmentResponse(BaseModel):
    card_id: str
    expected_text: str
    recognized_text: str
    no_speech_detected: bool
    audio_duration: float
    scores: ScoresResponse
    words: list[WordResponse]
    phonemes: list[PhonemeResponse]
    findings: list[FindingResponse]
    capabilities: list[str]
    limitations: list[str]
    summary: str = ""

    @classmethod
    def of(cls, card_id: str, result: AssessmentResult, summary: str = ""):
        return cls(
            card_id=card_id,
            expected_text=result.expected_text,
            recognized_text=result.recognized_text,
            no_speech_detected=result.no_speech_detected,
            audio_duration=round(result.audio_duration, 2),
            scores=ScoresResponse(
                word_accuracy=result.scores.word_accuracy,
                phoneme_accuracy=result.scores.phoneme_accuracy,
                fluency=result.scores.fluency,
                practice_score=result.scores.practice_score,
            ),
            words=[
                WordResponse(index=w.index, expected=w.expected, recognized=w.recognized,
                             matched=w.matched, mean_gop=w.mean_gop)
                for w in result.words
            ],
            phonemes=[
                PhonemeResponse(index=p.index, phone=p.phone, word_index=p.word_index,
                                gop=p.gop, status=p.status)
                for p in result.phonemes
            ],
            findings=[
                FindingResponse(kind=f.kind, message=f.message, evidence=f.evidence.value,
                                severity=f.severity.value, word=f.word,
                                word_index=f.word_index, score=f.score)
                for f in result.findings
            ],
            capabilities=sorted(c.value for c in result.capabilities),
            limitations=result.limitations,
            summary=summary,
        )


class ProgressSummary(BaseModel):
    total_attempts: int
    cards_practised: int
    cards_mastered: int
    average_score: float | None
    deck_size: int
