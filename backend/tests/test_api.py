"""API: contrato das rotas, com todos os servicos externos dublados.

Nenhum teste aqui carrega o Whisper nem toca a ElevenLabs.
"""

import io

import pytest
from conftest import FakeSynthesizer, FakeTranscriber
from fastapi.testclient import TestClient

from sptrainer.api.app import create_app
from sptrainer.api.services import Services
from sptrainer.assessment.pipeline import AssessmentPipeline
from sptrainer.config import ElevenLabsSettings, Settings
from sptrainer.content.models import CardType, Category, Deck, Flashcard, Level
from sptrainer.tts.cache import TTSCache

PHRASE = "Me gustaría aprender español"


def make_deck():
    return Deck(name="test", cards=[
        Flashcard(id="c1", text=PHRASE, translation="Eu gostaria de aprender espanhol",
                  level=Level.INTERMEDIATE, card_type=CardType.SENTENCE,
                  category=Category.DAILY_LIFE),
        Flashcard(id="c2", text="Hola", translation="Oi", level=Level.BEGINNER,
                  card_type=CardType.VOCABULARY, category=Category.GREETINGS),
        Flashcard(id="c3", text="¿Cómo estás?", translation="Como vai?",
                  level=Level.BEGINNER, card_type=CardType.QUESTION,
                  category=Category.GREETINGS),
    ])


@pytest.fixture
def synth():
    return FakeSynthesizer()


@pytest.fixture
def client(tmp_path, synth):
    settings = Settings(
        elevenlabs=ElevenLabsSettings(api_key="sk_test_fake"), data_dir=tmp_path
    )
    services = Services(settings=settings, deck=make_deck())
    services.__dict__["tts"] = TTSCache(tmp_path / "tts", synthesizer=synth)
    services.__dict__["pipeline"] = AssessmentPipeline(
        transcriber=FakeTranscriber(PHRASE), recognizer=None
    )
    app = create_app(services)
    with TestClient(app) as c:
        c.services = services
        yield c
    services.close()


def wav_bytes(seconds=2.0, sample_rate=16000):
    """WAV real: o endpoint passa o audio pelo ffmpeg de verdade."""
    import wave

    import numpy as np

    rng = np.random.default_rng(0)
    samples = (rng.standard_normal(int(sample_rate * seconds)) * 6000).astype(np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sample_rate)
        w.writeframes(samples.tobytes())
    return buffer.getvalue()


# --- saude e metadados -----------------------------------------------------

