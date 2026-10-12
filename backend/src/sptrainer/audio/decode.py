"""Decoding the audio that arrives from the browser.

MediaRecorder delivers webm/opus (or ogg, or mp4 depending on the browser).
Both faster-whisper and wav2vec2 want mono 16 kHz PCM, so ffmpeg bridges the
gap. It is the only external process in the assessment path.
"""

from __future__ import annotations

import shutil
import subprocess

import numpy as np

SAMPLE_RATE = 16000


class AudioDecodeError(RuntimeError):
    """The uploaded audio could not be decoded."""


def ffmpeg_path() -> str:
    path = shutil.which("ffmpeg")
    if path is None:
        raise AudioDecodeError("ffmpeg was not found on PATH. Install ffmpeg.")
    return path


def decode_to_pcm16(data: bytes, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Converts compressed audio bytes into mono int16 at the requested rate.

    Accepts any format ffmpeg can read (webm/opus, ogg, mp4, wav, mp3).
    Returns a 1-D int16 array.
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
        detail = result.stderr.decode("utf-8", "replace").strip() or f"exit code {result.returncode}"
        raise AudioDecodeError(f"ffmpeg could not decode the uploaded audio: {detail}")
    if not result.stdout:
        raise AudioDecodeError("ffmpeg returned empty audio.")
    return np.frombuffer(result.stdout, dtype=np.int16)
