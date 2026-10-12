"""Modelo de dados dos flashcards.

Desenhado para sobreviver a chegada de outros idiomas: o par de idiomas e
explicito (`language` / `translation_language`), entao nada aqui presume
espanhol, mesmo que a primeira versao so traga espanhol.

`expected_phonemes` guarda o resultado do espeak-ng, nao palpite de LLM. Fica
vazio por padrao e e preenchido pelo G2P -- assim o dataset continua legivel a
mao e a referencia fonetica continua deterministica.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class Level(int, Enum):
    """Niveis definidos pela aplicacao. Nao sao CEFR e nao se pretendem equivalentes."""

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
    """Carta montada em volta de um som dificil especifico."""

    INTONATION = "intonation"
    """Carta em que a melodia da frase e o objetivo."""


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
    """O que o aluno le e pronuncia."""

    translation: str
    language: str = "es"
    translation_language: str = "pt-BR"
    level: Level
    card_type: CardType
    category: Category

    grammar_note: str | None = None
    pronunciation_focus: str | None = None
    """O som ou padrao que esta carta treina, em linguagem de aluno."""

    phoneme_targets: list[str] = Field(default_factory=list)
    """Fonemas IPA que a carta exercita. Usado para montar series por som."""

    expected_phonemes: list[str] = Field(default_factory=list)
    """Preenchido pelo espeak-ng. Vazio no arquivo-fonte, de proposito."""

    example: str | None = None
    example_translation: str | None = None
    tags: list[str] = Field(default_factory=list)
    audio_path: str | None = None
    created_at: datetime | None = None

    @field_validator("text", "translation")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("texto nao pode ser vazio")
        return value.strip()

    @field_validator("id")
    @classmethod
    def _id_is_slug(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned or " " in cleaned:
            raise ValueError("id deve ser um slug sem espacos")
        return cleaned

    @property
    def word_count(self) -> int:
        return len(self.text.split())


class Deck(BaseModel):
    """Colecao de cartas com um pouco de proveniencia."""

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