def test_health_reports_real_state(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["cards"] == 3
    assert body["accent"] == "es-419"


def test_meta_lists_only_categories_present_in_the_deck(client):
    body = client.get("/api/meta").json()
    assert set(body["categories"]) == {"greetings", "daily_life"}
    assert len(body["levels"]) == 3


# --- cartas ----------------------------------------------------------------

def test_next_card_respects_the_level_filter(client):
    for _ in range(10):
        assert client.get("/api/cards/next?level=1").json()["level"] == 1


def test_next_card_respects_the_category_filter(client):
    body = client.get("/api/cards/next?category=daily_life").json()
    assert body["category"] == "daily_life"


def test_impossible_filter_returns_404(client):
    assert client.get("/api/cards/next?level=3").status_code == 404


def test_invalid_category_is_a_400_with_options(client):
    response = client.get("/api/cards/next?category=nao_existe")
    assert response.status_code == 400
    assert "greetings" in response.json()["detail"]


def test_unknown_card_is_404(client):
    assert client.get("/api/cards/nope").status_code == 404


# --- audio de referencia e cache ------------------------------------------

def test_first_audio_request_synthesizes_and_second_uses_cache(client, synth):
    """O cache e o que protege a cota da ElevenLabs."""
    first = client.get("/api/cards/c2/audio")
    assert first.status_code == 200
    assert first.headers["x-cache"] == "miss"
    assert first.headers["x-characters-billed"] == "4"
    assert first.headers["content-type"] == "audio/mpeg"

    second = client.get("/api/cards/c2/audio")
    assert second.headers["x-cache"] == "hit"
    assert second.headers["x-characters-billed"] == "0"
    assert second.content == first.content
    assert synth.calls == ["Hola"], "a ElevenLabs foi chamada duas vezes"


def test_audio_without_api_key_is_503(tmp_path):
    services = Services(settings=Settings(data_dir=tmp_path), deck=make_deck())
    services.__dict__["tts"] = TTSCache(tmp_path / "tts", synthesizer=None)
    with TestClient(create_app(services)) as client:
        assert client.get("/api/cards/c2/audio").status_code == 503
    services.close()


# --- tentativa -------------------------------------------------------------

def test_attempt_returns_assessment_and_records_progress(client):
    response = client.post(
        "/api/cards/c1/attempt", files={"audio": ("a.wav", wav_bytes(), "audio/wav")}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["card_id"] == "c1"
    assert body["recognized_text"] == PHRASE
    assert body["scores"]["word_accuracy"] == 1.0
    assert "transcript_match" in body["capabilities"]

    summary = client.get("/api/progress/summary").json()
    assert summary["total_attempts"] == 1
    assert summary["cards_practised"] == 1


def test_attempt_without_phoneme_model_declares_the_limitation(client):
    body = client.post(
        "/api/cards/c1/attempt", files={"audio": ("a.wav", wav_bytes(), "audio/wav")}
    ).json()
    assert "phoneme_analysis" not in body["capabilities"]
    assert body["scores"]["phoneme_accuracy"] is None
    assert any("Sound-by-sound analysis is off" in limit for limit in body["limitations"])


def test_silent_recording_is_reported_as_no_speech(client):
    import wave

    import numpy as np
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(np.zeros(32000, dtype=np.int16).tobytes())
    body = client.post(
        "/api/cards/c1/attempt", files={"audio": ("a.wav", buffer.getvalue(), "audio/wav")}
    ).json()
    assert body["no_speech_detected"] is True


def test_undecodable_audio_is_a_400(client):
    response = client.post(
        "/api/cards/c1/attempt",
        files={"audio": ("a.webm", b"isto nao e audio", "audio/webm")},
    )
    assert response.status_code == 400


def test_attempt_on_unknown_card_is_404(client):
    response = client.post(
        "/api/cards/nope/attempt", files={"audio": ("a.wav", wav_bytes(), "audio/wav")}
    )
    assert response.status_code == 404


# --- conteudo --------------------------------------------------------------

def test_export_json_and_csv(client):
    body = client.get("/api/content/export?fmt=json").json()
    assert len(body["cards"]) == 3

    csv_text = client.get("/api/content/export?fmt=csv").text
    assert csv_text.splitlines()[0].startswith("id,text,translation")
    assert "¿Cómo estás?" in csv_text


def test_validate_upload_reports_problems(client):
    csv_text = (
        "id,text,translation,level,card_type,category\n"
        "dup,Hola,Oi,1,vocabulary,greetings\n"
        "dup,Adiós,Tchau,1,vocabulary,greetings\n"
    )
    body = client.post(
        "/api/content/validate",
        files={"file": ("d.csv", csv_text.encode(), "text/csv")},
    ).json()
    assert body["ok"] is False
    assert any(e["field"] == "id" for e in body["errors"])


def test_validate_rejects_csv_without_columns(client):
    response = client.post(
        "/api/content/validate", files={"file": ("d.csv", b"a,b\n1,2\n", "text/csv")}
    )
    assert response.status_code == 400



def test_adaptive_order_is_accepted(client):
    assert client.get("/api/cards/next?order=adaptive").status_code == 200


def test_attempt_includes_a_deterministic_summary(client):
    body = client.post(
        "/api/cards/c1/attempt", files={"audio": ("a.wav", wav_bytes(), "audio/wav")}
    ).json()
    assert body["summary"]
    assert "summary_source" not in body, "sobrou resíduo da remoção do LLM"
