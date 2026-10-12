"""Local cache of the reference audio.

The ElevenLabs free account gives 10k characters/month (20k on the flash/turbo
models). A flashcard is 10-40 characters, so without a cache a learner repeating
the same card would burn the quota in an afternoon. With a cache, each
combination (text, voice, model, format) costs a single call, forever.

Slow playback does NOT come through here: the browser lowers `playbackRate`,
which costs zero credits.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

# Bump this when something changes that invalidates the audio already stored.
CACHE_SCHEMA_VERSION = "1"

_EXTENSIONS = {"mp3": ".mp3", "pcm": ".pcm", "ulaw": ".ulaw", "opus": ".opus", "wav": ".wav"}


def cache_key(text: str, voice_id: str, model_id: str, output_format: str) -> str:
    """Content-addressed key: same input, same file, always."""
    payload = f"{CACHE_SCHEMA_VERSION}|{text.strip()}|{voice_id}|{model_id}|{output_format}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _extension_for(output_format: str) -> str:
    return _EXTENSIONS.get(output_format.split("_")[0], ".mp3")


@dataclass
class CacheResult:
    path: Path
    audio: bytes
    cached: bool
    """True when it came from disk -- that is, it cost no credits."""

    characters_billed: int = 0


class TTSCache:
    """Stores the synthesized audio and the metadata explaining where it came from."""

    def __init__(self, directory: Path, synthesizer=None) -> None:
        self.directory = Path(directory)
        self.synthesizer = synthesizer
        self.hits = 0
        self.misses = 0

    def path_for(self, text: str, voice_id: str, model_id: str, output_format: str) -> Path:
        key = cache_key(text, voice_id, model_id, output_format)
        return self.directory / f"{key}{_extension_for(output_format)}"

    def get(self, text: str, voice_id: str, model_id: str, output_format: str) -> bytes | None:
        path = self.path_for(text, voice_id, model_id, output_format)
        if path.exists():
            return path.read_bytes()
        return None

    def store(
        self, text: str, voice_id: str, model_id: str, output_format: str, audio: bytes
    ) -> Path:
        path = self.path_for(text, voice_id, model_id, output_format)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(audio)
        path.with_suffix(path.suffix + ".json").write_text(
            json.dumps(
                {
                    "text": text,
                    "voice_id": voice_id,
                    "model_id": model_id,
                    "output_format": output_format,
                    "schema_version": CACHE_SCHEMA_VERSION,
                    "bytes": len(audio),
                    "characters": len(text.strip()),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return path

    def synthesize(
        self,
        text: str,
        voice_id: str,
        model_id: str,
        output_format: str,
    ) -> CacheResult:
        """Returns the audio, synthesizing only when it does not exist yet."""
        text = (text or "").strip()
        cached = self.get(text, voice_id, model_id, output_format)
        if cached is not None:
            self.hits += 1
            return CacheResult(
                path=self.path_for(text, voice_id, model_id, output_format),
                audio=cached,
                cached=True,
                characters_billed=0,
            )
        if self.synthesizer is None:
            raise RuntimeError(
                "This audio is not cached and no synthesiser is configured "
                "(is ELEVENLABS_API_KEY missing?)."
            )
        self.misses += 1
        audio = self.synthesizer.synthesize(text)
        path = self.store(text, voice_id, model_id, output_format, audio)
        return CacheResult(path=path, audio=audio, cached=False, characters_billed=len(text))
