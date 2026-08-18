"""EmbeatService assembly.

This module aggregates the finer business modules under ``backend/embeat``
into the ``EmbeatService`` class used by the FastAPI layer. It intentionally
keeps no business logic of its own beyond construction and composition.

Modules:
- ``aliases``        artist alias loading + shared singletons
- ``qdrant``         Qdrant client/reconnect/retry mixin
- ``text_utils``     text variant/similarity/track-packing helpers
- ``search``         track and artist search mixin
- ``recommendations`` recommend/discover/genre/weekly/playlist-seed mixin
- ``platforms``      platform credential/captcha/login mixin
- ``netease_client`` NetEase API client
"""

from __future__ import annotations

from pathlib import Path

from config import CONFIG
from aliases import (
    APP_DIR,
    ARTIST_EN_ALIASES,
    ARTIST_ZH_ALIASES,
    METADATA_RESOLVER,
    load_artist_aliases,
)
from app_database import AppDatabase
from export_manager import ExportManager
from kugou_client import KugouClient
from netease_client import NetEaseClient
from platforms import PlatformsMixin
from qdrant import QdrantMixin
from recommendations import RecommendationsMixin
from search import SearchMixin
from text_utils import TextMixin

STATIC_DIR = APP_DIR / "static"


class EmbeatService(QdrantMixin, TextMixin, PlatformsMixin, SearchMixin, RecommendationsMixin):
    def __init__(self) -> None:
        self.app_db = AppDatabase(APP_DIR)
        self._init_qdrant()
        self.netease = NetEaseClient(metadata_resolver=METADATA_RESOLVER)
        self.kugou = KugouClient(
            APP_DIR / "data" / ".disabled_credentials.json",
            alias_map={**ARTIST_ZH_ALIASES, **ARTIST_EN_ALIASES},
            to_simplified=self._to_simplified,
            proxy_url=CONFIG.proxy_url,
            metadata_resolver=METADATA_RESOLVER,
            persist_credentials=False,
        )
        self.export_manager = ExportManager(self.netease, self.kugou)


__all__ = [
    "APP_DIR",
    "ARTIST_EN_ALIASES",
    "ARTIST_ZH_ALIASES",
    "EmbeatService",
    "METADATA_RESOLVER",
    "NetEaseClient",
    "STATIC_DIR",
    "load_artist_aliases",
]