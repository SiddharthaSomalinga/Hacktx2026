"""Block and report (FR-45)."""

from __future__ import annotations

from fastapi import APIRouter

from app.interface import schemas
from app.interface.deps import ServicesDep, UserId
from app.services.safety import Other

router = APIRouter(prefix="/api", tags=["safety"])


def _other(body: schemas.BlockIn) -> Other:
    return Other(user_id=body.user_id, request_id=body.request_id, match_id=body.match_id)


@router.post("/block", response_model=schemas.Ok)
def block(body: schemas.BlockIn, user_id: UserId, services: ServicesDep) -> schemas.Ok:
    services.safety.block(user_id, _other(body))
    return schemas.Ok()


@router.post("/report", response_model=schemas.Ok)
def report(body: schemas.ReportIn, user_id: UserId, services: ServicesDep) -> schemas.Ok:
    services.safety.report(user_id, _other(body), body.reason)
    return schemas.Ok()
