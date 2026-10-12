"""Cache local do audio de referencia.

A conta free da ElevenLabs da 10k caracteres/mes (20k nos modelos flash/turbo).
Um flashcard tem 10-40 caracteres, entao sem cache um aluno repetindo a mesma
carta queimaria a cota em uma tarde. Com cache, cada combinacao
(texto, voz, modelo, formato) custa uma unica chamada para sempre.

A reproducao lenta NAO passa por aqui: o navegador baixa o `playbackRate`, o que
custa zero credito.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

# Suba quando mudar algo que invalide o audio ja gravado.
CACHE_SCHEMA_VERSION = "1"

_EXTENSIONS = {"mp3": ".mp3", "pcm": ".pcm", "ulaw": ".ulaw", "opus": ".opus", "wav": ".wav"}


def cache_key(text: str, voice_id: str, model_id: str, output_format: str) -> str:
    """Chave enderecada por conteudo: mesma entrada, mesmo arquivo, sempre."""
    payload = f"{CACHE_SCHEMA_VERSION}|{text.strip()}|{voice_id}|{model_id}|{output_format}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _extension_for(output_format: str) -> str:
    return _EXTENSIONS.get(output_format.split("_")[0], ".mp3")


@dataclass
class CacheResult:
    path: Path
    audio: bytes
    cached: bool
    """True quando veio do disco -- ou seja, nao custou credito."""

    characters_billed: int = 0


class TTSCache:
    """Guarda o audio sintetizado e os metadados que explicam de onde ele veio."""

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
        """Devolve o audio, sintetizando apenas quando ele ainda nao existe."""
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
