"""Bridge to the Embeat business core in ``backend/embeat/service.py``.

``EmbeatService`` (copied from embeat-ui-oss, HTTP layer removed, rewritten
here) holds all business logic: EmbeatDatabase integration, artist aliases,
matching, platform clients and the history store. This module puts
``backend/embeat`` and the vendored ``embeat/`` ML backend onto ``sys.path`` and
exposes ``EmbeatService`` as a lazy singleton so the FastAPI layer stays purely
about HTTP + orchestration.
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent
EMBEAT_CORE_DIR = BACKEND_DIR / "embeat"
EMBEAT_ML_DIR = PROJECT_ROOT / "embeat"

load_dotenv(BACKEND_DIR / ".env")

if str(EMBEAT_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(EMBEAT_CORE_DIR))

DEFAULT_EMBEAT_ROOT = EMBEAT_ML_DIR


def _locate_embeat_root() -> Path:
    configured = os.environ.get("EMBEAT_ROOT")
    if configured:
        root = Path(configured).resolve()
        if root.is_dir():
            return root
        raise RuntimeError(f"EMBEAT_ROOT 指向的目录不存在: {configured}")
    if (DEFAULT_EMBEAT_ROOT / "infer").is_dir():
        return DEFAULT_EMBEAT_ROOT
    raise RuntimeError(
        "找不到 Embeat ML 后端：请设置环境变量 EMBEAT_ROOT "
        f"（默认探测路径 {DEFAULT_EMBEAT_ROOT} 未包含 infer/）"
    )


if os.environ.get("EMBEAT_ROOT") is None:
    os.environ["EMBEAT_ROOT"] = str(_locate_embeat_root())

from service import EmbeatService  # noqa: E402

_service: EmbeatService | None = None
_service_lock = threading.Lock()
_service_ready = threading.Event()


def get_service() -> EmbeatService:
    """Return the shared EmbeatService, lazily constructing it on first use."""
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = EmbeatService()
                _service_ready.set()
    return _service


def service_ready() -> bool:
    return _service is not None


def run_on_ready(callback: Callable[[EmbeatService], Any]) -> Any:
    """Run ``callback(service)`` once the service has been constructed.

    Blocks until construction finishes; if the service was never created this
    blocks forever, matching the oss server's eager initialization behaviour.
    """
    _service_ready.wait()
    return callback(_service)


def reset_service() -> None:
    global _service
    with _service_lock:
        _service = None
        _service_ready.clear()