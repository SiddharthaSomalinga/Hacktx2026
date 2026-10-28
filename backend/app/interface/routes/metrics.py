"""GET /metrics for Prometheus (D60). Outside /api and the client contract; needs METRICS_TOKEN."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from app.interface.deps import ServicesDep, require_metrics_token

router = APIRouter(include_in_schema=False)


@router.get("/metrics", dependencies=[Depends(require_metrics_token)])
def metrics(services: ServicesDep) -> Response:
    body, media_type = services.metrics.render()
    return Response(content=body, media_type=media_type)
