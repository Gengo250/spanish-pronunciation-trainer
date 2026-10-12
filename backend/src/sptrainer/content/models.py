"""Flashcard data model.

Designed to survive the arrival of other languages: the language pair is
explicit (`language` / `translation_language`), so nothing here assumes Spanish,
even though the first version ships Spanish only.

`expected_phonemes` holds the espeak-ng result, not an LLM's guess. It is empty
by default and filled in by the G2P -- that way the dataset stays readable by
hand and the phonetic reference stays deterministic.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class Level(int, Enum):
    """Levels defined by the app. They are not CEFR and claim no equivalence."""

    BEGINNER = 1
    INTERMEDIATE = 2
    ADVANCED = 3


class CardType(str, Enum):
    VOCABULARY = "vocabulary"
    PHRASE = "phrase"
    SENTENCE = "sentence"
    QUESTION = "question"
    EXPRESSION = "expression"
    VERB = "verb"
    PRONUNCIATION = "pronunciation"
    """Card built around one specific difficult sound."""

    INTONATION = "intonation"
    """Card where the melody of the sentence is the point."""


class Category(str, Enum):
    GREETINGS = "greetings"
    NUMBERS = "numbers"
    COLORS = "colors"
    OBJECTS = "objects"
    FOOD = "food"
    FAMILY = "family"
    TRAVEL = "travel"
    DAILY_LIFE = "daily_life"
    WORK = "work"
    FEELINGS = "feelings"
    TIME = "time"
    GRAMMAR = "grammar"
    IDIOMS = "idioms"
    CULTURE = "culture"
    SOUNDS = "sounds"


class Flashcard(BaseModel):
    id: str
    text: str
    """What the learner reads and pronounces."""

    translation: str
    language: str = "es"
    translation_language: str = "pt-BR"
    level: Level
    card_type: CardType
    category: Category

    grammar_note: str | None = None
    pronunciation_focus: str | None = None
    """The sound or pattern this card drills, in learner-facing language."""

    phoneme_targets: list[str] = Field(default_factory=list)
    """IPA phonemes the card exercises. Used to build series by sound."""

    expected_phonemes: list[str] = Field(default_factory=list)
    """Filled in by espeak-ng. Empty in the source file, on purpose."""

    example: str | None = None
    example_translation: str | None = None
    tags: list[str] = Field(default_factory=list)
    audio_path: str | None = None
    created_at: datetime | None = None

    @field_validator("text", "translation")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("text cannot be empty")
        return value.strip()

    @field_validator("id")
    @classmethod
    def _id_is_slug(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned or " " in cleaned:
            raise ValueError("id must be a slug with no spaces")
        return cleaned

    @property
    def word_count(self) -> int:
        return len(self.text.split())


class Deck(BaseModel):
    """A collection of cards with a little provenance."""

    name: str = "default"
    language: str = "es"
    description: str = ""
    cards: list[Flashcard] = Field(default_factory=list)

    def __len__(self) -> int:
        return len(self.cards)

    def by_level(self, level: Level) -> list[Flashcard]:
        return [c for c in self.cards if c.level == level]

    def by_category(self, category: Category) -> list[Flashcard]:
        return [c for c in self.cards if c.category == category]

    def ids(self) -> set[str]:
        return {c.id for c in self.cards}
