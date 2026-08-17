from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping


KANA_RE = re.compile(r"[\u3040-\u30ff]")
CJK_RE = re.compile(r"[\u3400-\u9fff]")
BRACKET_LABEL_RE = re.compile(r"[\[\]［］【】〔〕]")
BLOCKED_DISPLAY_NAMES = {
    "从缺",
    "無藝術家",
    "无艺术家",
    "未知艺术家",
    "未知藝人",
    "未知艺人",
    "匿名",
    "佚名",
}


def normalize_artist_key(value: str) -> str:
    """Normalize artist lookup keys without changing displayed spelling."""
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def load_curated_aliases(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    items = json.loads(path.read_text(encoding="utf-8"))
    aliases: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        english = str(item.get("english") or "").strip()
        chinese = str(item.get("chinese") or "").strip()
        if english and chinese:
            aliases[english] = chinese
    return aliases


def _language_rank(language: str) -> int:
    normalized = str(language or "").strip().casefold().replace("-", "_")
    if normalized in {"zh_hans", "zh_cn", "zh_sg"} or normalized.startswith(
        "zh_hans_"
    ):
        return 0
    if normalized == "zh":
        return 1
    if normalized.startswith("zh_"):
        return 2
    if not normalized:
        return 3
    return 4


def _parse_zh_aliases(value: Any) -> list[tuple[str, str, bool]]:
    try:
        items = json.loads(value or "[]") if isinstance(value, str) else value or []
    except (TypeError, ValueError):
        return []
    aliases: list[tuple[str, str, bool]] = []
    for item in items:
        if isinstance(item, dict):
            name = str(item.get("name") or item.get("alias") or "").strip()
            language = str(item.get("locale") or item.get("language") or "").strip()
            primary = bool(item.get("primary"))
        elif isinstance(item, (list, tuple)) and item:
            name = str(item[0] or "").strip()
            language = str(item[1] or "").strip() if len(item) > 1 else ""
            primary = bool(item[2]) if len(item) > 2 else False
        else:
            continue
        if name:
            aliases.append((name, language, primary))
    return aliases


def _valid_display_name(value: str, artist_name: str) -> bool:
    normalized = normalize_artist_key(value)
    if not normalized or normalized == normalize_artist_key(artist_name):
        return False
    if len(value) > 80 or KANA_RE.search(value) or BRACKET_LABEL_RE.search(value):
        return False
    if not CJK_RE.search(value):
        return False
    return value not in BLOCKED_DISPLAY_NAMES


def _pick_candidate(
    candidates: Iterable[tuple[str, str, bool]],
    artist_name: str,
    to_simplified: Callable[[str], str] | None,
) -> str | None:
    unique: dict[str, tuple[str, str, bool, int]] = {}
    for index, (name, language, primary) in enumerate(candidates):
        unique.setdefault(normalize_artist_key(name), (name, language, primary, index))

    ranked = sorted(
        unique.values(),
        key=lambda item: (_language_rank(item[1]), not item[2], item[3]),
    )
    for name, _language, _primary, _index in ranked:
        try:
            simplified = to_simplified(name) if to_simplified else name
        except Exception:
            simplified = name
        simplified = str(simplified or "").strip()
        if _valid_display_name(simplified, artist_name):
            return simplified
    return None


def choose_musicbrainz_chinese_name(
    artist_name: str,
    cn_artist_name: Any,
    zh_aliases: Any,
    to_simplified: Callable[[str], str] | None = None,
) -> str | None:
    aliases = _parse_zh_aliases(zh_aliases)

    cn_name = str(cn_artist_name or "").strip()
    if cn_name:
        matched_language = next((language for name, language, _primary in aliases if name == cn_name), "")
        aliases = [(cn_name, matched_language, True), *aliases]

    primary_aliases = [item for item in aliases if item[2]]
    selected = _pick_candidate(primary_aliases or aliases, artist_name, to_simplified)
    if selected is not None:
        return selected
    # Fall back to non-primary aliases only when the rejected primary name is
    # not simply the source artist name itself (e.g. an English-only artist
    # whose only "Chinese" primary alias equals the original name).
    if primary_aliases and not all(
        normalize_artist_key(name) == normalize_artist_key(artist_name)
        for name, _language, _primary in primary_aliases
    ):
        return _pick_candidate(aliases, artist_name, to_simplified)
    return None


def load_musicbrainz_aliases(
    path: Path,
    to_simplified: Callable[[str], str] | None = None,
) -> dict[str, str]:
    if not path.is_file():
        return {}
    # sqlite3 on Windows rejects the RFC-style ``file:///F:/...`` URI in some
    # environments. SQLite's native ``file:F:/...`` form also works on POSIX.
    uri = f"file:{path.resolve().as_posix()}?mode=ro&immutable=1"
    aliases: dict[str, str] = {}
    with closing(sqlite3.connect(uri, uri=True)) as db:
        with closing(db.execute("SELECT artist_name,cn_artist_name,zh_aliases FROM lookup")) as rows:
            for artist_name, cn_artist_name, zh_aliases in rows:
                english = str(artist_name or "").strip()
                if not english:
                    continue
                chinese = choose_musicbrainz_chinese_name(
                    english,
                    cn_artist_name,
                    zh_aliases,
                    to_simplified,
                )
                if chinese:
                    aliases[english] = chinese
    return aliases


def merge_artist_alias_sources(
    preferred_sources: Iterable[Mapping[str, str]],
    fallback_sources: Iterable[Mapping[str, str]] = (),
) -> dict[str, str]:
    merged: dict[str, tuple[str, str]] = {}
    for source in preferred_sources:
        for english, chinese in source.items():
            key = normalize_artist_key(english)
            chinese_name = str(chinese or "").strip()
            if key and chinese_name:
                merged[key] = (str(english).strip(), chinese_name)
    for source in fallback_sources:
        for english, chinese in source.items():
            key = normalize_artist_key(english)
            chinese_name = str(chinese or "").strip()
            if key and chinese_name:
                merged.setdefault(key, (str(english).strip(), chinese_name))
    return {english: chinese for english, chinese in merged.values()}


def build_artist_alias_maps(aliases: Mapping[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    english_to_chinese: dict[str, str] = {}
    chinese_to_english: dict[str, str] = {}
    for english, chinese in aliases.items():
        english_key = normalize_artist_key(english)
        chinese_key = normalize_artist_key(chinese)
        if english_key and chinese:
            english_to_chinese[english_key] = chinese
        if chinese_key and english and normalize_artist_key(english) != chinese_key:
            chinese_to_english.setdefault(chinese_key, english)
    return english_to_chinese, chinese_to_english
