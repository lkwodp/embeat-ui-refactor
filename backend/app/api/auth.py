"""Authentication endpoints (register / login / logout / device pairing)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from embeat.config import CONFIG

from app.api.deps import (
    DEVICE_COOKIE,
    SESSION_COOKIE,
    check_auth_rate_limit,
    current_user,
    record_auth_failure,
    require_service,
    secure_compare,
)

router = APIRouter(tags=["auth"])

SESSION_MAX_AGE = 30 * 24 * 3600
DEVICE_MAX_AGE = 365 * 24 * 3600


class RegisterRequest(BaseModel):
    username: str
    password: str
    invite_code: str = ""


class LoginRequest(BaseModel):
    username: str
    password: str


class PairRequest(BaseModel):
    code: str = ""


def _set_cookie(response: Response, name: str, value: str, max_age: int) -> None:
    response.set_cookie(
        key=name,
        value=value,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        path="/",
    )


@router.get("/api/auth/me")
def auth_me(request: Request, response: Response) -> dict[str, Any]:
    service = require_service()
    database = service.app_db
    if not CONFIG.auth_enabled and not CONFIG.pairing_code:
        user = database.ensure_local_user()
        existing = database.get_user_by_device(request.cookies.get(DEVICE_COOKIE, ""))
        if existing:
            return {"user": user, "auth_enabled": False, "open_access": True}
        token = database.create_device_token(int(user["id"]))
        _set_cookie(response, DEVICE_COOKIE, token, DEVICE_MAX_AGE)
        return {"user": user, "auth_enabled": False, "open_access": True}
    user = current_user(request)
    if not user:
        message = "请先登录" if CONFIG.auth_enabled else "请先输入配对码"
        raise PermissionError(message)
    return {"user": user, "auth_enabled": CONFIG.auth_enabled}


@router.post("/api/auth/register")
def register(body: RegisterRequest, request: Request, response: Response) -> dict[str, Any]:
    if not CONFIG.auth_enabled:
        raise PermissionError("当前已关闭账号认证，请直接输入配对码")
    check_auth_rate_limit(request)
    service = require_service()
    database = service.app_db
    required_invite = CONFIG.invite_code
    if required_invite and not secure_compare(body.invite_code, required_invite):
        record_auth_failure(request)
        raise ValueError("邀请码无效")
    try:
        user = database.create_user(body.username, body.password)
    except ValueError as error:
        record_auth_failure(request)
        raise ValueError(str(error)) from error
    token = database.create_session(int(user["id"]))
    _set_cookie(response, SESSION_COOKIE, token, SESSION_MAX_AGE)
    return {"user": user, "auth_enabled": True}


@router.post("/api/auth/login")
def login(body: LoginRequest, request: Request, response: Response) -> dict[str, Any]:
    if not CONFIG.auth_enabled:
        raise PermissionError("当前已关闭账号认证，请直接输入配对码")
    check_auth_rate_limit(request)
    service = require_service()
    database = service.app_db
    user = database.authenticate(body.username, body.password)
    if not user:
        record_auth_failure(request)
        raise ValueError("用户名或密码错误")
    token = database.create_session(int(user["id"]))
    _set_cookie(response, SESSION_COOKIE, token, SESSION_MAX_AGE)
    return {"user": user, "auth_enabled": True}


@router.post("/api/device/pair")
def device_pair(body: PairRequest, request: Request, response: Response) -> dict[str, Any]:
    if CONFIG.auth_enabled:
        raise PermissionError("账号认证已开启，无需配对")
    if not CONFIG.pairing_code:
        raise PermissionError("当前为开放模式，无需配对")
    check_auth_rate_limit(request)
    service = require_service()
    database = service.app_db
    if not secure_compare(body.code, CONFIG.pairing_code):
        record_auth_failure(request)
        raise ValueError("配对码无效")
    user = database.ensure_local_user()
    token = database.create_device_token(int(user["id"]))
    _set_cookie(response, DEVICE_COOKIE, token, DEVICE_MAX_AGE)
    return {"user": user, "auth_enabled": False}


@router.post("/api/auth/logout")
def logout(request: Request, response: Response) -> dict[str, Any]:
    service = require_service()
    database = service.app_db
    session_token = request.cookies.get(SESSION_COOKIE, "")
    if session_token:
        database.delete_session(session_token)
    device_token = request.cookies.get(DEVICE_COOKIE, "")
    if device_token:
        database.delete_device_token(device_token)
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(DEVICE_COOKIE, path="/")
    return {"ok": True}
