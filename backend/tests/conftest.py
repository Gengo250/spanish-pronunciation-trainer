import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class FakeSynthesizer:
    """Fake synthesizer: counts calls instead of spending credits."""

    def __init__(self, audio: bytes = b"ID3-fake-mp3-bytes") -> None:
        self.audio = audio
        self.calls: list[str] = []

    def synthesize(self, text: str) -> bytes:
        self.calls.append(text)
        return self.audio + text.encode("utf-8")


@pytest.fixture
def fake_synth() -> FakeSynthesizer:
    return FakeSynthesizer()


class FakeTranscript:
    def __init__(self, text, words=None, duration=2.0, language="es"):
        self.text = text
        self.words = words or []
        self.duration = duration
        self.language = language

    def is_empty(self):
        return not self.text.strip()


class FakeWord:
    def __init__(self, text, start, end, probability=0.9):
        self.text, self.start, self.end, self.probability = text, start, end, probability

    @property
    def duration(self):
        return max(0.0, self.end - self.start)


class FakeTranscriber:
    """Controlled transcriber: assessment tests must not depend on Whisper."""

    def __init__(self, text="", words=None):
        self.text, self.words = text, words

    def transcribe(self, audio, sample_rate=16000):
        words = self.words
        if words is None:
            words = [
                FakeWord(w, i * 0.5, i * 0.5 + 0.4) for i, w in enumerate(self.text.split())
            ]
        return FakeTranscript(self.text, words)


@pytest.fixture
def speech_audio():
    """Ruido com energia suficiente para passar a porta de silencio."""
    import numpy as np

    rng = np.random.default_rng(0)
    return (rng.standard_normal(16000 * 2) * 0.1).astype("float32")
