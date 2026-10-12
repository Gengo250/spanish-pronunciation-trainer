"""In-memory audio utilities.

Reused from the `voice-assistant/src/voice_assistant/audio_input.py` prototype.
Microphone capture does NOT come along: in the trainer the browser does the
recording (MediaRecorder), so `Recorder` and `record_until_enter` were left
behind and `sounddevice` stopped being a dependency.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

CHANNELS = 1
SAMPLE_RATE = 16000


def duration_seconds(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> float:
    return len(audio) / float(sample_rate) if sample_rate else 0.0


def rms_level(audio: np.ndarray) -> float:
    """Normalized RMS level (0.0 to 1.0). Useful for detecting a silent mic."""
    if audio.size == 0:
        return 0.0
    if audio.dtype == np.float32:
        return float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
    return float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)) / 32768.0)


def to_float32(audio: np.ndarray) -> np.ndarray:
    """Converts int16 -> float32 in [-1, 1], the format the models expect."""
    if audio.dtype == np.float32:
        return audio.reshape(-1)
    return (audio.astype(np.float32) / 32768.0).reshape(-1)


def normalize_for_wav2vec2(audio: np.ndarray) -> np.ndarray:
    """Zero mean and unit variance, as wav2vec2 expects on its input."""
    samples = to_float32(audio)
    if samples.size == 0:
        return samples
    return (samples - samples.mean()) / (samples.std() + 1e-7)


def speech_span(
    audio: np.ndarray,
    sample_rate: int = SAMPLE_RATE,
    frame_ms: float = 20.0,
    threshold_ratio: float = 0.08,
) -> float:
    """Seconds between the start and the end of speech, less the edge silence.

    This measures the reference audio the same way we measure the learner. The
    learner's rhythm comes from Whisper's timestamps, which already ignore the
    silence; if the reference were measured by the MP3's full duration the two
    quantities would not be comparable and every card would look spoken too fast.

    The threshold is relative to the loudest frame of the audio itself, so it
    works for a home recording as well as for studio audio.
    """
    samples = to_float32(audio)
    if samples.size == 0:
        return 0.0
    frame = max(1, int(sample_rate * frame_ms / 1000.0))
    usable = samples.size - (samples.size % frame)
    if usable < frame:
        return duration_seconds(samples, sample_rate)
    frames = samples[:usable].reshape(-1, frame)
    energy = np.sqrt((frames.astype(np.float64) ** 2).mean(axis=1))
    peak = energy.max()
    if peak <= 0:
        return 0.0
    loud = np.flatnonzero(energy >= peak * threshold_ratio)
    if loud.size == 0:
        return 0.0
    return float((loud[-1] - loud[0] + 1) * frame / sample_rate)


def save_wav(audio: np.ndarray, path: str | Path, sample_rate: int = SAMPLE_RATE) -> Path:
    """Writes the audio as 16-bit PCM WAV (useful for debugging and test fixtures)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if audio.dtype == np.float32:
        audio = np.clip(audio, -1.0, 1.0) * 32767.0
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(CHANNELS)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(audio.astype(np.int16).tobytes())
    return path
