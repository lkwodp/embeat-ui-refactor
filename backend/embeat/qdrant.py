"""Qdrant connectivity mixin: client construction, reconnect and retry wrapper."""

from __future__ import annotations

import sys
import threading
from typing import Any

from config import CONFIG

EMBEAT_ROOT = CONFIG.embeat_root
EMBEAT_INFER_DIR = CONFIG.embeat_infer_dir

if str(EMBEAT_INFER_DIR) not in sys.path:
    sys.path.insert(0, str(EMBEAT_INFER_DIR))

from Embeat import EmbeatDatabase  # noqa: E402


class QdrantMixin:
    """Provides ``self.database`` and the ``_qdrant_call`` retry wrapper.

    The initial client is built from CONFIG (as the original server did in
    ``EmbeatService.__init__``); reconnects build a bare ``EmbeatDatabase`` to
    match the original ``_new_database`` behaviour.
    """

    def _build_database(self) -> EmbeatDatabase:
        database = EmbeatDatabase(
            qdrant_url=CONFIG.qdrant_url,
            qdrant_api_key=CONFIG.qdrant_api_key,
            collection_name=CONFIG.qdrant_collection,
            qdrant_timeout=CONFIG.qdrant_timeout,
            verbose_log=False,
        )
        database.verbose_log = False
        return database

    def _new_database(self) -> EmbeatDatabase:
        database = EmbeatDatabase(verbose_log=False)
        database.verbose_log = False
        return database

    def _init_qdrant(self) -> None:
        self.lock = threading.Lock()
        self.database = self._build_database()

    def reconnect_qdrant(self) -> None:
        with self.lock:
            self.database = self._new_database()

    def _qdrant_call(self, operation: Any) -> Any:
        """Run one Qdrant operation, rebuilding stale clients and retrying once."""
        try:
            return operation(self.database)
        except Exception as first_error:
            if not self._is_qdrant_connection_error(first_error):
                raise
            print(f"Qdrant call failed, reconnecting: {first_error}", flush=True)
            try:
                self.reconnect_qdrant()
                return operation(self.database)
            except Exception:
                raise first_error

    @staticmethod
    def _is_qdrant_connection_error(error: BaseException) -> bool:
        """Recognize transport failures without retrying normal lookup errors."""
        current: BaseException | None = error
        seen: set[int] = set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            if isinstance(current, (ConnectionError, TimeoutError, OSError)):
                return True
            module = type(current).__module__.casefold()
            name = type(current).__name__.casefold()
            if any(part in module for part in ("qdrant_client", "httpx", "httpcore")) and any(
                part in name for part in ("connection", "connect", "timeout", "transport", "responsehandling")
            ):
                return True
            current = current.__cause__ or current.__context__
        return False

    def health(self) -> dict[str, Any]:
        info = self._qdrant_call(lambda database: database.client.get_collection(database.collection_name))
        return {
            "status": str(info.status),
            "collection": self.database.collection_name,
            "points": int(info.points_count or 0),
            "qdrant_url": self.database.qdrant_url,
        }