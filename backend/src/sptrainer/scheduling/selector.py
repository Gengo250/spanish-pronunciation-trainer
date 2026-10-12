"""Escolha da proxima carta.

Separado do conteudo e do progresso de proposito: o seletor recebe as cartas e um
retrato do historico, e devolve a proxima. Nao le banco, nao grava nada, nao
chama LLM -- o que o torna trivial de testar e de trocar quando chegar uma
repeticao espacada de verdade.

A regra que mais afeta a sensacao de uso e a janela anti-repeticao: sem ela, o
sorteio uniforme repete a mesma carta dentro de poucas rodadas e o aluno acha
que o app travou.
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
    """Sorteio ponderado pelo desempenho: o que saiu mal volta mais."""


class Pool(str, Enum):
    ALL = "all"
    NEW = "new"
    """Cartas que o aluno ainda nao praticou."""

    SEEN = "seen"
    """Cartas ja praticadas, para revisao."""

    STRUGGLING = "struggling"
    """Cartas ja praticadas cuja melhor nota ficou abaixo do limiar."""


# Nota a partir da qual consideramos a carta dominada.
MASTERY_SCORE = 80.0

# Quantas cartas recentes ficam bloqueadas antes de poderem voltar.
DEFAULT_RECENT_WINDOW = 10

# --- pesos do modo adaptativo ---------------------------------------------
# Repetição espaçada de verdade agenda por data. Isto é deliberadamente mais
# simples: só reponderar o sorteio pela melhor nota de cada carta. Resolve o que
# importa agora -- o que saiu mal volta mais -- sem introduzir estado temporal
# que depois teria de ser migrado.
WEIGHT_NEW = 2.0          # carta inédita: vale mais que uma já dominada
WEIGHT_MASTERED = 0.3     # dominada: continua aparecendo, mas raramente
WEIGHT_BASE = 1.0         # piso de uma carta já praticada
WEIGHT_DEFICIT = 3.0      # quanto a dificuldade soma ao peso


@dataclass
class StudyState:
    """Retrato do historico do aluno, injetado por quem chama."""

    attempts: dict[str, int] = field(default_factory=dict)
    best_score: dict[str, float] = field(default_factory=dict)
    recent: list[str] = field(default_factory=list)
    """Ids mostrados recentemente, do mais antigo para o mais novo."""

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
    # Sequencia de guardas de proposito: cada filtro fica legivel e isolado.
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
    if filters.pool is Pool.STRUGGLING and (  # noqa: SIM103 - guarda, nao expressao
        not state.seen(card.id) or state.best_score.get(card.id, 0.0) >= MASTERY_SCORE
    ):
        return False
    return True


def candidates(
    cards: list[Flashcard], filters: SelectionFilters, state: StudyState
) -> list[Flashcard]:
    return [c for c in cards if matches(c, filters, state)]


def card_weight(card_id: str, state: StudyState) -> float:
    """Peso de uma carta no sorteio adaptativo.

    Nova = 2.0 · dominada = 0.3 · praticada = 1.0 + 3.0 x (quanto falta para
    dominar). Uma carta com nota 0 pesa 4.0, ou seja, aparece cerca de treze
    vezes mais que uma já dominada.
    """
    if not state.seen(card_id):
        return WEIGHT_NEW
    best = state.best_score.get(card_id, 0.0)
    if best >= MASTERY_SCORE:
        return WEIGHT_MASTERED
    deficit = max(0.0, (MASTERY_SCORE - best) / MASTERY_SCORE)
    return WEIGHT_BASE + WEIGHT_DEFICIT * deficit


class CardSelector:
    """Devolve a proxima carta respeitando filtros, ordem e anti-repeticao."""

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

        # Evita repetir o que acabou de sair -- mas so enquanto sobrar escolha.
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
        """Monta uma sessao sem repetir carta dentro dela."""
        filters = filters or SelectionFilters()
        state = state or StudyState()
        pool = candidates(self.cards, filters, state)
        if filters.order is Order.SEQUENTIAL:
            return pool[:size]
        shuffled = pool[:]
        self.rng.shuffle(shuffled)
        return shuffled[:size]
