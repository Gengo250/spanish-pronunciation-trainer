"""Local speech-to-text with faster-whisper.

Adapted from `voice-assistant/src/voice_assistant/transcription.py`. Two changes
from the prototype: the default language is Spanish, and per-word timestamps are
on -- rhythm, pauses and the anchoring of each phoneme to the right word all
come from them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..audio.utils import to_float32


class TranscriptionError(RuntimeError):
    """Failure loading the model or transcribing the audio."""


@dataclass
class Word:
    text: str
    start: float
    end: float
    probability: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class Transcript:
    text: str
    language: str
    duration: float
    words: list[Word] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.text.strip()


class Transcriber:
    """Thin wrapper over faster-whisper, with lazy model loading."""

    def __init__(
        self,
        model_size: str = "small",
        device: str = "cpu",
        compute_type: str = "int8",
        language: str = "es",
    ) -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self._model = None

    def load(self):
        """Loads the model (downloads from HuggingFace on first use)."""
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:  # pragma: no cover
                raise TranscriptionError(
                    "faster-whisper is not installed. Run: uv sync"
                ) from exc
            try:
                self._model = WhisperModel(
                    self.model_size, device=self.device, compute_type=self.compute_type
                )
            except Exception as exc:
                raise TranscriptionError(
                    f"Could not load the Whisper model {self.model_size!r} "
                    f"on {self.device}/{self.compute_type}: {exc}"
                ) from exc
        return self._model

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> Transcript:
        """Transcribes mono int16 or float32 audio at 16 kHz."""
        if sample_rate != 16000:
            raise TranscriptionError(
                f"faster-whisper expects 16000 Hz, got {sample_rate} Hz."
            )
        if audio.size == 0:
            return Transcript(text="", language=self.language, duration=0.0)

        model = self.load()
        samples = to_float32(audio)
        try:
            segments, info = model.transcribe(
                samples,
                language=self.language or None,
                beam_size=5,
                word_timestamps=True,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 400},
            )
            texts: list[str] = []
            words: list[Word] = []
            for segment in segments:
                texts.append(segment.text.strip())
                for w in getattr(segment, "words", None) or []:
                    words.append(
                        Word(
                            text=w.word.strip(),
                            start=float(w.start),
                            end=float(w.end),
                            probability=float(getattr(w, "probability", 0.0)),
                        )
                    )
        except Exception as exc:
            raise TranscriptionError(f"Transcription failed: {exc}") from exc

        return Transcript(
            text=" ".join(t for t in texts if t).strip(),
            language=getattr(info, "language", self.language),
            duration=float(getattr(info, "duration", 0.0)),
            words=words,
        )
