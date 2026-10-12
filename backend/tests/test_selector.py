"""Card selection: filters, order, anti-repetition."""

import random
from collections import Counter

import pytest

from sptrainer.content.models import CardType, Category, Flashcard, Level
from sptrainer.content.repository import load_json
from sptrainer.scheduling.selector import (
    CardSelector,
    Order,
    Pool,
    SelectionFilters,
    StudyState,
    candidates,
    card_weight,
)


def make(n, level=Level.BEGINNER, category=Category.GREETINGS,
         card_type=CardType.VOCABULARY, tags=()):
    return Flashcard(id=f"c{n}", text=f"palabra{n}", translation=f"palavra{n}",
                     level=level, card_type=card_type, category=category, tags=list(tags))


@pytest.fixture
def cards():
    return (
        [make(i) for i in range(10)]
        + [make(100 + i, level=Level.INTERMEDIATE, category=Category.TRAVEL) for i in range(5)]
        + [make(200 + i, level=Level.ADVANCED, card_type=CardType.IDIOMS
                if hasattr(CardType, "IDIOMS") else CardType.EXPRESSION) for i in range(5)]
    )


def test_level_filter(cards):
    got = candidates(cards, SelectionFilters(level=Level.INTERMEDIATE), StudyState())
    assert len(got) == 5 and all(c.level == Level.INTERMEDIATE for c in got)


def test_category_filter(cards):
    got = candidates(cards, SelectionFilters(category=Category.TRAVEL), StudyState())
    assert all(c.category == Category.TRAVEL for c in got) and got


def test_new_pool_excludes_practised_cards(cards):
    state = StudyState(attempts={"c0": 2, "c1": 1})
    got = candidates(cards, SelectionFilters(pool=Pool.NEW), state)
    assert {"c0", "c1"}.isdisjoint({c.id for c in got})


def test_seen_pool_only_returns_practised_cards(cards):
    state = StudyState(attempts={"c0": 2, "c1": 1})
    got = candidates(cards, SelectionFilters(pool=Pool.SEEN), state)
    assert {c.id for c in got} == {"c0", "c1"}


def test_struggling_pool_skips_mastered_cards(cards):
    state = StudyState(attempts={"c0": 1, "c1": 1}, best_score={"c0": 95.0, "c1": 40.0})
    got = candidates(cards, SelectionFilters(pool=Pool.STRUGGLING), state)
    assert {c.id for c in got} == {"c1"}


def test_sequential_order_walks_the_deck(cards):
    sel = CardSelector(cards)
    f = SelectionFilters(order=Order.SEQUENTIAL, level=Level.BEGINNER)
    assert [sel.next_card(f).id for _ in range(4)] == ["c0", "c1", "c2", "c3"]


def test_random_order_avoids_recent_cards(cards):
    """Without an anti-repetition window the draw returns the same card right away."""
    sel = CardSelector(cards, recent_window=5, rng=random.Random(7))
    state = StudyState(recent=["c0", "c1", "c2", "c3", "c4"])
    f = SelectionFilters(level=Level.BEGINNER)
    picked = {sel.next_card(f, state).id for _ in range(30)}
    assert picked.isdisjoint({"c0", "c1", "c2", "c3", "c4"})


def test_anti_repetition_relaxes_when_nothing_else_is_left(cards):
    """With a single eligible card, repeating beats returning nothing."""
    sel = CardSelector(cards, recent_window=10, rng=random.Random(1))
    state = StudyState(recent=[f"c{i}" for i in range(10)])
    assert sel.next_card(SelectionFilters(level=Level.BEGINNER), state) is not None


def test_random_selection_covers_the_whole_pool(cards):
    sel = CardSelector(cards, recent_window=0, rng=random.Random(3))
    f = SelectionFilters(level=Level.BEGINNER)
    counts = Counter(sel.next_card(f).id for _ in range(400))
    assert len(counts) == 10, "the draw left cards out"


def test_no_match_returns_none(cards):
    sel = CardSelector(cards)
    state = StudyState(attempts={c.id: 1 for c in cards})
    assert sel.next_card(SelectionFilters(pool=Pool.NEW), state) is None


def test_session_has_no_duplicates(cards):
    sel = CardSelector(cards, rng=random.Random(5))
    session = sel.session(8, SelectionFilters(level=Level.BEGINNER))
    assert len(session) == 8 and len({c.id for c in session}) == 8


def test_selector_works_on_the_real_deck():
    deck = load_json("src/sptrainer/content/seed/es_starter.json")
    sel = CardSelector(deck.cards, rng=random.Random(0))
    for level in Level:
        assert sel.next_card(SelectionFilters(level=level)).level == level


# --- modo adaptativo (SRS-lite) -------------------------------------------

def test_weight_ranks_difficulty_above_mastery():
    """Ordem pretendida: ruim > nova > média > dominada.

    The unseen card sits above the "average" on purpose: new material is worth
    more than drilling a card that already comes out reasonably. What genuinely
    continua acima de tudo.
    """
    state = StudyState(
        attempts={"dominada": 3, "media": 2, "ruim": 4},
        best_score={"dominada": 92.0, "media": 60.0, "ruim": 10.0},
    )
    ruim = card_weight("ruim", state)
    nova = card_weight("inedita", state)
    media = card_weight("media", state)
    dominada = card_weight("dominada", state)
    assert ruim > nova > media > dominada


def test_mastered_cards_still_appear_sometimes():
    """Low weight, not zero: occasional review still happens."""
    state = StudyState(attempts={"c": 1}, best_score={"c": 100.0})
    assert card_weight("c", state) > 0


def test_adaptive_order_favours_the_weak_card(cards):
    """With one bad card and one mastered, the bad one must come up far more."""
    state = StudyState(
        attempts={"c0": 1, "c1": 1},
        best_score={"c0": 5.0, "c1": 95.0},
    )
    two = [c for c in cards if c.id in {"c0", "c1"}]
    sel = CardSelector(two, recent_window=0, rng=random.Random(11))
    f = SelectionFilters(order=Order.ADAPTIVE)
    counts = Counter(sel.next_card(f, state).id for _ in range(600))
    assert counts["c0"] > counts["c1"] * 5, counts


def test_adaptive_order_still_covers_everything(cards):
    state = StudyState()
    sel = CardSelector(cards, recent_window=0, rng=random.Random(4))
    f = SelectionFilters(level=Level.BEGINNER, order=Order.ADAPTIVE)
    assert len(Counter(sel.next_card(f, state).id for _ in range(500))) == 10


def test_adaptive_order_respects_filters(cards):
    sel = CardSelector(cards, rng=random.Random(2))
    f = SelectionFilters(level=Level.INTERMEDIATE, order=Order.ADAPTIVE)
    assert all(sel.next_card(f, StudyState()).level == Level.INTERMEDIATE for _ in range(20))
