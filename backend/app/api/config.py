"""Server config and per-user preferences endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from embeat.config import CONFIG

from app.api.deps import require_service, require_user

router = APIRouter(tags=["config"])


class PreferencesUpdate(BaseModel):
    theme: str | None = None
    accent_hue: int | None = None


@router.get("/api/config")
def public_defaults(request: Request) -> dict[str, str]:
    require_user(request)
    return CONFIG.public_defaults()


@router.get("/api/preferences")
def get_preferences(request: Request) -> dict[str, Any]:
    user = require_user(request)
    return require_service().app_db.get_preferences(user["id"])


@router.post("/api/preferences")
def update_preferences(body: PreferencesUpdate, request: Request) -> dict[str, Any]:
    user = require_user(request)
    updates: dict[str, Any] = {}
    if body.theme is not None:
        updates["theme"] = body.theme
    if body.accent_hue is not None:
        updates["accent_hue"] = body.accent_hue
    return require_service().app_db.update_preferences(user["id"], **updates)
