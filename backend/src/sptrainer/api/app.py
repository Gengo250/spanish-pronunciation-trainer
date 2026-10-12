"""FastAPI application.

The routes are thin on purpose: they validate input, call a module and format
the output. All the real logic lives in `assessment`, `content`, `scheduling`
and `tts`, none of which know HTTP exists.
"""

from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, Response

from ..assessment.g2p import flatten, phonemize_text
from ..assessment.summary import summarize
from ..audio.decode import AudioDecodeError, decode_to_pcm16
from ..content.models import CardType, Category, Level
from ..content.repository import ContentError, dumps_csv, loads_csv
from ..content.validation import validate_deck
from ..scheduling.selector import Order, Pool, SelectionFilters
from ..tts.elevenlabs_client import SpeechError
from .schemas import AssessmentResponse, CardResponse, ProgressSummary
from .services import Services

logger = logging.getLogger(__name__)

# Vite's default dev ports. In a local production run the interface is served
# alongside the API.
DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def get_services(request: Request) -> Services:
    """Builds the services on the first request, not at import time.

    Importing the module must not open a database or read a deck: the tests need
    to inject doubles before anything comes up.
    """
    services = getattr(request.app.state, "services", None)
    if services is None:
        services = Services()
        request.app.state.services = services
    return services


