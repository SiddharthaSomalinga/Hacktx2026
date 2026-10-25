"""Demo login, logout and "who am I" (FR-14..16, D9)."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.interface import schemas
from app.interface.deps import OptionalUserId, ServicesDep, UserId

router = APIRouter(prefix="/api", tags=["account"])


@router.get("/demo-users", response_model=list[schemas.DemoUser])
def demo_users(services: ServicesDep) -> list[schemas.DemoUser]:
    return [schemas.DemoUser.model_validate(u) for u in services.auth.demo_users()]


@router.post("/login", response_model=schemas.DemoUser)
def login(body: schemas.LoginIn, request: Request, services: ServicesDep) -> schemas.DemoUser:
    user = services.auth.login(body.user_id)
    request.session.clear()
    request.session["user_id"] = user.id
    return schemas.DemoUser.model_validate(user)


@router.post("/logout", response_model=schemas.Ok)
def logout(request: Request, _: UserId) -> schemas.Ok:
    request.session.clear()
    return schemas.Ok()


@router.get("/me", response_model=schemas.MeOut)
def me(user_id: OptionalUserId, services: ServicesDep) -> schemas.MeOut:
    return schemas.MeOut.model_validate(services.auth.me(user_id))
