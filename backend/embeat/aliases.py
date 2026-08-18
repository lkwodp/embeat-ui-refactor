"""Artist alias loading and shared module-level singletons."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from artist_aliases import (
    build_artist_alias_maps,
    load_curated_aliases,
    load_musicbrainz_aliases,
    merge_artist_alias_sources,
)
from config import CONFIG
from music_metadata import MusicMetadataResolver

APP_DIR = Path(__file__).resolve().parent


def load_artist_aliases() -> tuple[dict[str, str], dict[str, str]]:
    """Merge curated aliases with the optional MusicBrainz lookup database."""
    built_in_aliases = {
        "Joyce Cheng": "郑欣宜",
        "Gin Lee": "李幸倪",
        "Mag Lam": "林欣彤",
        "Hins Cheung": "张敬轩",
        "Alfred Hui": "许廷铿",
        "Jason Chan": "陈柏宇",
        "Alan Po": "布志纶",
        "Candy Lo": "卢巧音",
        "Cloud 云浩影": "云浩影",
        "JW": "王灏儿",
        "BOYZ": "关智斌",
        "ToNick": "ToNick",
        "Beyond": "Beyond",
        "Frances Yip": "叶丽仪",
        "Hebe Tien": "田馥甄",
        "HANA": "HANA菊梓乔",
    }
    alias_path = APP_DIR / "data" / "chinese_singers_extended.json"
    curated_aliases: dict[str, str] = {}
    try:
        curated_aliases = load_curated_aliases(alias_path)
    except (OSError, ValueError, TypeError) as exc:
        print(f"Failed to load artist aliases from {alias_path}: {exc}", flush=True)

    try:
        from zhconv import convert as zh_convert
    except ImportError:
        zh_convert = None

    mb_path_value = CONFIG.mb_lookup_path
    mb_path = Path(mb_path_value).expanduser() if mb_path_value else APP_DIR / "data" / "mb_lookup.db"
    mb_aliases: dict[str, str] = {}
    try:
        mb_aliases = load_musicbrainz_aliases(
            mb_path,
            lambda value: zh_convert(value, locale="zh-cn") if zh_convert else value,
        )
    except (OSError, ValueError, TypeError, sqlite3.Error) as exc:
        print(f"Failed to load MusicBrainz artist aliases from {mb_path}: {exc}", flush=True)

    curated = merge_artist_alias_sources((built_in_aliases, curated_aliases))
    merged = merge_artist_alias_sources((built_in_aliases, curated_aliases), (mb_aliases,))
    if mb_path.is_file():
        print(
            f"Loaded artist aliases: {len(curated)} curated, "
            f"{len(merged) - len(curated)} added from MusicBrainz, {len(merged)} total.",
            flush=True,
        )
    return build_artist_alias_maps(merged)


ARTIST_ZH_ALIASES, ARTIST_EN_ALIASES = load_artist_aliases()
METADATA_RESOLVER = MusicMetadataResolver(APP_DIR / "data" / "music_metadata_cache.json")