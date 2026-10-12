"""Progresso do aluno em SQLite.

SQLite porque o app roda local, para uma pessoa: um arquivo, zero servidor, zero
configuracao. O esquema e deliberadamente raso -- uma linha por tentativa -- e
toda estatistica e derivada por consulta. Assim nada precisa de migracao quando a
forma do relatorio mudar.

Guardamos a nota e as metricas, nunca o audio: gravacao de voz e dado sensivel e
nao ha motivo para o trainer acumular isso.
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
