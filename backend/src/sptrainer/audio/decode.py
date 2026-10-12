"""Decodificacao do audio que chega do navegador.

O MediaRecorder entrega webm/opus (ou ogg, ou mp4 conforme o browser). Tanto o
faster-whisper quanto o wav2vec2 querem PCM mono 16 kHz, entao o ffmpeg faz a
ponte. E o unico processo externo do caminho de avaliacao.
"""

from __future__ import annotations

import shutil
import subprocess

import numpy as np

SAMPLE_RATE = 16000


class AudioDecodeError(RuntimeError):
    """O audio enviado nao pode ser decodificado."""


def ffmpeg_path() -> str:
    path = shutil.which("ffmpeg")
    if path is None:
        raise AudioDecodeError("ffmpeg was not found on PATH. Install ffmpeg.")
    return path


def decode_to_pcm16(data: bytes, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Converte bytes de audio comprimido em int16 mono na taxa pedida.

    Aceita qualquer formato que o ffmpeg leia (webm/opus, ogg, mp4, wav, mp3).
    Devolve um array 1-D int16.
    """
    if not data:
        raise AudioDecodeError("No audio was received.")

    result = subprocess.run(
        [
            ffmpeg_path(),
            "-hide_banner", "-loglevel", "error",
            "-i", "pipe:0",
            "-f", "s16le", "-acodec", "pcm_s16le",
            "-ar", str(sample_rate), "-ac", "1",
            "pipe:1",
        ],
        input=data,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip() or f"codigo {result.returncode}"
        raise AudioDecodeError(f"ffmpeg could not decode the uploaded audio: {detail}")
    if not result.stdout:
        raise AudioDecodeError("ffmpeg returned empty audio.")
    return np.frombuffer(result.stdout, dtype=np.int16)
