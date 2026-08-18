"""Platform credential endpoints: netease / kugou status, config, playlists,
captcha send/login, and export start/status."""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Body, Query, Request
from pydantic import BaseModel

from app.api.deps import (
    check_captcha_rate_limit,
    require_service,
    require_user,
)

router = APIRouter(tags=["platforms"])


class PlatformConfig(BaseModel):
    api_url: str = ""
    proxy_url: str = ""
    cookie: str = ""
    clear: bool = False


class CaptchaSend(BaseModel):
    phone: str = ""
    api_url: str = ""
    proxy_url: str = ""
    country_code: str = "86"


class CaptchaLogin(BaseModel):
    phone: str = ""
    code: str = ""
    api_url: str = ""
    proxy_url: str = ""
    country_code: str = "86"


class ExportStart(BaseModel):
    target: str = "netease"
    tracks: list[dict[str, Any]] = []
    netease: dict[str, Any] = {}
    kugou: dict[str, Any] = {}


@router.get("/api/netease/status")
def netease_status(request: Request) -> dict[str, Any]:
    user = require_user(request)
    return require_service().platform_status(user["id"], "netease")


@router.get("/api/netease/config")
def netease_config(request: Request) -> dict[str, Any]:
    user = require_user(request)
    return require_service().platform_status(user["id"], "netease")


@router.get("/api/netease/playlists")
def netease_playlists(request: Request) -> dict[str, Any]:
    user = require_user(request)
    return {"playlists": require_service()._credential_client(user["id"], "netease").playlists()}


@router.get("/api/kugou/status")
def kugou_status(request: Request) -> dict[str, Any]:
    user = require_user(request)
    return require_service().platform_status(user["id"], "kugou")


@router.get("/api/kugou/config")
def kugou_config(request: Request) -> dict[str, Any]:
    user = require_user(request)
    return require_service().platform_status(user["id"], "kugou")


@router.get("/api/kugou/playlists")
def kugou_playlists(request: Request) -> dict[str, Any]:
    user = require_user(request)
    return {"playlists": require_service()._credential_client(user["id"], "kugou").playlists()}


@router.post("/api/netease/config")
def netease_config_save(body: PlatformConfig, request: Request) -> dict[str, Any]:
    user = require_user(request)
    service = require_service()
    if body.clear:
        service.app_db.clear_credential(user["id"], "netease")
        return {"configured": False}
    return service.configure_platform(user["id"], "netease", body.model_dump())


@router.post("/api/kugou/config")
def kugou_config_save(body: PlatformConfig, request: Request) -> dict[str, Any]:
    user = require_user(request)
    service = require_service()
    if body.clear:
        service.app_db.clear_credential(user["id"], "kugou")
        return {"configured": False}
    return service.configure_platform(user["id"], "kugou", body.model_dump())


@router.post("/api/netease/captcha/send")
def netease_captcha_send(body: CaptchaSend, request: Request) -> dict[str, Any]:
    user = require_user(request)
    service = require_service()
    check_captcha_rate_limit(user["id"], "netease", body.phone)
    return service.send_phone_captcha("netease", body.api_url, body.proxy_url, body.phone, body.country_code)


@router.post("/api/kugou/captcha/send")
def kugou_captcha_send(body: CaptchaSend, request: Request) -> dict[str, Any]:
    user = require_user(request)
    service = require_service()
    check_captcha_rate_limit(user["id"], "kugou", body.phone)
    return service.send_phone_captcha("kugou", body.api_url, body.proxy_url, body.phone, body.country_code)


@router.post("/api/netease/captcha/login")
def netease_captcha_login(body: CaptchaLogin, request: Request) -> dict[str, Any]:
    user = require_user(request)
    service = require_service()
    return service.login_phone_captcha(user["id"], "netease", body.api_url, body.proxy_url, body.phone, body.code, body.country_code)


@router.post("/api/kugou/captcha/login")
def kugou_captcha_login(body: CaptchaLogin, request: Request) -> dict[str, Any]:
    user = require_user(request)
    service = require_service()
    return service.login_phone_captcha(user["id"], "kugou", body.api_url, body.proxy_url, body.phone, body.code, body.country_code)


@router.post("/api/export/start")
def export_start(body: ExportStart, request: Request) -> dict[str, Any]:
    user = require_user(request)
    service = require_service()
    clients = {
        platform: service._credential_client(user["id"], platform)
        for platform in ("netease", "kugou")
    }
    return service.export_manager.start(
        body.target,
        body.tracks,
        body.netease,
        body.kugou,
        user_id=user["id"],
        clients=clients,
        app_db=service.app_db,
    )


@router.get("/api/export/status")
def export_status(request: Request, id: str = Query("")) -> dict[str, Any]:
    user = require_user(request)
    return require_service().export_manager.status(id, user["id"])