"""Utilitarios de audio em memoria.

Reaproveitados do prototipo `voice-assistant/src/voice_assistant/audio_input.py`.
A captura de microfone NAO vem junto: no trainer quem grava e o navegador
(MediaRecorder), entao `Recorder` e `record_until_enter` ficaram para tras e o
`sounddevice` deixou de ser dependencia.
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
    """Nivel RMS normalizado (0.0 a 1.0). Util para detectar microfone mudo."""
    if audio.size == 0:
        return 0.0
    if audio.dtype == np.float32:
        return float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
    return float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)) / 32768.0)


def to_float32(audio: np.ndarray) -> np.ndarray:
    """Converte int16 -> float32 em [-1, 1], formato esperado pelos modelos."""
    if audio.dtype == np.float32:
        return audio.reshape(-1)
    return (audio.astype(np.float32) / 32768.0).reshape(-1)


def normalize_for_wav2vec2(audio: np.ndarray) -> np.ndarray:
    """Media zero e variancia unitaria, como o wav2vec2 espera na entrada."""
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
    """Segundos entre o inicio e o fim da fala, descontando o silencio das bordas.

    Serve para medir o audio de referencia do mesmo jeito que medimos o aluno. O
    ritmo do aluno sai dos timestamps do Whisper, que ja ignoram o silencio; se a
    referencia fosse medida pela duracao cheia do MP3, as duas grandezas nao
    seriam comparaveis e toda carta pareceria falada rapido demais.

    O limiar e relativo ao quadro mais forte do proprio audio, entao funciona
    tanto para a gravacao caseira quanto para o audio de estudio.
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
    """Grava o audio em WAV PCM 16 bits (util para depuracao e fixtures de teste)."""
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
