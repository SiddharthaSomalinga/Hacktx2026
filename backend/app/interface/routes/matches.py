"""Match view, arrival and cancellation (FR-38..42, D25)."""

from __future__ import annotations

from fastapi import APIRouter

from app.interface import schemas
from app.interface.deps import ServicesDep, UserId

router = APIRouter(prefix="/api/matches", tags=["matches"])


@router.get("/{match_id}", response_model=schemas.MatchOut)
def view(match_id: str, user_id: UserId, services: ServicesDep) -> schemas.MatchOut:
    return schemas.MatchOut.model_validate(services.match.view(user_id, match_id))


@router.post("/{match_id}/arrived", response_model=schemas.MatchStatusOut)
def arrived(match_id: str, user_id: UserId, services: ServicesDep) -> schemas.MatchStatusOut:
    return schemas.MatchStatusOut(status=services.match.arrived(user_id, match_id))


@router.post("/{match_id}/cancel", response_model=schemas.MatchStatusOut)
def cancel(match_id: str, user_id: UserId, services: ServicesDep) -> schemas.MatchStatusOut:
    return schemas.MatchStatusOut(status=services.match.cancel(user_id, match_id))
