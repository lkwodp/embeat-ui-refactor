"""Authentication and current-user resolution for the FastAPI layer.

Mirrors the oss server's cookie-based auth (``embeat_session`` /
``embeat_device``) so the React UI port can rely on the same contracts:

- ``AUTH_ENABLED=true``  -> login/register with ``embeat_session`` cookie
- ``AUTH_ENABLED=false`` + ``PAIRING_CODE`` -> device pairing cookie
- open access (both off) -> a local user is used directly
"""

from __future__ import annotations

import secrets
import time
import threading
from typing import Any

from fastapi import HTTPException, Request

from app.core.embeat import get_service

from embeat.config import CONFIG
from embeat.service import EmbeatService

SESSION_COOKIE = "embeat_session"
DEVICE_COOKIE = "embeat_device"

_AUTH_LOCK = threading.Lock()
_AUTH_ATTEMPTS: dict[str, list[float]] = {}
_CAPTCHA_LOCK = threading.Lock()
_CAPTCHA_ATTEMPTS: dict[str, list[float]] = {}


def _cookie(request: Request, name: str) -> str:
    return request.cookies.get(name, "")


def current_user(request: Request) -> dict[str, Any] | None:
    """Resolve the current user the same way the oss server does."""
    service = get_service()
    if not CONFIG.auth_enabled:
        if not CONFIG.pairing_code:
            return service.app_db.ensure_local_user()
        return service.app_db.get_user_by_device(_cookie(request, DEVICE_COOKIE))
    return service.app_db.get_user_by_session(_cookie(request, SESSION_COOKIE))


def require_user(request: Request) -> dict[str, Any]:
    user = current_user(request)
    if not user:
        if CONFIG.auth_enabled:
            raise PermissionError("请先登录")
        raise PermissionError("请先输入配对码")
    return user


def require_service() -> EmbeatService:
    try:
        return get_service()
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


def check_auth_rate_limit(request: Request) -> None:
    now = time.time()
    ip = request.client.host if request.client else "unknown"
    with _AUTH_LOCK:
        recent = [stamp for stamp in _AUTH_ATTEMPTS.get(ip, []) if stamp > now - 900]
        if len(recent) >= 10:
            raise PermissionError("登录尝试过于频繁，请 15 分钟后重试")
        _AUTH_ATTEMPTS[ip] = recent


def record_auth_failure(request: Request) -> None:
    now = time.time()
    ip = request.client.host if request.client else "unknown"
    with _AUTH_LOCK:
        _AUTH_ATTEMPTS.setdefault(ip, []).append(now)


def check_captcha_rate_limit(user_id: int, platform: str, phone: str) -> None:
    now = time.time()
    key = f"{user_id}:{platform}:{phone}"
    with _CAPTCHA_LOCK:
        recent = [stamp for stamp in _CAPTCHA_ATTEMPTS.get(key, []) if stamp > now - 900]
        if recent and recent[-1] > now - 60:
            raise PermissionError("验证码发送过于频繁，请 60 秒后重试")
        if len(recent) >= 5:
            raise PermissionError("验证码发送次数过多，请 15 分钟后重试")
        recent.append(now)
        _CAPTCHA_ATTEMPTS[key] = recent


def secure_compare(left: str, right: str) -> bool:
    return secrets.compare_digest(left, right)
