"""Speech synthesis with ElevenLabs.

Reuses the synthesis and, above all, the error translation from the prototype
(`voice-assistant/src/voice_assistant/speech.py`), which already maps the real
stumbles of the free-tier API. What was left out is `play_bytes`: in the trainer
the browser plays the audio, so the backend only returns bytes.
"""

from __future__ import annotations

from typing import Protocol

# Default voices available to free accounts (library voices need a paid plan).
DEFAULT_VOICES = {
    "Sarah": "EXAVITQu4vr4xnSDxMaL",
    "George": "JBFqnCBsd6RMkjVDRZzb",
    "Brian": "nPczCjzI2devNBz1zQrb",
    "Lily": "pFZP5JQG7iQjIQuC4Bku",
    "Laura": "FGY2WhTYpPnrIDTdsKH5",
    "Charlotte": "XB0fDUnXU5powFXDhCwa",
}


class SpeechError(RuntimeError):
    """Audio synthesis failed."""


class Synthesizer(Protocol):
    """Minimal contract of a synthesizer, for the cache and the tests."""

    def synthesize(self, text: str) -> bytes: ...


def explain(exc: Exception) -> str:
    """Translates the most common API errors into actionable messages.

    Copied from the prototype: each branch corresponds to an error that really
    happened with this key.
    """
    message = str(exc)
    low = message.lower()
    if "library_voice" in low or "paid_plan_required" in low:
        return (
            "This is a library voice, which free accounts cannot use through the API. "
            f"Pick one of the default voices: {', '.join(DEFAULT_VOICES)}."
        )
    if "quota_exceeded" in low or "credits" in low:
        return "The ElevenLabs quota for this cycle is used up. It renews monthly."
    if "missing the permission" in low:
        return f"The ElevenLabs key is missing a required permission: {message}"
    if "401" in low or "unauthorized" in low:
        return "The ElevenLabs key is invalid or revoked."
    return f"Speech synthesis failed: {message}"


class ElevenLabsSynthesizer:
    """Synthesizes text and tracks the approximate character usage."""

    def __init__(
        self,
        api_key: str,
        voice_id: str = DEFAULT_VOICES["Sarah"],
        model_id: str = "eleven_multilingual_v2",
        output_format: str = "mp3_44100_128",
    ) -> None:
        if not api_key:
            raise SpeechError("ELEVENLABS_API_KEY is empty.")
        self.voice_id = voice_id
        self.model_id = model_id
        self.output_format = output_format
        self.characters_used = 0
        self._api_key = api_key
        self._client = None

    def __repr__(self) -> str:  # never leak the key
        return (
            f"ElevenLabsSynthesizer(voice_id={self.voice_id!r}, "
            f"model_id={self.model_id!r}, characters_used={self.characters_used})"
        )

    def _get_client(self):
        if self._client is None:
            from elevenlabs.client import ElevenLabs

            self._client = ElevenLabs(api_key=self._api_key)
        return self._client

    def synthesize(self, text: str) -> bytes:
        """Converts text into audio bytes. Every call costs credits."""
        text = (text or "").strip()
        if not text:
            raise SpeechError("Empty text: nothing to synthesise.")
        try:
            stream = self._get_client().text_to_speech.convert(
                voice_id=self.voice_id,
                model_id=self.model_id,
                output_format=self.output_format,
                text=text,
            )
            audio = b"".join(stream)
        except Exception as exc:
            raise SpeechError(explain(exc)) from exc
        if not audio:
            raise SpeechError("ElevenLabs returned empty audio.")
        self.characters_used += len(text)
        return audio
