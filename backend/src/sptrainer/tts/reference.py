"""Perfil acustico do audio de referencia de cada carta.

Existe por causa de um resultado medido: um limiar absoluto de GOP acusa erro em
audio comprovadamente correto -- a sinalefa entre palavras, as aproximantes
intervocalicas e as palavras atonas tem GOP naturalmente baixo mesmo numa
pronuncia perfeita. Em 79 fonemas, o limiar absoluto marcou 5 falsos positivos
na propria referencia da ElevenLabs.

A saida e comparar o aluno com a referencia **da mesma frase**, som a som. Aquilo
que e intrinsecamente fraco e fraco nos dois, entao a diferenca fica perto de
zero e nao vira erro. Com isso os falsos positivos caem a zero por construcao,
sem perder deteccao.

O perfil e calculado uma vez por carta e guardado ao lado do MP3 em cache: custa
uma passada do modelo (~160 ms) na primeira vez e nada depois.
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

# Abaixo disto nao ha ritmo a comparar: uma palavra isolada nao tem velocidade de
# fala, so duracao.
MIN_WORDS_FOR_RATE = 2


@dataclass
class ReferenceProfile:
    gop: list[float] | None = None
    """GOP por fonema esperado no audio de referencia."""

    speech_rate: float | None = None
    """Palavras por segundo na referencia, usado como base da fluencia."""

    duration: float = 0.0


class ReferenceProfiler:
    """Calcula e guarda o perfil acustico da referencia de cada carta."""

    def __init__(self, cache, recognizer, settings) -> None:
        self.cache = cache
        self.recognizer = recognizer
        self.settings = settings

    def _profile_path(self, audio_path: Path) -> Path:
        return audio_path.with_suffix(audio_path.suffix + ".profile.json")

    def profile(self, text: str, expected_phonemes: list[str]) -> ReferenceProfile:
        """Perfil da carta. Devolve um perfil vazio se nada disso for possivel."""
        eleven = self.settings.elevenlabs
        try:
            reference = self.cache.synthesize(
                text, eleven.voice_id, eleven.model_id, eleven.output_format
            )
        except Exception as exc:  # noqa: BLE001 - sem referencia a avaliacao segue
            logger.info("sem audio de referencia para %r: %s", text[:40], exc)
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
                logger.warning("perfil de referencia ilegivel em %s: %s", path, exc)

        try:
            pcm = decode_to_pcm16(reference.audio)
        except Exception as exc:  # noqa: BLE001
            logger.warning("nao consegui decodificar a referencia: %s", exc)
            return ReferenceProfile()

        duration = duration_seconds(to_float32(pcm))
        # O silencio das bordas precisa sair: o ritmo do aluno vem dos
        # timestamps do Whisper, que ja o ignoram. Medir a referencia pela
        # duracao cheia faria toda carta parecer falada rapido demais.
        span = speech_span(pcm)
        words = len(text.split())
        # Com uma palavra so nao existe "ritmo" para comparar.
        rate = (words / span) if span > 0 and words >= MIN_WORDS_FOR_RATE else None

        gop = None
        if self.recognizer is not None and expected_phonemes:
            try:
                gop = self.recognizer.recognize(
                    normalize_for_wav2vec2(pcm), expected_phonemes
                ).gop
            except Exception as exc:  # noqa: BLE001
                logger.warning("perfil acustico da referencia falhou: %s", exc)

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
            logger.warning("nao consegui gravar o perfil de referencia: %s", exc)
        return profile
