"""Leitura e escrita de baralhos em JSON e CSV.

JSON e o formato nativo (aninhamento e listas saem de graca). CSV existe porque
e onde conteudo de idioma costuma ser escrito de verdade -- planilha, revisao a
quatro maos, importacao de material pronto. Campos de lista viram texto separado
por `;` na ida e voltam a ser lista na volta, entao o round-trip e sem perda.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from pydantic import ValidationError

from .models import Deck, Flashcard

LIST_SEPARATOR = ";"
LIST_FIELDS = ("phoneme_targets", "expected_phonemes", "tags")

CSV_COLUMNS = (
    "id", "text", "translation", "language", "translation_language",
    "level", "card_type", "category", "grammar_note", "pronunciation_focus",
    "phoneme_targets", "expected_phonemes", "example", "example_translation",
    "tags", "audio_path",
)


class ContentError(RuntimeError):
    """Baralho malformado."""


# --- JSON ------------------------------------------------------------------

def load_json(path: str | Path) -> Deck:
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContentError(f"baralho nao encontrado: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ContentError(f"JSON invalido em {path}: {exc}") from exc
    try:
        return Deck.model_validate(raw)
    except ValidationError as exc:
        raise ContentError(f"baralho invalido em {path}: {exc}") from exc


def save_json(deck: Deck, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        deck.model_dump_json(indent=2, exclude_none=True) + "\n", encoding="utf-8"
    )
    return path


# --- CSV -------------------------------------------------------------------

def _to_row(card: Flashcard) -> dict[str, str]:
    data = card.model_dump(mode="json")
    row: dict[str, str] = {}
    for column in CSV_COLUMNS:
        value = data.get(column)
        if column in LIST_FIELDS:
            row[column] = LIST_SEPARATOR.join(value or [])
        else:
            row[column] = "" if value is None else str(value)
    return row


def _from_row(row: dict[str, str]) -> Flashcard:
    data: dict[str, object] = {}
    for column in CSV_COLUMNS:
        value = (row.get(column) or "").strip()
        if column in LIST_FIELDS:
            data[column] = [v for v in (p.strip() for p in value.split(LIST_SEPARATOR)) if v]
        elif value == "":
            continue
        elif column == "level":
            data[column] = int(value)
        else:
            data[column] = value
    try:
        return Flashcard.model_validate(data)
    except ValidationError as exc:
        raise ContentError(f"linha invalida (id={row.get('id')!r}): {exc}") from exc


def dumps_csv(deck: Deck) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(CSV_COLUMNS), lineterminator="\n")
    writer.writeheader()
    for card in deck.cards:
        writer.writerow(_to_row(card))
    return buffer.getvalue()


def loads_csv(text: str, name: str = "imported") -> Deck:
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ContentError("CSV sem cabecalho.")
    missing = {"id", "text", "translation", "level", "card_type", "category"} - set(
        reader.fieldnames
    )
    if missing:
        raise ContentError(f"CSV sem as colunas obrigatorias: {', '.join(sorted(missing))}")
    return Deck(name=name, cards=[_from_row(row) for row in reader])


def save_csv(deck: Deck, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps_csv(deck), encoding="utf-8")
    return path


def load_csv(path: str | Path) -> Deck:
    path = Path(path)
    try:
        return loads_csv(path.read_text(encoding="utf-8"), name=path.stem)
    except FileNotFoundError as exc:
        raise ContentError(f"baralho nao encontrado: {path}") from exc
