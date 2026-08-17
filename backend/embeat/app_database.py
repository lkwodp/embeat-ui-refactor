from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from config import CONFIG

try:
    from cryptography.fernet import Fernet
except ImportError as exc:  # pragma: no cover - deployment dependency check
    Fernet = None
    _FERNET_ERROR = exc


PBKDF2_ITERATIONS = 240_000
THEME_IDS = frozenset({
    "auto", "studio", "night", "ocean", "contrast",
    "forest", "berry", "graphite", "solar",
})
_UNSET = object()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hash_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError("密码至少需要 8 位")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, iterations, salt_hex, digest_hex = encoded.split("$", 3)
        if scheme != "pbkdf2":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations))
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


class AppDatabase:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.data_dir = root / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / "embeat.db"
        self.secret_path = self.data_dir / "secret.key"
        self.lock = threading.RLock()
        self._fernet = self._load_fernet()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _init_schema(self) -> None:
        with self.lock, closing(self._connect()) as db, db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                  password_hash TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  last_login_at TEXT
                );
                CREATE TABLE IF NOT EXISTS sessions (
                  token_hash TEXT PRIMARY KEY,
                  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                  created_at TEXT NOT NULL,
                  expires_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS device_tokens (
                  token_hash TEXT PRIMARY KEY,
                  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                  created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS credentials (
                  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                  platform TEXT NOT NULL,
                  api_url TEXT, proxy_url TEXT, cookie_enc TEXT,
                  uid TEXT, extra_json TEXT,
                  updated_at TEXT NOT NULL, last_validated_at TEXT,
                  PRIMARY KEY (user_id, platform)
                );
                CREATE TABLE IF NOT EXISTS history (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                  kind TEXT NOT NULL, title TEXT NOT NULL, summary_json TEXT,
                  tracks_json TEXT, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS export_log (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                  target TEXT NOT NULL, platform TEXT NOT NULL,
                  playlist_id TEXT, playlist_name TEXT,
                  total INTEGER, added INTEGER, skipped INTEGER, failed INTEGER,
                  detail_json TEXT, status TEXT, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
                CREATE INDEX IF NOT EXISTS idx_history_user_created ON history(user_id, created_at DESC);
                """
            )
            columns = {row[1] for row in db.execute("PRAGMA table_info(users)").fetchall()}
            if "theme" not in columns:
                db.execute("ALTER TABLE users ADD COLUMN theme TEXT")
            if "accent_hue" not in columns:
                db.execute("ALTER TABLE users ADD COLUMN accent_hue INTEGER")
            rows = db.execute("SELECT user_id,platform,extra_json FROM credentials WHERE extra_json IS NOT NULL").fetchall()
            for row in rows:
                try:
                    extra = json.loads(row["extra_json"] or "{}")
                except (ValueError, TypeError):
                    extra = {}
                sanitized = {"phone": extra.get("phone")} if extra.get("phone") else {}
                if extra != sanitized:
                    db.execute("UPDATE credentials SET extra_json=? WHERE user_id=? AND platform=?", (json.dumps(sanitized, ensure_ascii=False), row["user_id"], row["platform"]))

    def _load_fernet(self):
        if Fernet is None:
            raise RuntimeError("缺少 cryptography 依赖，请执行 conda install cryptography") from _FERNET_ERROR
        if self.secret_path.exists():
            key = self.secret_path.read_bytes().strip()
        else:
            key = Fernet.generate_key()
            self.secret_path.write_bytes(key)
            try:
                os.chmod(self.secret_path, 0o600)
            except OSError:
                pass
        return Fernet(key)

    def create_user(self, username: str, password: str) -> dict[str, Any]:
        username = username.strip()
        if not username or len(username) > 80:
            raise ValueError("用户名不能为空且不能超过 80 个字符")
        invite = CONFIG.invite_code
        with self.lock, closing(self._connect()) as db, db:
            try:
                cursor = db.execute("INSERT INTO users(username,password_hash,created_at) VALUES(?,?,?)", (username, hash_password(password), utc_now()))
            except sqlite3.IntegrityError as exc:
                raise ValueError("用户名已存在") from exc
            return {"id": cursor.lastrowid, "username": username}

    def authenticate(self, username: str, password: str) -> dict[str, Any] | None:
        with self.lock, closing(self._connect()) as db, db:
            row = db.execute("SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username.strip(),)).fetchone()
            if not row or not verify_password(password, row["password_hash"]):
                return None
            now = utc_now()
            db.execute("UPDATE users SET last_login_at=? WHERE id=?", (now, row["id"]))
            return {"id": row["id"], "username": row["username"]}

    def create_session(self, user_id: int, days: int = 30) -> str:
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        with self.lock, closing(self._connect()) as db, db:
            db.execute("INSERT INTO sessions VALUES(?,?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), user_id, now.isoformat(timespec="seconds"), (now + timedelta(days=days)).isoformat(timespec="seconds")))
        return token

    def get_user_by_session(self, token: str, slide_days: int = 30) -> dict[str, Any] | None:
        if not token:
            return None
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with self.lock, closing(self._connect()) as db, db:
            row = db.execute("SELECT u.id,u.username,s.expires_at FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=?", (token_hash,)).fetchone()
            if not row:
                return None
            try:
                expires = datetime.fromisoformat(row["expires_at"])
            except ValueError:
                return None
            if expires <= datetime.now(timezone.utc):
                db.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))
                return None
            renewed = (datetime.now(timezone.utc) + timedelta(days=slide_days)).isoformat(timespec="seconds")
            db.execute("UPDATE sessions SET expires_at=? WHERE token_hash=?", (renewed, token_hash))
            return {"id": row["id"], "username": row["username"]}

    def get_preferences(self, user_id: int) -> dict[str, Any]:
        with self.lock, closing(self._connect()) as db, db:
            row = db.execute("SELECT theme,accent_hue FROM users WHERE id=?", (user_id,)).fetchone()
        if not row:
            raise ValueError("用户不存在")
        return {"theme": row["theme"], "accent_hue": row["accent_hue"]}

    def update_preferences(self, user_id: int, *, theme: Any = _UNSET, accent_hue: Any = _UNSET) -> dict[str, Any]:
        if theme is not _UNSET:
            theme = str(theme).strip().casefold()
            if theme not in THEME_IDS:
                raise ValueError("无效的主题")
        if accent_hue is not _UNSET:
            if accent_hue in (None, ""):
                accent_hue = None
            else:
                try:
                    accent_hue = max(0, min(359, int(accent_hue)))
                except (TypeError, ValueError) as exc:
                    raise ValueError("无效的强调色色相") from exc
        with self.lock, closing(self._connect()) as db, db:
            current = db.execute("SELECT theme,accent_hue FROM users WHERE id=?", (user_id,)).fetchone()
            if not current:
                raise ValueError("用户不存在")
            next_theme = current["theme"] if theme is _UNSET else theme
            next_hue = current["accent_hue"] if accent_hue is _UNSET else accent_hue
            db.execute("UPDATE users SET theme=?,accent_hue=? WHERE id=?", (next_theme, next_hue, user_id))
        return {"theme": next_theme, "accent_hue": next_hue}

    def delete_session(self, token: str) -> None:
        with self.lock, closing(self._connect()) as db, db:
            db.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))

    def ensure_local_user(self) -> dict[str, Any]:
        with self.lock, closing(self._connect()) as db, db:
            row = db.execute("SELECT id,username FROM users WHERE username = ? COLLATE NOCASE", ("local",)).fetchone()
            if row:
                return {"id": row["id"], "username": row["username"]}
            cursor = db.execute("INSERT INTO users(username,password_hash,created_at) VALUES(?,?,?)", ("local", hash_password(secrets.token_urlsafe(24)), utc_now()))
            return {"id": cursor.lastrowid, "username": "local"}

    def create_device_token(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        with self.lock, closing(self._connect()) as db, db:
            db.execute("INSERT INTO device_tokens(token_hash,user_id,created_at) VALUES(?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), user_id, utc_now()))
        return token

    def get_user_by_device(self, token: str) -> dict[str, Any] | None:
        if not token:
            return None
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with self.lock, closing(self._connect()) as db, db:
            row = db.execute("SELECT u.id,u.username FROM device_tokens d JOIN users u ON u.id=d.user_id WHERE d.token_hash=?", (token_hash,)).fetchone()
            if not row:
                return None
            return {"id": row["id"], "username": row["username"]}

    def delete_device_token(self, token: str) -> None:
        if not token:
            return
        with self.lock, closing(self._connect()) as db, db:
            db.execute("DELETE FROM device_tokens WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))

    def save_credential(self, user_id: int, platform: str, values: dict[str, Any]) -> None:
        cookie = str(values.get("cookie") or "")
        cookie_enc = self._fernet.encrypt(cookie.encode()).decode() if cookie else None
        extra = {"phone": values.get("phone")} if values.get("phone") not in (None, "") else {}
        with self.lock, closing(self._connect()) as db, db:
            db.execute(
                """INSERT INTO credentials(user_id,platform,api_url,proxy_url,cookie_enc,uid,extra_json,updated_at,last_validated_at)
                   VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id,platform) DO UPDATE SET api_url=excluded.api_url,proxy_url=excluded.proxy_url,cookie_enc=COALESCE(excluded.cookie_enc,credentials.cookie_enc),uid=excluded.uid,extra_json=excluded.extra_json,updated_at=excluded.updated_at,last_validated_at=excluded.last_validated_at""",
                (user_id, platform, values.get("api_url", ""), values.get("proxy_url", ""), cookie_enc, values.get("uid") or values.get("userid", ""), json.dumps(extra, ensure_ascii=False), utc_now(), utc_now()),
            )

    def get_credential(self, user_id: int, platform: str) -> dict[str, Any] | None:
        with self.lock, closing(self._connect()) as db, db:
            row = db.execute("SELECT * FROM credentials WHERE user_id=? AND platform=?", (user_id, platform)).fetchone()
            if not row:
                return None
            values = dict(row)
            values["cookie"] = self._fernet.decrypt(values["cookie_enc"].encode()).decode() if values.get("cookie_enc") else ""
            values.update(json.loads(values.get("extra_json") or "{}"))
            return values

    def clear_credential(self, user_id: int, platform: str) -> None:
        with self.lock, closing(self._connect()) as db, db:
            db.execute("DELETE FROM credentials WHERE user_id=? AND platform=?", (user_id, platform))

    def mark_credential_invalid(self, user_id: int, platform: str) -> None:
        with self.lock, closing(self._connect()) as db, db:
            db.execute("UPDATE credentials SET last_validated_at=NULL WHERE user_id=? AND platform=?", (user_id, platform))

    def add_history(self, user_id: int, kind: str, title: str, summary: Any = None, tracks: Any = None) -> None:
        with self.lock, closing(self._connect()) as db, db:
            db.execute("INSERT INTO history(user_id,kind,title,summary_json,tracks_json,created_at) VALUES(?,?,?,?,?,?)", (user_id, kind, title, json.dumps(summary, ensure_ascii=False) if summary is not None else None, json.dumps(tracks, ensure_ascii=False) if tracks is not None else None, utc_now()))
            db.execute("DELETE FROM history WHERE user_id=? AND id NOT IN (SELECT id FROM history WHERE user_id=? ORDER BY created_at DESC LIMIT 500)", (user_id, user_id))

    def list_history(self, user_id: int, kind: str = "", page: int = 1, page_size: int = 30) -> dict[str, Any]:
        page = max(1, page); page_size = max(1, min(page_size, 100)); offset = (page - 1) * page_size
        where = "WHERE user_id=?"; args: list[Any] = [user_id]
        if kind:
            where += " AND kind=?"; args.append(kind)
        with self.lock, closing(self._connect()) as db, db:
            total = db.execute(f"SELECT COUNT(*) FROM history {where}", args).fetchone()[0]
            rows = db.execute(f"SELECT * FROM history {where} ORDER BY created_at DESC LIMIT ? OFFSET ?", args + [page_size, offset]).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["summary"] = json.loads(item.pop("summary_json") or "null")
            item["tracks"] = json.loads(item.pop("tracks_json") or "null")
            items.append(item)
        return {"items": items, "page": page, "page_size": page_size, "total": total}

    def add_export_log(self, user_id: int, target: str, platform: str, result: dict[str, Any], config: dict[str, Any], total: int) -> None:
        with self.lock, closing(self._connect()) as db, db:
            db.execute("INSERT INTO export_log(user_id,target,platform,playlist_id,playlist_name,total,added,skipped,failed,detail_json,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (user_id, target, platform, result.get("playlist_id"), config.get("playlist_name", ""), total, result.get("added", 0), result.get("skipped", 0), len(result.get("failed", []) or []), json.dumps(result, ensure_ascii=False), "completed" if result.get("ok", True) else "failed", utc_now()))

    def list_export_logs(self, user_id: int, page: int = 1, page_size: int = 30) -> dict[str, Any]:
        page = max(1, page); page_size = max(1, min(page_size, 100)); offset = (page - 1) * page_size
        with self.lock, closing(self._connect()) as db, db:
            total = db.execute("SELECT COUNT(*) FROM export_log WHERE user_id=?", (user_id,)).fetchone()[0]
            rows = [dict(row) for row in db.execute("SELECT * FROM export_log WHERE user_id=? ORDER BY created_at DESC LIMIT ? OFFSET ?", (user_id, page_size, offset)).fetchall()]
        for row in rows:
            row["detail"] = json.loads(row.pop("detail_json") or "null")
        return {"items": rows, "page": page, "page_size": page_size, "total": total}
