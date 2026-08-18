"""History and export-log endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Query
from pydantic import BaseModel, Field

from app.api.deps import require_service, require_user

router = APIRouter(tags=["history"])


class HistoryAdd(BaseModel):
    kind: str = "search"
    type: str | None = None
    title: str = "未命名记录"
    summary: Any = None
    data: Any = None
    tracks: Any = None


@router.get("/api/history")
def list_history(
    request: Request,
    kind: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
) -> dict[str, Any]:
    user = require_user(request)
    return require_service().app_db.list_history(user["id"], kind, page, page_size)


@router.post("/api/history")
def add_history(body: HistoryAdd, request: Request) -> dict[str, Any]:
    user = require_user(request)
    kind = body.kind or body.type or "search"
    summary = body.summary if body.summary is not None else body.data
    require_service().app_db.add_history(user["id"], kind, body.title, summary, body.tracks)
    return {"ok": True}


@router.get("/api/export/history")
def export_history(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
) -> dict[str, Any]:
    user = require_user(request)
    return require_service().app_db.list_export_logs(user["id"], page, page_size)