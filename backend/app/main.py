"""FastAPI application entrypoint for embeat-web.

Brings together the API routers on top of the oss ``EmbeatService`` bridge and
serves the built React frontend from ``frontend/dist`` when present.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import (
    auth,
    config,
    discover,
    health,
    history,
    platforms,
    recommend,
    search,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

app = FastAPI(title="Embeat Web", version="0.1.0")

app.include_router(health.router)
app.include_router(search.router)
app.include_router(recommend.router)
app.include_router(config.router)
app.include_router(auth.router)
app.include_router(discover.router)
app.include_router(history.router)
app.include_router(platforms.router)


@app.exception_handler(PermissionError)
async def permission_error_handler(request: Request, exc: PermissionError):
    message = str(exc)
    status = 429 if any(word in message for word in ("频繁", "过多")) else 401
    return JSONResponse(status_code=status, content={"error": message})


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"error": str(exc)})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    return JSONResponse(status_code=500, content={"error": str(exc)})


if FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        index = FRONTEND_DIST / "index.html"
        return FileResponse(index) if index.is_file() else JSONResponse(
            status_code=404, content={"error": "前端未构建，请先运行 npm run build"}
        )