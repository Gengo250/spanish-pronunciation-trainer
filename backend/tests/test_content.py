"""Conteudo: round-trip JSON/CSV, validacao e selecao."""

import pytest

from sptrainer.content.models import CardType, Category, Deck, Flashcard, Level
from sptrainer.content.repository import (
    ContentError,
    dumps_csv,
    load_json,
    loads_csv,
    save_csv,
    save_json,
)
from sptrainer.content.validation import validate_deck

SEED = "src/sptrainer/content/seed/es_starter.json"


@pytest.fixture
def deck():
    return load_json(SEED)


def card(**kw):
    base = {"id": "t-1", "text": "Hola", "translation": "Oi",
            "level": Level.BEGINNER, "card_type": CardType.VOCABULARY,
            "category": Category.GREETINGS}
    return Flashcard(**{**base, **kw})


# --- dataset inicial -------------------------------------------------------

def test_seed_deck_covers_all_three_levels(deck):
    for level in Level:
        assert len(deck.by_level(level)) >= 10, f"level {level.value} has too few cards"


def test_seed_deck_is_diverse(deck):
    assert len({c.card_type for c in deck.cards}) >= 7
    assert len({c.category for c in deck.cards}) >= 10


def test_seed_deck_has_no_validation_errors(deck):
    report = validate_deck(deck)
    assert report.ok, [f"{i.card_id}: {i.message}" for i in report.errors]


def test_seed_deck_ids_are_unique(deck):
    assert len(deck.ids()) == len(deck.cards)


# --- round-trip ------------------------------------------------------------

def test_json_round_trip(deck, tmp_path):
    path = save_json(deck, tmp_path / "d.json")
    assert load_json(path).cards == deck.cards


def test_csv_round_trip_preserves_everything(deck, tmp_path):
    save_csv(deck, tmp_path / "d.csv")
    restored = loads_csv((tmp_path / "d.csv").read_text(encoding="utf-8"))
    assert len(restored.cards) == len(deck.cards)
    for original, copy in zip(deck.cards, restored.cards):
        assert copy.id == original.id
        assert copy.text == original.text
        assert copy.translation == original.translation
        assert copy.level == original.level
        assert copy.card_type == original.card_type
        assert copy.tags == original.tags
        assert copy.phoneme_targets == original.phoneme_targets


def test_csv_keeps_accents_and_question_marks(tmp_path):
    deck = Deck(cards=[card(id="q", text="¿Cómo estás?", translation="Como vai?",
                            card_type=CardType.QUESTION)])
    restored = loads_csv(dumps_csv(deck))
    assert restored.cards[0].text == "¿Cómo estás?"


def test_csv_without_required_columns_is_rejected():
    with pytest.raises(ContentError, match="required columns"):
        loads_csv("id,text\nx,Hola\n")


def test_missing_file_is_reported():
    with pytest.raises(ContentError, match="not found"):
        load_json("/nonexistent/deck.json")


def test_invalid_json_is_reported(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ContentError, match="invalid JSON"):
        load_json(bad)


# --- validacao -------------------------------------------------------------

def test_duplicate_ids_are_errors():
    deck = Deck(cards=[card(id="dup"), card(id="dup", text="Adiós", translation="Tchau")])
    assert any(i.field_name == "id" for i in validate_deck(deck).errors)


def test_foreign_characters_are_errors():
    """Import junk -- this is exactly how a '社' got into the dataset."""
    deck = Deck(cards=[card(text="La desigualdad社 no se resuelve")])
    errors = validate_deck(deck).errors
    assert any("outside the Spanish alphabet" in i.message for i in errors)


def test_unclosed_spanish_question_is_an_error():
    deck = Deck(cards=[card(text="¿Cómo estás", card_type=CardType.QUESTION)])
    assert any("does not close" in i.message for i in validate_deck(deck).errors)


def test_cognate_translation_is_a_warning_not_an_error():
    """'azul' -> 'azul' e cognato legitimo entre espanhol e portugues."""
    deck = Deck(cards=[card(text="azul", translation="azul", category=Category.COLORS)])
    report = validate_deck(deck)
    assert report.ok
    assert any("cognate" in i.message for i in report.warnings)


def test_phoneme_target_check_accepts_allophones():
    """'dias' isolado da /d/; em 'buenos dias' soa /ð/. Nao pode acusar erro."""
    deck = Deck(cards=[card(text="Buenos días", translation="Bom dia",
                            phoneme_targets=["ð"], card_type=CardType.PHRASE)])
    assert not [i for i in validate_deck(deck).issues if i.field_name == "phoneme_targets"]


def test_phoneme_target_that_is_really_absent_warns():
    deck = Deck(cards=[card(text="mesa", translation="mesa", phoneme_targets=["x"])])
    assert any(i.field_name == "phoneme_targets" for i in validate_deck(deck).issues)
