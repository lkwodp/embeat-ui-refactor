"""Recommendation endpoints (single, multi-seed, artist)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.core.embeat import get_service
from app.schemas.models import (
    Artist,
    ArtistRecommendResponse,
    RecommendMultiRequest,
    RecommendRequest,
    RecommendResponse,
    Track,
)

router = APIRouter(tags=["recommend"])


def _recommend_response(payload: dict) -> RecommendResponse:
    seeds = payload.get("seeds") or []
    seed = payload.get("seed")
    return RecommendResponse(
        seed=Track(**seed) if seed else None,
        seeds=[Track(**item) for item in seeds] if seeds else None,
        tracks=[Track(**item) for item in payload["tracks"]],
        elapsed_ms=payload.get("elapsed_ms", 0),
    )


@router.post("/api/recommend", response_model=RecommendResponse)
def recommend(request: RecommendRequest) -> RecommendResponse:
    try:
        service = get_service()
        payload = service.recommend(request.track_id, limit=request.limit)
    except (ValueError, LookupError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return _recommend_response(payload)


@router.post("/api/recommend/multi", response_model=RecommendResponse)
def recommend_multi(request: RecommendMultiRequest) -> RecommendResponse:
    try:
        service = get_service()
        payload = service.recommend_multi(request.track_ids, limit=request.limit)
    except (ValueError, LookupError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return _recommend_response(payload)


@router.get("/api/recommend/artist", response_model=ArtistRecommendResponse)
def recommend_artist(
    name: str = Query(..., min_length=1, description="歌手名"),
    limit: int = Query(20, ge=1, le=50),
) -> ArtistRecommendResponse:
    try:
        service = get_service()
        payload = service.recommend_artist(name, limit=limit)
    except (ValueError, LookupError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    artist = payload["artist"]
    return ArtistRecommendResponse(
        mode="artist",
        artist=Artist(**artist),
        representative_track=Track(**payload["representative_track"]),
        tracks=[Track(**item) for item in payload["tracks"]],
        elapsed_ms=payload.get("elapsed_ms", 0),
    )