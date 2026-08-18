"""Discovery endpoints: weekly, by genre, genre list, playlist seeds."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from app.api.deps import require_service, require_user

router = APIRouter(tags=["discover"])


@router.get("/api/discover/genres")
def discover_genres(request: Request, limit: int = Query(100, ge=1, le=500)) -> dict[str, Any]:
    user = require_user(request)
    return {"genres": require_service().genres(limit)}


@router.get("/api/discover/genre")
def discover_genre(
    request: Request,
    genre: str = Query(""),
    limit: int = Query(50, ge=1, le=50),
) -> dict[str, Any]:
    user = require_user(request)
    service = require_service()
    result = service.discover_genre(genre, limit)
    service.app_db.add_history(
        user["id"],
        "genre",
        f"流派：{result.get('genre', '')}",
        {"genre": result.get("genre"), "discoveryTitle": result.get("genre"), "note": "按热度浏览该流派"},
        result.get("tracks"),
    )
    return result


@router.get("/api/discover/weekly")
def discover_weekly(request: Request, limit: int = Query(50, ge=1, le=50)) -> dict[str, Any]:
    user = require_user(request)
    service = require_service()
    result = service.weekly_discovery(limit)
    service.app_db.add_history(
        user["id"],
        "weekly",
        f"每周新发现 {result.get('week', '')}",
        {"week": result.get("week"), "discoveryTitle": f"每周新发现 · {result.get('week', '')}", "note": result.get("note", "")},
        result.get("tracks"),
    )
    return result


@router.get("/api/playlist/seeds")
def playlist_seeds(
    request: Request,
    platform: str = Query("netease"),
    id: str = Query(""),
    max_seeds: int = Query(30, ge=1, le=30),
) -> dict[str, Any]:
    user = require_user(request)
    service = require_service()
    client = service._credential_client(user["id"], platform)
    return service.playlist_seeds(platform, id, max_seeds, client)