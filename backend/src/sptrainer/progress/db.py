"""Learner progress in SQLite.

SQLite because the app runs locally, for one person: one file, no server, no
configuration. The schema is deliberately shallow -- one row per attempt -- and
every statistic is derived by query. That way nothing needs a migration when the
shape of a report changes.

We store the score and the metrics, never the audio: voice recordings are
sensitive data and there is no reason for the trainer to accumulate them.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS attempts (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id           TEXT    NOT NULL,
    created_at        TEXT    NOT NULL,
    practice_score    REAL    NOT NULL,
    word_accuracy     REAL    NOT NULL,
    phoneme_accuracy  REAL,
    fluency           REAL,
    recognized_text   TEXT    NOT NULL DEFAULT '',
    no_speech         INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_attempts_card ON attempts(card_id);
CREATE INDEX IF NOT EXISTS idx_attempts_time ON attempts(created_at);

CREATE TABLE IF NOT EXISTS finding_counts (
    card_id   TEXT NOT NULL,
    kind      TEXT NOT NULL,
    word      TEXT,
    total     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (card_id, kind, word)
);
"""


@dataclass
class CardProgress:
    card_id: str
    attempts: int
    best_score: float
    last_score: float
    average_score: float
    last_practised: str | None = None

    @property
    def mastered(self) -> bool:
        from ..scheduling.selector import MASTERY_SCORE

        return self.best_score >= MASTERY_SCORE


def connect(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA)
    return connection


@contextmanager
def transaction(connection: sqlite3.Connection):
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
