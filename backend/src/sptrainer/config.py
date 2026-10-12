"""Configuracao por ambiente.

Segue o padrao do prototipo `voice-assistant`: tudo vem do `.env`, com padroes
seguros, e cada secao e um dataclass que os modulos recebem pronto. Nenhum
segredo aparece em `repr()` ou em log.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]

# Variante de espanhol -> voz do espeak-ng usada no G2P de referencia.
ACCENT_VOICES = {"es-419": "es-419", "es": "es"}
DEFAULT_ACCENT = "es-419"


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = _env(name)
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name).lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on", "sim"}


class ConfigError(RuntimeError):
    """Configuracao ausente ou invalida."""


@dataclass
class ElevenLabsSettings:
    api_key: str = ""
    voice_id: str = "EXAVITQu4vr4xnSDxMaL"
    model_id: str = "eleven_multilingual_v2"
    output_format: str = "mp3_44100_128"

    def __repr__(self) -> str:  # nunca vazar a chave em log/traceback
        state = "set" if self.api_key else "missing"
        return (
            f"ElevenLabsSettings(api_key=<{state}>, voice_id={self.voice_id!r}, "
            f"model_id={self.model_id!r}, output_format={self.output_format!r})"
        )

    @property
    def configured(self) -> bool:
        return bool(self.api_key)


@dataclass
class WhisperSettings:
    model: str = "small"
    device: str = "cpu"
    compute_type: str = "int8"
    language: str = "es"


@dataclass
class PhonemeSettings:
    """Modelo acustico de fonemas (wav2vec2 CTC, int8 ONNX)."""

    enabled: bool = True
    repo_id: str = "duyentq/sonari-wav2vec2-phoneme-int8"
    filename: str = "wav2vec2_int8.onnx"
    vocab_repo_id: str = "facebook/wav2vec2-lv-60-espeak-cv-ft"
    vocab_filename: str = "vocab.json"
    # GOP medio abaixo deste valor vira candidato a erro de pronuncia.
    # Provisorio (spike M0); calibrar com gravacoes reais. Ver docs/pronunciation-assessment.md
    gop_threshold: float = -2.0


@dataclass
class Settings:
    elevenlabs: ElevenLabsSettings = field(default_factory=ElevenLabsSettings)
    whisper: WhisperSettings = field(default_factory=WhisperSettings)
    phonemes: PhonemeSettings = field(default_factory=PhonemeSettings)
    accent: str = DEFAULT_ACCENT
    data_dir: Path = field(default_factory=lambda: REPO_ROOT / "data")

    @property
    def espeak_voice(self) -> str:
        return ACCENT_VOICES.get(self.accent, ACCENT_VOICES[DEFAULT_ACCENT])

    @property
    def tts_cache_dir(self) -> Path:
        return self.data_dir / "cache" / "tts"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "progress.db"


def load_settings(env_file: Path | None = None) -> Settings:
    """Le o `.env` (se houver) e monta as configuracoes."""
    load_dotenv(env_file or REPO_ROOT / ".env", override=False)

    accent = _env("SPANISH_ACCENT", DEFAULT_ACCENT)
    if accent not in ACCENT_VOICES:
        raise ConfigError(
            f"SPANISH_ACCENT={accent!r} invalido. Use um de: {', '.join(ACCENT_VOICES)}"
        )

    data_dir = Path(_env("DATA_DIR", "data"))
    if not data_dir.is_absolute():
        data_dir = REPO_ROOT / data_dir

    return Settings(
        elevenlabs=ElevenLabsSettings(
            api_key=_env("ELEVENLABS_API_KEY"),
            voice_id=_env("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL"),
            model_id=_env("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2"),
            output_format=_env("ELEVENLABS_OUTPUT_FORMAT", "mp3_44100_128"),
        ),
        whisper=WhisperSettings(
            model=_env("WHISPER_MODEL", "small"),
            device=_env("WHISPER_DEVICE", "cpu"),
            compute_type=_env("WHISPER_COMPUTE_TYPE", "int8"),
            language=_env("WHISPER_LANGUAGE", "es"),
        ),
        phonemes=PhonemeSettings(
            enabled=_env_bool("PHONEME_ASSESSMENT_ENABLED", True),
            repo_id=_env("PHONEME_MODEL_REPO", "duyentq/sonari-wav2vec2-phoneme-int8"),
            filename=_env("PHONEME_MODEL_FILE", "wav2vec2_int8.onnx"),
            gop_threshold=_env_float("PHONEME_GOP_THRESHOLD", -2.0),
        ),
        accent=accent,
        data_dir=data_dir,
    )
