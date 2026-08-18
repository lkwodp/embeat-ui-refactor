"""Track search endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.deps import require_service, require_user
from app.core.embeat import get_service
from app.schemas.models import SearchResponse, Track

router = APIRouter(tags=["search"])


@router.get("/api/search", response_model=SearchResponse)
def search(
    request: Request,
    name: str = Query(..., min_length=1, description="曲名"),
    artist: str = Query("", description="艺人名（可选）"),
    limit: int = Query(50, ge=1, le=100),
) -> SearchResponse:
    try:
        service = get_service()
        tracks = service.search(name, artist, limit=limit)
        user = require_user(request)
        service.app_db.add_history(
            user["id"],
            "search",
            f"{name} - {artist}".strip(" -"),
            {"name": name, "artist": artist, "count": len(tracks)},
            tracks,
        )
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return SearchResponse(tracks=[Track(**item) for item in tracks])