def create_app(services: Services | None = None) -> FastAPI:
    app = FastAPI(
        title="Spanish Pronunciation Trainer",
        description="Spanish pronunciation training with local acoustic assessment.",
        version="0.1.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=DEV_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if services is not None:
        app.state.services = services

    _register(app)
    return app


def _register(app: FastAPI) -> None:

    # --- health and metadata -----------------------------------------------

    @app.get("/api/health")
    def health(svc: Services = Depends(get_services)) -> dict:
        """Says what is actually available, without loading any model."""
        return {
            "status": "ok",
            "deck": svc.deck.name,
            "cards": len(svc.deck),
            "accent": svc.settings.accent,
            "tts_configured": svc.settings.elevenlabs.configured,
            "phonemes_enabled": svc.settings.phonemes.enabled,
        }

    @app.get("/api/meta")
    def meta(svc: Services = Depends(get_services)) -> dict:
        present = {c.category.value for c in svc.deck.cards}
        types = {c.card_type.value for c in svc.deck.cards}
        return {
            "levels": [
                {"value": lv.value, "label": label}
                for lv, label in (
                    (Level.BEGINNER, "Iniciante"),
                    (Level.INTERMEDIATE, "Intermediário"),
                    (Level.ADVANCED, "Avançado"),
                )
            ],
            "categories": sorted(present),
            "card_types": sorted(types),
            "pools": [p.value for p in Pool],
            "orders": [o.value for o in Order],
        }

    # --- cards ---------------------------------------------------------------

    @app.get("/api/cards/next", response_model=CardResponse)
    def next_card(
        svc: Services = Depends(get_services),
        level: int | None = Query(None, ge=1, le=3),
        category: str | None = None,
        card_type: str | None = None,
        pool: Pool = Pool.ALL,
        order: Order = Order.RANDOM,
    ):
        filters = SelectionFilters(
            level=Level(level) if level else None,
            category=_enum_or_400(Category, category, "category"),
            card_type=_enum_or_400(CardType, card_type, "card_type"),
            pool=pool,
            order=order,
        )
        state = svc.progress.study_state()
        card = svc.selector.next_card(filters, state)
        if card is None:
            raise HTTPException(404, "No cards match those choices.")
        return CardResponse.of(
            card, state.attempts.get(card.id, 0), state.best_score.get(card.id),
            voice=svc.settings.espeak_voice,
        )

    @app.get("/api/cards/{card_id}", response_model=CardResponse)
    def get_card(card_id: str, svc: Services = Depends(get_services)):
        card = _find(svc, card_id)
        progress = svc.progress.card_progress(card_id)
        return CardResponse.of(
            card,
            progress.attempts if progress else 0,
            progress.best_score if progress else None,
            voice=svc.settings.espeak_voice,
        )

    # --- reference audio -----------------------------------------------------

    @app.get("/api/cards/{card_id}/audio")
    def card_audio(card_id: str, svc: Services = Depends(get_services)):
        """Reference audio. Synthesized once; served from cache ever after."""
        card = _find(svc, card_id)
        settings = svc.settings.elevenlabs
        try:
            result = svc.tts.synthesize(
                card.text, settings.voice_id, settings.model_id, settings.output_format
            )
        except SpeechError as exc:
            raise HTTPException(502, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc
        return Response(
            content=result.audio,
            media_type="audio/mpeg",
            headers={
                "X-Cache": "hit" if result.cached else "miss",
                "X-Characters-Billed": str(result.characters_billed),
                "Cache-Control": "public, max-age=31536000, immutable",
            },
        )

    # --- the learner's attempt -----------------------------------------------

    @app.post("/api/cards/{card_id}/attempt", response_model=AssessmentResponse)
    async def attempt(
        card_id: str,
        audio: UploadFile = File(...),
        svc: Services = Depends(get_services),
    ):
        card = _find(svc, card_id)
        raw = await audio.read()
        try:
            pcm = decode_to_pcm16(raw)
        except AudioDecodeError as exc:
            raise HTTPException(400, str(exc)) from exc

        # The card's own reference is the basis for comparison: without it the
        # per-sound analysis falls back to an absolute, far more conservative
        # threshold.
        expected = flatten(phonemize_text(card.text, svc.settings.espeak_voice))
        profile = svc.reference.profile(card.text, expected)

        result = svc.pipeline.assess(
            pcm,
            card.text,
            sample_rate=16000,
            reference_rate=profile.speech_rate,
            reference_gop=profile.gop,
        )
        svc.progress.record(card_id, result)
        return AssessmentResponse.of(card_id, result, summary=summarize(result))

    # --- progress ------------------------------------------------------------

    @app.get("/api/progress/summary", response_model=ProgressSummary)
    def progress_summary(svc: Services = Depends(get_services)):
        return ProgressSummary(**svc.progress.summary(), deck_size=len(svc.deck))

    @app.get("/api/progress/mistakes")
    def mistakes(limit: int = Query(10, ge=1, le=50),
                 svc: Services = Depends(get_services)) -> list[dict]:
        return svc.progress.common_mistakes(limit)

    @app.get("/api/progress/history")
    def history(card_id: str | None = None, limit: int = Query(50, ge=1, le=500),
                svc: Services = Depends(get_services)) -> list[dict]:
        return svc.progress.history(card_id, limit)

    # --- content -------------------------------------------------------------

    @app.get("/api/content/export")
    def export(fmt: str = Query("json", pattern="^(json|csv)$"),
               svc: Services = Depends(get_services)):
        if fmt == "csv":
            return PlainTextResponse(
                dumps_csv(svc.deck),
                media_type="text/csv",
                headers={"Content-Disposition": 'attachment; filename="deck.csv"'},
            )
        return Response(
            content=svc.deck.model_dump_json(indent=2, exclude_none=True),
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="deck.json"'},
        )

    @app.post("/api/content/validate")
    async def validate_upload(file: UploadFile = File(...)) -> dict:
        """Checks a CSV before importing. Does not touch the active deck."""
        text = (await file.read()).decode("utf-8", "replace")
        try:
            deck = loads_csv(text)
        except ContentError as exc:
            raise HTTPException(400, str(exc)) from exc
        report = validate_deck(deck)
        return {
            "cards": len(deck),
            "ok": report.ok,
            "errors": [
                {"card_id": i.card_id, "field": i.field_name, "message": i.message}
                for i in report.errors
            ],
            "warnings": [
                {"card_id": i.card_id, "field": i.field_name, "message": i.message}
                for i in report.warnings
            ],
        }


# --- utilities -------------------------------------------------------------

def _find(svc: Services, card_id: str):
    for card in svc.deck.cards:
        if card.id == card_id:
            return card
    raise HTTPException(404, f"Card {card_id!r} does not exist.")


def _enum_or_400(enum_cls, value, name):
    if value is None:
        return None
    try:
        return enum_cls(value)
    except ValueError as exc:
        options = ", ".join(e.value for e in enum_cls)
        raise HTTPException(400, f"Invalid {name}: {value!r}. Options: {options}") from exc


app = create_app()
