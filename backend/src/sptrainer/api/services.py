"""Wiring of the application's dependencies.

A single place decides what exists and when it gets loaded. Loading is lazy on
purpose: on this machine Whisper takes several hundred MB and the phoneme model
a few more, and the flashcard screen has to open without waiting for either.
They only come up when the learner records for the first time.

Everything here is replaceable in tests: the API tests inject doubles and never
touch ElevenLabs or load Whisper.
"""

from __future__ import annotations

import logging
from functools import cached_property
from pathlib import Path

from ..assessment.phonemes import PhonemeRecognizer
from ..assessment.pipeline import AssessmentPipeline
from ..config import Settings, load_settings
from ..content.models import Deck
from ..content.repository import load_json
from ..progress.db import connect
from ..progress.repository import ProgressRepository
from ..scheduling.selector import CardSelector
from ..stt.whisper import Transcriber
from ..tts.cache import TTSCache
from ..tts.elevenlabs_client import ElevenLabsSynthesizer
from ..tts.reference import ReferenceProfiler

logger = logging.getLogger(__name__)

SEED_DECK = Path(__file__).resolve().parents[1] / "content" / "seed" / "es_starter.json"


class Services:
    def __init__(self, settings: Settings | None = None, deck: Deck | None = None) -> None:
        self.settings = settings or load_settings()
        self.deck = deck if deck is not None else load_json(SEED_DECK)
        self.selector = CardSelector(self.deck.cards)
        self.connection = connect(self.settings.db_path)
        self.progress = ProgressRepository(self.connection)

    # --- TTS ---------------------------------------------------------------

    @cached_property
    def tts(self) -> TTSCache:
        synthesizer = None
        if self.settings.elevenlabs.configured:
            synthesizer = ElevenLabsSynthesizer(
                api_key=self.settings.elevenlabs.api_key,
                voice_id=self.settings.elevenlabs.voice_id,
                model_id=self.settings.elevenlabs.model_id,
                output_format=self.settings.elevenlabs.output_format,
            )
        else:
            logger.warning(
                "ELEVENLABS_API_KEY missing: only already-cached audio can be played."
            )
        return TTSCache(self.settings.tts_cache_dir, synthesizer=synthesizer)

    # --- assessment ----------------------------------------------------------

    @cached_property
    def transcriber(self) -> Transcriber:
        return Transcriber(
            model_size=self.settings.whisper.model,
            device=self.settings.whisper.device,
            compute_type=self.settings.whisper.compute_type,
            language=self.settings.whisper.language,
        )

    @cached_property
    def recognizer(self) -> PhonemeRecognizer | None:
        if not self.settings.phonemes.enabled:
            return None
        recognizer = PhonemeRecognizer(
            repo_id=self.settings.phonemes.repo_id,
            filename=self.settings.phonemes.filename,
        )
        if not recognizer.available():
            logger.warning(
                "phoneme model unavailable: assessment will run without per-sound analysis."
            )
            return None
        return recognizer

    @cached_property
    def pipeline(self) -> AssessmentPipeline:
        return AssessmentPipeline(
            transcriber=self.transcriber,
            recognizer=self.recognizer,
            espeak_voice=self.settings.espeak_voice,
            absolute_floor=self.settings.phonemes.gop_threshold,
            phonemes_enabled=self.settings.phonemes.enabled,
        )

    @cached_property
    def reference(self) -> ReferenceProfiler:
        """Acoustic profile of the reference -- the relative basis of per-sound analysis."""
        return ReferenceProfiler(self.tts, self.recognizer, self.settings)

    def close(self) -> None:
        self.connection.close()
