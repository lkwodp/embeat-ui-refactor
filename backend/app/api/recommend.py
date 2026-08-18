"""Recommendation endpoints (single, multi-seed, artist)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.deps import require_service, require_user
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
def recommend(request: Request, body: RecommendRequest) -> RecommendResponse:
    try:
        service = get_service()
        payload = service.recommend(body.track_id, limit=body.limit)
        user = require_user(request)
        seed = payload.get("seed") or {}
        service.app_db.add_history(
            user["id"],
            "recommend",
            f"{seed.get('track_name', '')} - {seed.get('artist_name', '')}".strip(" -"),
            {"seed": seed, "elapsed_ms": payload.get("elapsed_ms", 0)},
            payload.get("tracks"),
        )
    except (ValueError, LookupError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return _recommend_response(payload)


@router.post("/api/recommend/multi", response_model=RecommendResponse)
def recommend_multi(request: Request, body: RecommendMultiRequest) -> RecommendResponse:
    try:
        service = get_service()
        payload = service.recommend_multi(body.track_ids, limit=body.limit)
        user = require_user(request)
        history_title = body.history_title or f"{len(payload.get('seeds', []))} 首种子电台"
        service.app_db.add_history(
            user["id"],
            "radio",
            history_title,
            {"seeds": payload.get("seeds", []), "elapsed_ms": payload.get("elapsed_ms", 0)},
            payload.get("tracks"),
        )
    except (ValueError, LookupError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return _recommend_response(payload)


@router.get("/api/recommend/artist", response_model=ArtistRecommendResponse)
def recommend_artist(
    request: Request,
    name: str = Query(..., min_length=1, description="歌手名"),
    limit: int = Query(20, ge=1, le=50),
) -> ArtistRecommendResponse:
    try:
        service = get_service()
        payload = service.recommend_artist(name, limit=limit)
        user = require_user(request)
        artist = payload.get("artist") or {}
        display_name = str(artist.get("artist_name_zh") or artist.get("artist_name") or name)
        service.app_db.add_history(
            user["id"],
            "artist_recommend",
            f"歌手电台：{display_name}",
            {
                "mode": "artist",
                "artist": artist,
                "representative_track": payload.get("representative_track"),
                "elapsed_ms": payload.get("elapsed_ms", 0),
            },
            payload.get("tracks"),
        )
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