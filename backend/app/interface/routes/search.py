"""Searches and the join cascade (FR-29..35)."""

from __future__ import annotations

from fastapi import APIRouter

from app.interface import schemas
from app.interface.deps import ServicesDep, UserId

router = APIRouter(prefix="/api/search", tags=["search"])


@router.post("", response_model=schemas.SearchOut)
def create(body: schemas.SearchIn, user_id: UserId, services: ServicesDep) -> schemas.SearchOut:
    return schemas.SearchOut.model_validate(
        services.search.create(user_id, body.topic_raw, body.group)
    )


@router.post("/{search_id}/join", response_model=schemas.SearchStatusOut)
def join(search_id: str, user_id: UserId, services: ServicesDep) -> schemas.SearchStatusOut:
    return schemas.SearchStatusOut.model_validate(services.search.join(user_id, search_id))


@router.get("/{search_id}", response_model=schemas.SearchStatusOut)
def status(search_id: str, user_id: UserId, services: ServicesDep) -> schemas.SearchStatusOut:
    return schemas.SearchStatusOut.model_validate(services.search.status(user_id, search_id))


@router.post("/{search_id}/cancel", response_model=schemas.SearchCancelOut)
def cancel(search_id: str, user_id: UserId, services: ServicesDep) -> schemas.SearchCancelOut:
    return schemas.SearchCancelOut(status=services.search.cancel(user_id, search_id))
