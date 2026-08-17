"""Runtime configuration for Embeat UI.

Values are resolved with the following priority (highest first):
1. Real environment variables
2. A local ``.env`` file in the project root (optional)
3. Built-in defaults

The ``.env`` file is parsed with a tiny built-in parser so the project has no
third-party configuration dependencies.
"""

from __future__ import annotations

import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
ENV_FILE = APP_DIR / ".env"

_ENV_KEYS = (
    "EMBEAT_ROOT",
    "QDRANT_URL",
    "QDRANT_API_KEY",
    "QDRANT_COLLECTION",
    "QDRANT_TIMEOUT",
    "KUGOU_API_URL",
    "NETEASE_API_URL",
    "PROXY_URL",
    "UI_HOST",
    "UI_PORT",
    "INVITE_CODE",
    "AUTH_ENABLED",
    "PAIRING_CODE",
    "MB_LOOKUP_PATH",
)


def _as_bool(value: object) -> bool:
    return str(value).strip().casefold() not in ("", "0", "false", "no", "off")


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return values
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def _as_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class Config:
    """Resolved Embeat UI runtime configuration."""

    def __init__(self, overrides: dict[str, str] | None = None) -> None:
        raw = _parse_env_file(ENV_FILE)
        if overrides:
            raw.update(overrides)
        for key in _ENV_KEYS:
            if os.environ.get(key) is not None:
                raw[key] = os.environ[key]

        self.embeat_root = Path(raw.get("EMBEAT_ROOT") or str(APP_DIR.parent / "Embeat")).resolve()
        self.embeat_infer_dir = self.embeat_root / "infer"
        self.qdrant_url = str(raw.get("QDRANT_URL") or "http://127.0.0.1:6333").strip().rstrip("/")
        self.qdrant_api_key = str(raw.get("QDRANT_API_KEY") or "").strip()
        self.qdrant_collection = str(raw.get("QDRANT_COLLECTION") or "spotify_tracks").strip() or "spotify_tracks"
        self.qdrant_timeout = _as_int(raw.get("QDRANT_TIMEOUT", "30"), 30)
        self.kugou_api_url = str(raw.get("KUGOU_API_URL") or "").strip().rstrip("/")
        self.netease_api_url = str(raw.get("NETEASE_API_URL") or "").strip().rstrip("/")
        self.proxy_url = str(raw.get("PROXY_URL") or "").strip()
        self.ui_host = str(raw.get("UI_HOST") or "0.0.0.0").strip()
        self.ui_port = _as_int(raw.get("UI_PORT", "8765"), 8765)
        self.invite_code = str(raw.get("INVITE_CODE") or "").strip()
        self.auth_enabled = _as_bool(raw.get("AUTH_ENABLED", "true"))
        self.pairing_code = str(raw.get("PAIRING_CODE") or "").strip()
        self.mb_lookup_path = str(raw.get("MB_LOOKUP_PATH") or "").strip()

    def public_defaults(self) -> dict[str, str]:
        """Non-sensitive defaults exposed to the browser UI."""
        return {
            "netease_api_url": self.netease_api_url,
            "kugou_api_url": self.kugou_api_url,
            "proxy_url": self.proxy_url,
        }


CONFIG = Config()