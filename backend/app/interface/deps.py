"""Request-scoped dependencies: services, the logged-in user, the node key."""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Depends, Header, Request

from app.services.container import Services
from app.services.errors import unauthorized


def get_services(request: Request) -> Services:
    services: Services = request.app.state.services
    return services


ServicesDep = Annotated[Services, Depends(get_services)]


def current_user_id(request: Request, services: ServicesDep) -> str:
    user_id = request.session.get("user_id")
    if not isinstance(user_id, str) or services.auth.user(user_id) is None:
        raise unauthorized("not_logged_in", "Log in to do this")
    return user_id


def optional_user_id(request: Request) -> str | None:
    user_id = request.session.get("user_id")
    return user_id if isinstance(user_id, str) else None


UserId = Annotated[str, Depends(current_user_id)]
OptionalUserId = Annotated[str | None, Depends(optional_user_id)]


def require_node_key(request: Request, x_node_key: Annotated[str | None, Header()] = None) -> None:
    expected: str = request.app.state.node_key
    if x_node_key is None or not hmac.compare_digest(x_node_key.encode(), expected.encode()):
        raise unauthorized("invalid_node_key", "Missing or wrong X-Node-Key header")
