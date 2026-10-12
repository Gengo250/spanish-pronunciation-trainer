"""Ritmo, pausas e entonacao.

Tudo aqui sai de duas fontes medidas: os timestamps por palavra do Whisper e a
forma de onda. Nenhuma conclusao e inferida de "parece" -- se o sinal nao
sustenta, a funcao devolve `None` e quem chama nao gera finding.

Sobre entonacao: a F0 sai de autocorrelacao quadro a quadro, que e confiavel o
bastante para dizer se o final do enunciado **sobe ou desce** (o que importa para
perguntas em espanhol), e insuficiente para qualquer afirmacao mais fina. O
modulo so expoe a direcao, de proposito.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np

# Silencio entre palavras a partir do qual ja e pausa percebida.
PAUSE_THRESHOLD_S = 0.30

# Faixa de F0 considerada voz humana. Fora disso e ruido ou erro de oitava.
F0_MIN_HZ = 70.0
F0_MAX_HZ = 400.0

FRAME_MS = 40.0
HOP_MS = 20.0

# Correlacao minima para considerar o quadro sonoro (voiced).
VOICING_THRESHOLD = 0.35


class Contour(str, Enum):
    RISING = "rising"
    FALLING = "falling"
    FLAT = "flat"
    UNKNOWN = "unknown"
    """Audio sem quadros sonoros suficientes para afirmar qualquer coisa."""


@dataclass
class Pause:
    after_word: str
    after_index: int
    duration: float


@dataclass
class ProsodyResult:
    speech_rate: float | None = None
    """Palavras por segundo de fala (exclui silencio inicial e final)."""

    articulation_duration: float = 0.0
    pauses: list[Pause] = field(default_factory=list)
    final_contour: Contour = Contour.UNKNOWN
    f0_median: float | None = None
    reference_rate: float | None = None
    """Palavras por segundo no audio de referencia da ElevenLabs, quando existe."""

    @property
    def rate_ratio(self) -> float | None:
        """Velocidade do aluno dividida pela da referencia. 1.0 = igual."""
        if self.speech_rate and self.reference_rate:
            return self.speech_rate / self.reference_rate
        return None


# Uma palavra isolada tem duracao, nao ritmo. Comparar velocidade de fala exige
# pelo menos duas palavras.
MIN_WORDS_FOR_RATE = 2


def speech_rate(words, total_duration: float | None = None) -> tuple[float | None, float]:
    """Palavras por segundo entre o inicio da primeira e o fim da ultima palavra."""
    if len(words) < MIN_WORDS_FOR_RATE:
        return None, 0.0
    span = words[-1].end - words[0].start
    if span <= 0:
        return None, 0.0
    return len(words) / span, span


def detect_pauses(words, threshold: float = PAUSE_THRESHOLD_S) -> list[Pause]:
    """Silencios entre palavras acima do limiar."""
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
    """F0 por quadro via autocorrelacao. `nan` nos quadros surdos."""
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
    """Direcao da F0 no trecho final. Devolve `(direcao, mediana_global)`.

    Compara a mediana do ultimo `tail_fraction` dos quadros sonoros com a dos
    anteriores. Precisa de pelo menos 6 quadros sonoros -- abaixo disso devolve
    UNKNOWN em vez de chutar.
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
