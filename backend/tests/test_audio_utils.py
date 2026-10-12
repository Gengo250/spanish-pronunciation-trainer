"""Medidas de audio -- em especial o span de fala, que calibra a fluencia."""

import numpy as np
import pytest

from sptrainer.audio.utils import rms_level, speech_span, to_float32


def tone(seconds, sample_rate=16000, amplitude=0.4):
    t = np.linspace(0, seconds, int(sample_rate * seconds), endpoint=False)
    return (np.sin(2 * np.pi * 150 * t) * amplitude).astype(np.float32)


def silence(seconds, sample_rate=16000):
    return np.zeros(int(sample_rate * seconds), dtype=np.float32)


def test_span_ignores_leading_and_trailing_silence():
    """O bug real: o MP3 da ElevenLabs tem silencio nas bordas e o Whisper nao.

    Medir a referencia pela duracao cheia fazia toda carta parecer falada rapido
    demais -- inclusive o proprio audio de referencia contra ele mesmo.
    """
    clip = np.concatenate([silence(0.5), tone(1.0), silence(0.8)])
    assert len(clip) / 16000 == pytest.approx(2.3, abs=0.01)
    assert speech_span(clip) == pytest.approx(1.0, abs=0.08)


def test_span_of_continuous_speech_is_the_whole_clip():
    assert speech_span(tone(1.5)) == pytest.approx(1.5, abs=0.08)


def test_span_of_silence_is_zero():
    assert speech_span(silence(1.0)) == 0.0


def test_span_of_empty_audio_is_zero():
    assert speech_span(np.zeros(0, dtype=np.float32)) == 0.0


def test_span_is_amplitude_independent():
    """O limiar e relativo ao proprio audio: estudio e microfone caseiro valem igual."""
    loud = np.concatenate([silence(0.3), tone(1.0, amplitude=0.9), silence(0.3)])
    quiet = np.concatenate([silence(0.3), tone(1.0, amplitude=0.05), silence(0.3)])
    assert speech_span(loud) == pytest.approx(speech_span(quiet), abs=0.08)


def test_int16_and_float32_agree():
    clip = np.concatenate([silence(0.2), tone(0.8), silence(0.2)])
    as_int16 = (clip * 32767).astype(np.int16)
    assert speech_span(as_int16) == pytest.approx(speech_span(clip), abs=0.08)
    assert rms_level(as_int16) == pytest.approx(rms_level(clip), abs=0.01)


def test_to_float32_is_idempotent():
    clip = tone(0.1)
    assert np.allclose(to_float32(to_float32(clip)), clip)
