"""Public, no-login endpoints: health, map, recommendations, history (FR-8..14, FR-49)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from app.interface import schemas
from app.interface.deps import PathId, ServicesDep
from app.services.views import BuildingFullView, Cached

router = APIRouter(prefix="/api", tags=["public"])


def _cached(request: Request, cached: Cached) -> Response:
    headers = {"ETag": cached.etag, "Cache-Control": "no-cache"}
    if request.headers.get("if-none-match") == cached.etag:
        return Response(status_code=304, headers=headers)
    return Response(content=cached.content, media_type="application/json", headers=headers)


@router.get("/health", response_model=schemas.Health)
def health(services: ServicesDep) -> schemas.Health:
    return schemas.Health(ok=True, db=services.health.db_ok())


@router.get("/buildings", response_model=list[schemas.BuildingSummary])
def buildings(request: Request, services: ServicesDep) -> Response:
    return _cached(request, services.map.buildings())


@router.get("/buildings/{building_id}", response_model=schemas.BuildingDetail)
def building(building_id: PathId, request: Request, services: ServicesDep) -> Response:
    return _cached(request, services.map.building(building_id))


@router.get("/recommend", response_model=schemas.Recommendation | schemas.BuildingFull)
def recommend(
    services: ServicesDep,
    building_id: Annotated[str, Query(min_length=1, max_length=64)],
    floor: int | None = None,
    table_id: Annotated[str | None, Query(max_length=64)] = None,
) -> schemas.Recommendation | schemas.BuildingFull:
    result = services.map.recommend(building_id, floor, table_id)
    if isinstance(result, BuildingFullView):
        return schemas.BuildingFull(nearest_building_id=result.nearest_building_id)
    return schemas.Recommendation.model_validate(result)


@router.get("/buildings/{building_id}/history", response_model=list[schemas.HistoryPoint])
def history(building_id: PathId, services: ServicesDep) -> list[schemas.HistoryPoint]:
    return [
        schemas.HistoryPoint(hour=hour, open_avg=avg)
        for hour, avg in services.history.history(building_id)
    ]
