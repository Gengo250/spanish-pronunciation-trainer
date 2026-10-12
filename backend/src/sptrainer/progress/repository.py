"""Consultas de progresso."""

from __future__ import annotations

import sqlite3

from ..assessment.types import AssessmentResult
from ..scheduling.selector import MASTERY_SCORE, StudyState
from .db import CardProgress, transaction, utcnow

# Quantas cartas recentes alimentam a janela anti-repeticao do seletor.
RECENT_LIMIT = 20


class ProgressRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    # --- escrita -----------------------------------------------------------

    def record(self, card_id: str, result: AssessmentResult) -> int:
        """Guarda uma tentativa. Devolve o id da linha criada."""
        with transaction(self.connection) as conn:
            cursor = conn.execute(
                "INSERT INTO attempts (card_id, created_at, practice_score, "
                "word_accuracy, phoneme_accuracy, fluency, recognized_text, no_speech) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    card_id,
                    utcnow(),
                    result.scores.practice_score,
                    result.scores.word_accuracy,
                    result.scores.phoneme_accuracy,
                    result.scores.fluency,
                    result.recognized_text,
                    int(result.no_speech_detected),
                ),
            )
            # Erros recorrentes so tem valor se forem contados ao longo do tempo.
            for finding in result.findings:
                if finding.kind in ("no_speech", "pause"):
                    continue
                conn.execute(
                    "INSERT INTO finding_counts (card_id, kind, word, total) "
                    "VALUES (?, ?, ?, 1) "
                    "ON CONFLICT(card_id, kind, word) DO UPDATE SET total = total + 1",
                    (card_id, finding.kind, finding.word),
                )
            return int(cursor.lastrowid)

    # --- leitura -----------------------------------------------------------

    def card_progress(self, card_id: str) -> CardProgress | None:
        row = self.connection.execute(
            "SELECT COUNT(*) n, MAX(practice_score) best, AVG(practice_score) avg, "
            "MAX(created_at) last_at FROM attempts WHERE card_id = ? AND no_speech = 0",
            (card_id,),
        ).fetchone()
        if not row or not row["n"]:
            return None
        last = self.connection.execute(
            "SELECT practice_score FROM attempts WHERE card_id = ? AND no_speech = 0 "
            "ORDER BY id DESC LIMIT 1",
            (card_id,),
        ).fetchone()
        return CardProgress(
            card_id=card_id,
            attempts=row["n"],
            best_score=row["best"],
            last_score=last["practice_score"],
            average_score=row["avg"],
            last_practised=row["last_at"],
        )

    def study_state(self) -> StudyState:
        """Monta o retrato que o seletor precisa, em tres consultas."""
        attempts: dict[str, int] = {}
        best: dict[str, float] = {}
        for row in self.connection.execute(
            "SELECT card_id, COUNT(*) n, MAX(practice_score) best FROM attempts "
            "WHERE no_speech = 0 GROUP BY card_id"
        ):
            attempts[row["card_id"]] = row["n"]
            best[row["card_id"]] = row["best"]

        recent = [
            row["card_id"]
            for row in self.connection.execute(
                "SELECT card_id FROM attempts ORDER BY id DESC LIMIT ?", (RECENT_LIMIT,)
            )
        ]
        recent.reverse()
        return StudyState(attempts=attempts, best_score=best, recent=recent)

    def summary(self) -> dict:
        row = self.connection.execute(
            "SELECT COUNT(*) total, COUNT(DISTINCT card_id) cards, "
            "AVG(practice_score) avg FROM attempts WHERE no_speech = 0"
        ).fetchone()
        mastered = self.connection.execute(
            "SELECT COUNT(*) n FROM (SELECT card_id FROM attempts WHERE no_speech = 0 "
            "GROUP BY card_id HAVING MAX(practice_score) >= ?)",
            (MASTERY_SCORE,),
        ).fetchone()
        return {
            "total_attempts": row["total"] or 0,
            "cards_practised": row["cards"] or 0,
            "average_score": round(row["avg"], 1) if row["avg"] is not None else None,
            "cards_mastered": mastered["n"] or 0,
        }

    def common_mistakes(self, limit: int = 10) -> list[dict]:
        """Erros mais repetidos. So vale olhar o que aconteceu mais de uma vez."""
        return [
            dict(row)
            for row in self.connection.execute(
                "SELECT card_id, kind, word, total FROM finding_counts "
                "WHERE total > 1 ORDER BY total DESC LIMIT ?",
                (limit,),
            )
        ]

    def history(self, card_id: str | None = None, limit: int = 50) -> list[dict]:
        if card_id:
            rows = self.connection.execute(
                "SELECT * FROM attempts WHERE card_id = ? ORDER BY id DESC LIMIT ?",
                (card_id, limit),
            )
        else:
            rows = self.connection.execute(
                "SELECT * FROM attempts ORDER BY id DESC LIMIT ?", (limit,)
            )
        return [dict(row) for row in rows]
