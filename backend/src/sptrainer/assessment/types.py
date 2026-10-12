"""The pronunciation assessment contract.

The rule that organizes this module: **every claim carries the evidence that
supports it**. If the acoustic phoneme model is disabled, missing or fails,
phonetic-level conclusions simply do not exist in the result -- they are not
guessed, nor filled in by estimate.

`AssessmentResult.capabilities` says what is actually running, and `limitations`
says, in plain language, what this analysis cannot claim.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Evidence(str, Enum):
    """Where the conclusion came from. Without it, no finding enters the result."""

    TRANSCRIPT = "transcript"
    """Comparison of the text Whisper recognized against the expected text."""

    PHONEME_ACOUSTIC = "phoneme_acoustic"
    """wav2vec2 per-phoneme posteriors aligned to the expected sequence (GOP)."""

    PROSODY = "prosody"
    """Duration, rhythm and pauses measured on the per-word timestamps."""


class Capability(str, Enum):
    TRANSCRIPT_MATCH = "transcript_match"
    PHONEME_ANALYSIS = "phoneme_analysis"
    PROSODY_ANALYSIS = "prosody_analysis"


class Severity(str, Enum):
    INFO = "info"
    MINOR = "minor"
    MAJOR = "major"


@dataclass
class Finding:
    """A single, traceable observation about the learner's speech."""

    kind: str
    message: str
    evidence: Evidence
    severity: Severity = Severity.INFO
    word: str | None = None
    word_index: int | None = None
    expected: str | None = None
    heard: str | None = None
    score: float | None = None
    """Raw value behind the conclusion (GOP, probability, seconds...)."""


@dataclass
class PhonemeScore:
    """An expected sound and how well the audio supported it.

    This is what the interface draws in the phoneme strip. `status` is resolved
    here so the screen does not have to reimplement the thresholds -- and so that
    `unknown` stays `unknown`, instead of becoming "bad" by omission.
    """

    index: int
    phone: str
    word_index: int
    gop: float | None = None
    status: str = "unknown"
    """strong | fair | weak | unknown"""


@dataclass
class WordScore:
    index: int
    expected: str
    recognized: str | None
    matched: bool
    phoneme_accuracy: float | None = None
    mean_gop: float | None = None
    start: float | None = None
    end: float | None = None


@dataclass
class Scores:
    """Numbers, all reproducible. The formulas are in scoring.py and the README."""

    word_accuracy: float
    phoneme_accuracy: float | None = None
    fluency: float | None = None
    practice_score: float = 0.0


@dataclass
class AssessmentResult:
    expected_text: str
    recognized_text: str
    scores: Scores
    words: list[WordScore] = field(default_factory=list)
    phonemes: list[PhonemeScore] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    capabilities: set[Capability] = field(default_factory=set)
    limitations: list[str] = field(default_factory=list)
    no_speech_detected: bool = False
    audio_duration: float = 0.0

    def findings_by_evidence(self, evidence: Evidence) -> list[Finding]:
        return [f for f in self.findings if f.evidence is evidence]

    @property
    def has_phoneme_analysis(self) -> bool:
        return Capability.PHONEME_ANALYSIS in self.capabilities
