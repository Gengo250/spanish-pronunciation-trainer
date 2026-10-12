"""Configuracao: padroes sensatos e, acima de tudo, nenhum vazamento de chave."""

import pytest

from sptrainer.config import ConfigError, ElevenLabsSettings, Settings, load_settings


def test_api_key_never_appears_in_repr():
    settings = Settings(elevenlabs=ElevenLabsSettings(api_key="sk_super_secret_value"))
    assert "sk_super_secret_value" not in repr(settings)
    assert "sk_super_secret_value" not in repr(settings.elevenlabs)
    assert "<set>" in repr(settings.elevenlabs)


def test_missing_key_is_reported_as_missing():
    assert "<missing>" in repr(ElevenLabsSettings())
    assert ElevenLabsSettings().configured is False


@pytest.mark.parametrize("accent,voice", [("es-419", "es-419"), ("es", "es")])
def test_accent_maps_to_espeak_voice(accent, voice):
    assert Settings(accent=accent).espeak_voice == voice


def test_unknown_accent_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("SPANISH_ACCENT", "pt-BR")
    with pytest.raises(ConfigError, match="SPANISH_ACCENT"):
        load_settings(env_file=tmp_path / "absent.env")
