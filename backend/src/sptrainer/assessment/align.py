"""Alinhamento de sequencias de fonemas (Needleman-Wunsch).

Comparar duas listas de fonemas so e util depois de alinha-las: sem isso, uma
unica insercao no comeco desloca tudo e o diff vira ruido.

A substituicao custa zero quando os dois fonemas sao equivalentes (alofonia,
variacao regional ou artefato conhecido do modelo), entao sotaque valido nao
aparece como erro nem no alinhamento nem na taxa.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .accents import collapse_geminates, equivalence_reason, equivalent


class Op(str, Enum):
    MATCH = "match"
    """Identicos."""

    EQUIVALENT = "equivalent"
    """Diferentes na notacao, equivalentes na fala. Nao e erro."""

    SUBSTITUTION = "substitution"
    DELETION = "deletion"
    """Esperado, mas nao pronunciado."""

    INSERTION = "insertion"
    """Pronunciado, mas nao esperado."""


@dataclass
class AlignedPair:
    op: Op
    expected: str | None
    heard: str | None
    expected_index: int | None = None
    heard_index: int | None = None
    reason: str | None = None
    """Por que foi considerado equivalente, quando foi."""

    @property
    def is_error(self) -> bool:
        return self.op in (Op.SUBSTITUTION, Op.DELETION, Op.INSERTION)


COST_SUBSTITUTION = 1
COST_GAP = 1


def align(expected: list[str], heard: list[str]) -> list[AlignedPair]:
    """Alinhamento global de custo minimo entre as duas sequencias."""
    n, m = len(expected), len(heard)
    # d[i][j] = custo de alinhar expected[:i] com heard[:j]
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        d[i][0] = i * COST_GAP
    for j in range(1, m + 1):
        d[0][j] = j * COST_GAP

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            sub = 0 if equivalent(expected[i - 1], heard[j - 1]) else COST_SUBSTITUTION
            d[i][j] = min(
                d[i - 1][j - 1] + sub,
                d[i - 1][j] + COST_GAP,
                d[i][j - 1] + COST_GAP,
            )

    # Backtrack. Diagonal tem prioridade para nao fatiar substituicoes em
    # delecao+insercao, que produziria um diff mais dificil de ler.
    pairs: list[AlignedPair] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0:
            sub = 0 if equivalent(expected[i - 1], heard[j - 1]) else COST_SUBSTITUTION
            if d[i][j] == d[i - 1][j - 1] + sub:
                e, h = expected[i - 1], heard[j - 1]
                if e == h:
                    op, reason = Op.MATCH, "identical"
                elif sub == 0:
                    op, reason = Op.EQUIVALENT, equivalence_reason(e, h)
                else:
                    op, reason = Op.SUBSTITUTION, None
                pairs.append(AlignedPair(op, e, h, i - 1, j - 1, reason))
                i, j = i - 1, j - 1
                continue
        if i > 0 and d[i][j] == d[i - 1][j] + COST_GAP:
            pairs.append(AlignedPair(Op.DELETION, expected[i - 1], None, i - 1, None))
            i -= 1
            continue
        pairs.append(AlignedPair(Op.INSERTION, None, heard[j - 1], None, j - 1))
        j -= 1

    pairs.reverse()
    return pairs


def error_rate(expected: list[str], heard: list[str], *, collapse: bool = True) -> float:
    """Taxa de erro por fonema (PER), ignorando equivalencias.

    `0.0` = tudo equivalente ou identico. Normalizada pelo tamanho do esperado,
    entao insercoes podem levar o valor acima de 1.0 -- quem usa deve limitar.
    """
    if collapse:
        expected, heard = collapse_geminates(expected), collapse_geminates(heard)
    if not expected:
        return 0.0 if not heard else 1.0
    errors = sum(1 for p in align(expected, heard) if p.is_error)
    return errors / len(expected)


def accuracy(expected: list[str], heard: list[str], *, collapse: bool = True) -> float:
    """`1 - PER`, limitado a [0, 1]."""
    return max(0.0, min(1.0, 1.0 - error_rate(expected, heard, collapse=collapse)))
