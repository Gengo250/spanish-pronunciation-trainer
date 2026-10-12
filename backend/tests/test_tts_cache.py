"""O cache de TTS e o que impede a cota da ElevenLabs de evaporar."""

import json

import pytest

from sptrainer.tts.cache import TTSCache, cache_key

VOICE, MODEL, FMT = "voice-1", "eleven_multilingual_v2", "mp3_44100_128"


def test_same_input_same_key():
    a = cache_key("Hola", VOICE, MODEL, FMT)
    b = cache_key("  Hola  ", VOICE, MODEL, FMT)
    assert a == b, "espacos nas bordas nao podem gerar audio novo"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"text": "Adios"},
        {"voice_id": "voice-2"},
        {"model_id": "eleven_flash_v2_5"},
        {"output_format": "mp3_22050_32"},
    ],
)
def test_any_parameter_change_changes_key(kwargs):
    base = {"text": "Hola", "voice_id": VOICE, "model_id": MODEL,
            "output_format": FMT}
    assert cache_key(**base) != cache_key(**{**base, **kwargs})


def test_second_call_does_not_hit_the_api(tmp_path, fake_synth):
    cache = TTSCache(tmp_path, synthesizer=fake_synth)

    first = cache.synthesize("Buenos días", VOICE, MODEL, FMT)
    second = cache.synthesize("Buenos días", VOICE, MODEL, FMT)

    assert first.cached is False and first.characters_billed == len("Buenos días")
    assert second.cached is True and second.characters_billed == 0
    assert second.audio == first.audio
    assert fake_synth.calls == ["Buenos días"], "a API foi chamada duas vezes"
    assert (cache.hits, cache.misses) == (1, 1)


def test_cache_survives_a_new_instance(tmp_path, fake_synth):
    TTSCache(tmp_path, synthesizer=fake_synth).synthesize("Gracias", VOICE, MODEL, FMT)
    again = TTSCache(tmp_path, synthesizer=fake_synth).synthesize("Gracias", VOICE, MODEL, FMT)
    assert again.cached is True
    assert len(fake_synth.calls) == 1


def test_sidecar_records_provenance(tmp_path, fake_synth):
    cache = TTSCache(tmp_path, synthesizer=fake_synth)
    result = cache.synthesize("Hola", VOICE, MODEL, FMT)
    meta = json.loads(result.path.with_suffix(result.path.suffix + ".json").read_text())
    assert meta["text"] == "Hola"
    assert meta["voice_id"] == VOICE
    assert meta["characters"] == 4


def test_missing_audio_without_synthesizer_is_an_error(tmp_path):
    with pytest.raises(RuntimeError, match="no synthesiser is configured"):
        TTSCache(tmp_path).synthesize("Hola", VOICE, MODEL, FMT)
