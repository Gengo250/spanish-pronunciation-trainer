"""Speech-to-Text local com faster-whisper.

Adaptado de `voice-assistant/src/voice_assistant/transcription.py`. Duas mudancas
em relacao ao prototipo: o idioma padrao e espanhol e os timestamps por palavra
vem ligados -- deles saem ritmo, pausas e a ancoragem de cada fonema na palavra
certa.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..audio.utils import to_float32


class TranscriptionError(RuntimeError):
    """Falha ao carregar o modelo ou transcrever o audio."""


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
    """Wrapper fino sobre faster-whisper, com carregamento preguicoso do modelo."""

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
        """Carrega o modelo (baixa do HuggingFace no primeiro uso)."""
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:  # pragma: no cover
                raise TranscriptionError(
                    "faster-whisper nao esta instalado. Rode: uv sync"
                ) from exc
            try:
                self._model = WhisperModel(
                    self.model_size, device=self.device, compute_type=self.compute_type
                )
            except Exception as exc:
                raise TranscriptionError(
                    f"Nao foi possivel carregar o modelo Whisper {self.model_size!r} "
                    f"em {self.device}/{self.compute_type}: {exc}"
                ) from exc
        return self._model

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> Transcript:
        """Transcreve audio int16 ou float32 mono a 16 kHz."""
        if sample_rate != 16000:
            raise TranscriptionError(
                f"faster-whisper espera 16000 Hz, recebi {sample_rate} Hz."
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
            raise TranscriptionError(f"Falha ao transcrever: {exc}") from exc

        return Transcript(
            text=" ".join(t for t in texts if t).strip(),
            language=getattr(info, "language", self.language),
            duration=float(getattr(info, "duration", 0.0)),
            words=words,
        )
