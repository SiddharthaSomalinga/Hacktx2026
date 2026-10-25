"""Node ingest (FR-1..7, HW-8)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.domain.types import Reading
from app.interface import schemas
from app.interface.deps import ServicesDep, require_node_key

router = APIRouter(prefix="/api", tags=["nodes"])


@router.post("/readings", response_model=schemas.LedsOut, dependencies=[Depends(require_node_key)])
def readings(body: schemas.ReadingsIn, services: ServicesDep) -> schemas.LedsOut:
    leds = services.readings.ingest(
        body.node_id,
        [Reading(r.seat_id, r.object_present, r.human_present) for r in body.readings],
    )
    return schemas.LedsOut(leds=leds)
