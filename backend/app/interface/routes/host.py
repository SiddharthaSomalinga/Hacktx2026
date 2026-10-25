"""Host mode (FR-20..28, D17, D20, D24)."""

from __future__ import annotations

from fastapi import APIRouter

from app.interface import schemas
from app.interface.deps import ServicesDep, UserId

router = APIRouter(prefix="/api/host", tags=["host"])


@router.post("/link", response_model=schemas.LinkOut)
def link(body: schemas.LinkIn, user_id: UserId, services: ServicesDep) -> schemas.LinkOut:
    return schemas.LinkOut(session_id=services.host.link(user_id, body.seat_id))


@router.post("/topic", response_model=schemas.TopicOut)
def topic(body: schemas.TopicIn, user_id: UserId, services: ServicesDep) -> schemas.TopicOut:
    t = services.host.set_topic(user_id, body.topic_raw, body.about_me)
    return schemas.TopicOut(label=t.label, course_code=t.course_code, subject=t.subject)


@router.post("/toggle", response_model=schemas.ToggleOut)
def toggle(body: schemas.ToggleIn, user_id: UserId, services: ServicesDep) -> schemas.ToggleOut:
    return schemas.ToggleOut(open=services.host.toggle(user_id, body.open))


@router.post("/mute", response_model=schemas.MuteOut)
def mute(body: schemas.MuteIn, user_id: UserId, services: ServicesDep) -> schemas.MuteOut:
    return schemas.MuteOut(muted=services.host.mute(user_id, body.muted))


@router.post("/confirm", response_model=schemas.ConfirmOut)
def confirm(user_id: UserId, services: ServicesDep) -> schemas.ConfirmOut:
    return schemas.ConfirmOut.model_validate(services.host.confirm(user_id))


@router.get("/inbox", response_model=list[schemas.InboxItem])
def inbox(user_id: UserId, services: ServicesDep) -> list[schemas.InboxItem]:
    return [schemas.InboxItem.model_validate(i) for i in services.host.inbox(user_id)]
