"""Rhythm, pauses and intonation.

Everything here comes from two measured sources: Whisper's per-word timestamps
and the waveform. No conclusion is inferred from "it seems" -- if the signal
does not support it, the function returns `None` and the caller produces no
finding.

On intonation: F0 comes from frame-by-frame autocorrelation, which is reliable
enough to say whether the end of the utterance **rises or falls** (what matters
for questions in Spanish), and insufficient for anything finer. The module
exposes only the direction, on purpose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np

# Silence between words from which it already reads as a perceived pause.
PAUSE_THRESHOLD_S = 0.30

# F0 range considered human voice. Outside it is noise or an octave error.
F0_MIN_HZ = 70.0
F0_MAX_HZ = 400.0

FRAME_MS = 40.0
HOP_MS = 20.0

# Minimum correlation for a frame to count as voiced.
VOICING_THRESHOLD = 0.35


class Contour(str, Enum):
    RISING = "rising"
    FALLING = "falling"
    FLAT = "flat"
    UNKNOWN = "unknown"
    """Audio without enough voiced frames to claim anything."""


@dataclass
class Pause:
    after_word: str
    after_index: int
    duration: float


@dataclass
class ProsodyResult:
    speech_rate: float | None = None
    """Words per second of speech (excludes leading and trailing silence)."""

    articulation_duration: float = 0.0
    pauses: list[Pause] = field(default_factory=list)
    final_contour: Contour = Contour.UNKNOWN
    f0_median: float | None = None
    reference_rate: float | None = None
    """Words per second in the ElevenLabs reference audio, when it exists."""

    @property
    def rate_ratio(self) -> float | None:
        """The learner's speed divided by the reference's. 1.0 = the same."""
        if self.speech_rate and self.reference_rate:
            return self.speech_rate / self.reference_rate
        return None


# A single word has duration, not rhythm. Comparing speech rate needs at least
# two words.
MIN_WORDS_FOR_RATE = 2


def speech_rate(words, total_duration: float | None = None) -> tuple[float | None, float]:
    """Words per second between the start of the first and the end of the last word."""
    if len(words) < MIN_WORDS_FOR_RATE:
        return None, 0.0
    span = words[-1].end - words[0].start
    if span <= 0:
        return None, 0.0
    return len(words) / span, span


def detect_pauses(words, threshold: float = PAUSE_THRESHOLD_S) -> list[Pause]:
    """Silences between words above the threshold."""
    pauses: list[Pause] = []
    for i in range(len(words) - 1):
        gap = words[i + 1].start - words[i].end
        if gap >= threshold:
            pauses.append(Pause(after_word=words[i].text, after_index=i, duration=gap))
    return pauses


def f0_contour(
    audio: np.ndarray,
    sample_rate: int = 16000,
    frame_ms: float = FRAME_MS,
    hop_ms: float = HOP_MS,
) -> np.ndarray:
    """Per-frame F0 via autocorrelation. `nan` on unvoiced frames."""
    samples = np.asarray(audio, dtype=np.float64).reshape(-1)
    if samples.size == 0:
        return np.empty(0)

    frame = int(sample_rate * frame_ms / 1000.0)
    hop = int(sample_rate * hop_ms / 1000.0)
    if samples.size < frame:
        return np.empty(0)

    min_lag = max(1, int(sample_rate / F0_MAX_HZ))
    max_lag = min(frame - 1, int(sample_rate / F0_MIN_HZ))
    if max_lag <= min_lag:
        return np.empty(0)

    out: list[float] = []
    for start in range(0, samples.size - frame + 1, hop):
        window = samples[start : start + frame]
        window = window - window.mean()
        energy = np.dot(window, window)
        if energy <= 1e-9:
            out.append(np.nan)
            continue
        corr = np.correlate(window, window, mode="full")[frame - 1 :]
        segment = corr[min_lag : max_lag + 1]
        if segment.size == 0:
            out.append(np.nan)
            continue
        peak = int(segment.argmax())
        if corr[0] <= 0 or segment[peak] / corr[0] < VOICING_THRESHOLD:
            out.append(np.nan)
            continue
        out.append(sample_rate / float(min_lag + peak))
    return np.asarray(out)


def final_contour(f0: np.ndarray, tail_fraction: float = 0.30) -> tuple[Contour, float | None]:
    """Direction of F0 over the final stretch. Returns `(direction, global_median)`.

    Compares the median of the last `tail_fraction` of voiced frames against the
    earlier ones. Needs at least 6 voiced frames -- below that it returns
    UNKNOWN instead of guessing.
    """
    voiced = f0[~np.isnan(f0)] if f0.size else np.empty(0)
    if voiced.size < 6:
        return Contour.UNKNOWN, (float(np.median(voiced)) if voiced.size else None)

    median = float(np.median(voiced))
    split = max(1, int(voiced.size * (1.0 - tail_fraction)))
    head, tail = voiced[:split], voiced[split:]
    if head.size == 0 or tail.size == 0:
        return Contour.UNKNOWN, median

    ratio = float(np.median(tail)) / float(np.median(head))
    if ratio >= 1.10:
        return Contour.RISING, median
    if ratio <= 0.90:
        return Contour.FALLING, median
    return Contour.FLAT, median


def analyse(
    audio: np.ndarray,
    words,
    sample_rate: int = 16000,
    reference_rate: float | None = None,
) -> ProsodyResult:
    rate, span = speech_rate(words)
    contour, median = final_contour(f0_contour(audio, sample_rate))
    return ProsodyResult(
        speech_rate=rate,
        articulation_duration=span,
        pauses=detect_pauses(words),
        final_contour=contour,
        f0_median=median,
        reference_rate=reference_rate,
    )
