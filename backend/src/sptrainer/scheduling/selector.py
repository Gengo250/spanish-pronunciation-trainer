"""Choosing the next card.

Deliberately separate from content and progress: the selector receives the cards
and a snapshot of the history, and returns the next one. It reads no database,
writes nothing and calls no LLM -- which makes it trivial to test and to replace
when real spaced repetition arrives.

The rule that affects the feel of the app most is the anti-repetition window:
without it, a uniform draw repeats the same card within a few rounds and the
learner thinks the app is stuck.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum

from ..content.models import CardType, Category, Flashcard, Level


class Order(str, Enum):
    RANDOM = "random"
    SEQUENTIAL = "sequential"
    ADAPTIVE = "adaptive"
    """Draw weighted by performance: what went badly comes back more often."""


class Pool(str, Enum):
    ALL = "all"
    NEW = "new"
    """Cards the learner has not practised yet."""

    SEEN = "seen"
    """Cards already practised, for review."""

    STRUGGLING = "struggling"
    """Cards already practised whose best score stayed below the threshold."""


# Score from which we consider a card mastered.
MASTERY_SCORE = 80.0

# How many recent cards stay blocked before they can come back.
DEFAULT_RECENT_WINDOW = 10

# --- adaptive mode weights -------------------------------------------------
# Real spaced repetition schedules by date. This is deliberately simpler: just
# reweight the draw by each card's best score. It solves what matters now --
# what went badly comes back more often -- without introducing temporal state
# that would later have to be migrated.
WEIGHT_NEW = 2.0          # unseen card: worth more than an already mastered one
WEIGHT_MASTERED = 0.3     # mastered: still shows up, but rarely
WEIGHT_BASE = 1.0         # floor for a card already practised
WEIGHT_DEFICIT = 3.0      # how much difficulty adds to the weight


@dataclass
class StudyState:
    """Snapshot of the learner's history, injected by the caller."""

    attempts: dict[str, int] = field(default_factory=dict)
    best_score: dict[str, float] = field(default_factory=dict)
    recent: list[str] = field(default_factory=list)
    """Ids shown recently, oldest first."""

    def seen(self, card_id: str) -> bool:
        return self.attempts.get(card_id, 0) > 0


@dataclass
class SelectionFilters:
    level: Level | None = None
    category: Category | None = None
    card_type: CardType | None = None
    tags: list[str] = field(default_factory=list)
    pool: Pool = Pool.ALL
    order: Order = Order.RANDOM


def matches(card: Flashcard, filters: SelectionFilters, state: StudyState) -> bool:
    # A sequence of guards on purpose: each filter stays readable and isolated.
    if filters.level is not None and card.level != filters.level:
        return False
    if filters.category is not None and card.category != filters.category:
        return False
    if filters.card_type is not None and card.card_type != filters.card_type:
        return False
    if filters.tags and not set(filters.tags) & set(card.tags):
        return False
    if filters.pool is Pool.NEW and state.seen(card.id):
        return False
    if filters.pool is Pool.SEEN and not state.seen(card.id):
        return False
    if filters.pool is Pool.STRUGGLING and (  # noqa: SIM103 - a guard, not an expression
        not state.seen(card.id) or state.best_score.get(card.id, 0.0) >= MASTERY_SCORE
    ):
        return False
    return True


def candidates(
    cards: list[Flashcard], filters: SelectionFilters, state: StudyState
) -> list[Flashcard]:
    return [c for c in cards if matches(c, filters, state)]


def card_weight(card_id: str, state: StudyState) -> float:
    """Weight of a card in the adaptive draw.

    New = 2.0 · mastered = 0.3 · practised = 1.0 + 3.0 x (how far from mastery).
    A card scoring 0 weighs 4.0, that is, it shows up about thirteen times more
    often than an already mastered one.
    """
    if not state.seen(card_id):
        return WEIGHT_NEW
    best = state.best_score.get(card_id, 0.0)
    if best >= MASTERY_SCORE:
        return WEIGHT_MASTERED
    deficit = max(0.0, (MASTERY_SCORE - best) / MASTERY_SCORE)
    return WEIGHT_BASE + WEIGHT_DEFICIT * deficit


class CardSelector:
    """Returns the next card, honouring filters, order and anti-repetition."""

    def __init__(
        self,
        cards: list[Flashcard],
        recent_window: int = DEFAULT_RECENT_WINDOW,
        rng: random.Random | None = None,
    ) -> None:
        self.cards = cards
        self.recent_window = recent_window
        self.rng = rng or random.Random()
        self._cursor = 0

    def next_card(
        self,
        filters: SelectionFilters | None = None,
        state: StudyState | None = None,
    ) -> Flashcard | None:
        filters = filters or SelectionFilters()
        state = state or StudyState()

        pool = candidates(self.cards, filters, state)
        if not pool:
            return None

        if filters.order is Order.SEQUENTIAL:
            card = pool[self._cursor % len(pool)]
            self._cursor += 1
            return card

        # Avoids repeating what just came up -- but only while there is choice left.
        blocked = set(state.recent[-self.recent_window :])
        choices = [c for c in pool if c.id not in blocked] or pool

        if filters.order is Order.ADAPTIVE:
            weights = [card_weight(c.id, state) for c in choices]
            return self.rng.choices(choices, weights=weights, k=1)[0]
        return self.rng.choice(choices)

    def session(
        self,
        size: int,
        filters: SelectionFilters | None = None,
        state: StudyState | None = None,
    ) -> list[Flashcard]:
        """Builds a session with no card repeated inside it."""
        filters = filters or SelectionFilters()
        state = state or StudyState()
        pool = candidates(self.cards, filters, state)
        if filters.order is Order.SEQUENTIAL:
            return pool[:size]
        shuffled = pool[:]
        self.rng.shuffle(shuffled)
        return shuffled[:size]
