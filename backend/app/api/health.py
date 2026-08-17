"""Health and status endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.embeat import get_service, service_ready
from app.schemas.models import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    try:
        service = get_service()
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    ready = service_ready()
    points = 0
    if ready:
        try:
            points = service.database.record_count
        except AttributeError:
            points = 0
    return HealthResponse(ready=ready, points=points)