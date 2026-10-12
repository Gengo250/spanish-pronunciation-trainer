"""Acoustic profile of each card's reference audio.

It exists because of a measured result: an absolute GOP threshold flags errors
in audio known to be correct -- synalepha between words, intervocalic
approximants and unstressed words all have naturally low GOP even in perfect
pronunciation. Over 79 phonemes, the absolute threshold marked 5 false positives
on ElevenLabs' own reference.

The way out is to compare the learner against the reference **of the same
sentence**, sound by sound. What is intrinsically weak is weak on both sides, so
the difference stays near zero and does not become an error. False positives
then fall to zero by construction, with no loss of detection.

The profile is computed once per card and stored next to the cached MP3: it
costs one pass of the model (~160 ms) the first time and nothing afterwards.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from ..audio.decode import decode_to_pcm16
from ..audio.utils import duration_seconds, normalize_for_wav2vec2, speech_span, to_float32

logger = logging.getLogger(__name__)

PROFILE_VERSION = "2"

# Below this there is no rhythm to compare: a single word has no speech rate,
# only duration.
MIN_WORDS_FOR_RATE = 2


@dataclass
class ReferenceProfile:
    gop: list[float] | None = None
    """GOP per expected phoneme in the reference audio."""

    speech_rate: float | None = None
    """Words per second in the reference, used as the fluency baseline."""

    duration: float = 0.0


class ReferenceProfiler:
    """Computes and stores the acoustic profile of each card's reference."""

    def __init__(self, cache, recognizer, settings) -> None:
        self.cache = cache
        self.recognizer = recognizer
        self.settings = settings

    def _profile_path(self, audio_path: Path) -> Path:
        return audio_path.with_suffix(audio_path.suffix + ".profile.json")

    def profile(self, text: str, expected_phonemes: list[str]) -> ReferenceProfile:
        """The card's profile. Returns an empty profile if none of this is possible."""
        eleven = self.settings.elevenlabs
        try:
            reference = self.cache.synthesize(
                text, eleven.voice_id, eleven.model_id, eleven.output_format
            )
        except Exception as exc:  # noqa: BLE001 - assessment carries on without a reference
            logger.info("no reference audio for %r: %s", text[:40], exc)
            return ReferenceProfile()

        path = self._profile_path(reference.path)
        if path.exists():
            try:
                stored = json.loads(path.read_text(encoding="utf-8"))
                if (
                    stored.get("version") == PROFILE_VERSION
                    and len(stored.get("gop") or []) == len(expected_phonemes)
                ):
                    return ReferenceProfile(
                        gop=stored["gop"],
                        speech_rate=stored.get("speech_rate"),
                        duration=stored.get("duration", 0.0),
                    )
            except (OSError, ValueError) as exc:
                logger.warning("unreadable reference profile at %s: %s", path, exc)

        try:
            pcm = decode_to_pcm16(reference.audio)
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not decode the reference: %s", exc)
            return ReferenceProfile()

        duration = duration_seconds(to_float32(pcm))
        # The edge silence has to go: the learner's rhythm comes from Whisper's
        # timestamps, which already ignore it. Measuring the reference by its
        # full duration would make every card look spoken too fast.
        span = speech_span(pcm)
        words = len(text.split())
        # With a single word there is no "rhythm" to compare.
        rate = (words / span) if span > 0 and words >= MIN_WORDS_FOR_RATE else None

        gop = None
        if self.recognizer is not None and expected_phonemes:
            try:
                gop = self.recognizer.recognize(
                    normalize_for_wav2vec2(pcm), expected_phonemes
                ).gop
            except Exception as exc:  # noqa: BLE001
                logger.warning("acoustic profile of the reference failed: %s", exc)

        profile = ReferenceProfile(gop=gop, speech_rate=rate, duration=duration)
        try:
            path.write_text(
                json.dumps(
                    {
                        "version": PROFILE_VERSION,
                        "gop": profile.gop,
                        "speech_rate": profile.speech_rate,
                        "duration": profile.duration,
                    }
                ),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("could not write the reference profile: %s", exc)
        return profile
