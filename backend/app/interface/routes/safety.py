"""Block and report (FR-45)."""

from __future__ import annotations

from fastapi import APIRouter

from app.interface import schemas
from app.interface.deps import ServicesDep, UserId

router = APIRouter(prefix="/api", tags=["safety"])


@router.post("/block", response_model=schemas.Ok)
def block(body: schemas.BlockIn, user_id: UserId, services: ServicesDep) -> schemas.Ok:
    services.safety.block(user_id, body.user_id)
    return schemas.Ok()


@router.post("/report", response_model=schemas.Ok)
def report(body: schemas.ReportIn, user_id: UserId, services: ServicesDep) -> schemas.Ok:
    services.safety.report(user_id, body.user_id, body.reason)
    return schemas.Ok()
