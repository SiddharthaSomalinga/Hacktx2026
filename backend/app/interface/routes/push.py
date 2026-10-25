"""Web push opt-in (FR-51)."""

from __future__ import annotations

from fastapi import APIRouter

from app.interface import schemas
from app.interface.deps import ServicesDep, UserId

router = APIRouter(prefix="/api/push", tags=["push"])


@router.get("/vapid-public-key", response_model=schemas.VapidKeyOut)
def vapid_public_key(services: ServicesDep) -> schemas.VapidKeyOut:
    return schemas.VapidKeyOut(key=services.push.vapid_public_key())


@router.post("/subscribe", response_model=schemas.Ok)
def subscribe(body: schemas.SubscribeIn, user_id: UserId, services: ServicesDep) -> schemas.Ok:
    services.push.subscribe(user_id, body.endpoint, body.keys.p256dh, body.keys.auth)
    return schemas.Ok()


@router.delete("/subscribe", response_model=schemas.Ok)
def unsubscribe(body: schemas.UnsubscribeIn, user_id: UserId, services: ServicesDep) -> schemas.Ok:
    services.push.unsubscribe(user_id, body.endpoint)
    return schemas.Ok()
