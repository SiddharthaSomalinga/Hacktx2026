"""Host answers: accept, decline, decline-and-mute (FR-36, 37, D20)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body

from app.interface import schemas
from app.interface.deps import ServicesDep, UserId

router = APIRouter(prefix="/api/requests", tags=["requests"])


@router.post("/{request_id}/accept", response_model=schemas.AcceptOut)
def accept(request_id: str, user_id: UserId, services: ServicesDep) -> schemas.AcceptOut:
    return schemas.AcceptOut(match_id=services.requests.accept(user_id, request_id))


@router.post("/{request_id}/decline", response_model=schemas.RequestStatusOut)
def decline(
    request_id: str,
    user_id: UserId,
    services: ServicesDep,
    body: Annotated[schemas.DeclineIn | None, Body()] = None,
) -> schemas.RequestStatusOut:
    mute = body.mute if body is not None else False
    return schemas.RequestStatusOut(status=services.requests.decline(user_id, request_id, mute))
