"""Pure text helpers shared across Embeat modules.

These are kept module-level so search, recommendations and platform clients
can reuse the same simplified-Chinese conversion, name variants, similarity
scoring and track packing without coupling through the service class.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from artist_aliases import normalize_artist_key
from aliases import ARTIST_ZH_ALIASES

try:
    from zhconv import convert as zh_convert
except ImportError:
    zh_convert = None


def to_simplified(value: str) -> str:
    return zh_convert(value, locale="zh-cn") if zh_convert else value


def text_variants(value: str) -> list[str]:
    """Return the trimmed input plus simplified and traditional variants."""
    variants = [value.strip()]
    if zh_convert and value.strip():
        for locale in ("zh-hk", "zh-cn"):
            converted = zh_convert(value.strip(), locale=locale)
            if converted not in variants:
                variants.append(converted)
    return [item for item in variants if item]


def similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left.casefold(), right.casefold()).ratio()


def artist_variants(value: str) -> list[str]:
    """Return text variants plus any mapped Chinese/English artist aliases."""
    variants = text_variants(value)
    lookup_key = normalize_artist_key(value)
    from aliases import ARTIST_EN_ALIASES

    mapped_zh = ARTIST_ZH_ALIASES.get(lookup_key)
    mapped_en = ARTIST_EN_ALIASES.get(lookup_key)
    for item in (mapped_zh, mapped_en):
        if item and item not in variants:
            variants.append(item)
    return variants


def pack_track(payload: dict[str, Any], match_score: float | None = None) -> dict[str, Any]:
    """Flatten a Qdrant payload into the track shape returned by the API."""
    sources = payload.get("sources") or []
    if not isinstance(sources, list):
        sources = [str(sources)]
    track_name = str(payload.get("track_name") or "未知歌曲")
    artist_name = str(payload.get("artist_name") or "未知艺人")
    artist_name_zh = ARTIST_ZH_ALIASES.get(
        normalize_artist_key(artist_name),
        to_simplified(artist_name),
    )
    packed = {
        "track_id": str(payload.get("track_id") or ""),
        "track_name": track_name,
        "artist_name": artist_name,
        "track_name_zh": to_simplified(track_name),
        "artist_name_zh": artist_name_zh,
        "album_name": str(payload.get("album_name") or "未知专辑"),
        "artist_genres": str(payload.get("artist_genres") or ""),
        "popularity": round(float(payload.get("popularity") or 0.0), 4),
        "score": round(float(payload.get("score") or 0.0), 4),
        "sources": sources,
    }
    if match_score is not None:
        packed["match_score"] = round(match_score, 4)
    return packed


class TextMixin:
    """Expose the text helpers as ``EmbeatService`` instance methods.

    This keeps the original ``self._variants``/``self._similarity``/
    ``self._pack_track``/``self._artist_variants`` calling convention intact
    for both the internal mixins and any external code that referenced them.
    """

    @staticmethod
    def _variants(value: str) -> list[str]:
        return text_variants(value)

    @staticmethod
    def _similarity(left: str, right: str) -> float:
        return similarity(left, right)

    @staticmethod
    def _artist_variants(value: str) -> list[str]:
        return artist_variants(value)

    @staticmethod
    def _pack_track(payload: dict[str, Any], match_score: float | None = None) -> dict[str, Any]:
        return pack_track(payload, match_score=match_score)

    @staticmethod
    def _to_simplified(value: str) -> str:
        return to_simplified(value)