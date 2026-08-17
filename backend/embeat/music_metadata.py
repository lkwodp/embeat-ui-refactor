from __future__ import annotations

import json
import concurrent.futures
import threading
import time
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
import re
from pathlib import Path
from typing import Any, Iterable

from music_matching import best_artist_similarity, best_title_similarity, normalize_match_text, version_tags


class MusicMetadataResolver:
    """Resolve localized titles through Apple's public multi-store catalogue.

    Apple uses the same track ID for localized store metadata. A search in the
    source language can therefore discover the ID, and lookups in other stores
    provide equivalent titles and artist spellings without maintaining a
    per-track translation table.
    """

    COUNTRIES = ("US", "KR", "JP", "CN", "HK", "TW")
    SEARCH_COUNTRIES = ("US", "KR")

    def __init__(self, cache_file: Path, ttl_days: int = 120) -> None:
        self.cache_file = cache_file
        self.ttl_seconds = ttl_days * 86400
        self.lock = threading.Lock()
        self.cache: dict[str, dict[str, Any]] = self._load()

    def resolve(self, titles: Iterable[str], artists: Iterable[str]) -> tuple[list[str], list[str]]:
        input_titles = self._unique(titles)
        input_artists = self._unique(artists)
        if not input_titles or not input_artists:
            return [], []
        key = self._key(input_titles, input_artists)
        cached = self.cache.get(key)
        if cached and time.time() - float(cached.get("updated_at") or 0) < self.ttl_seconds:
            return self._unique(cached.get("titles") or []), self._unique(cached.get("artists") or [])

        seed = self._find_seed(input_titles, input_artists)
        if not seed:
            with self.lock:
                self.cache[key] = {"updated_at": time.time(), "titles": [], "artists": [], "miss": True}
                self._save()
            return [], []
        track_id = str(seed.get("trackId") or "")
        titles_out = list(input_titles)
        artists_out = list(input_artists)
        for result in self._lookup_many(track_id, countries=("US", "KR", "HK")):
            if not result:
                continue
            title = str(result.get("trackName") or "").strip()
            artist = str(result.get("artistName") or "").strip()
            if title and not version_tags(title):
                titles_out.append(title)
            if artist:
                artists_out.append(artist)
        titles_out = self._unique(titles_out)
        artists_out = self._unique(artists_out)
        with self.lock:
            self.cache[key] = {"updated_at": time.time(), "track_id": track_id, "titles": titles_out, "artists": artists_out}
            self._save()
        return titles_out, artists_out

    def verify_candidate(
        self,
        input_titles: Iterable[str],
        input_artists: Iterable[str],
        candidate_titles: Iterable[str],
        candidate_artists: Iterable[str],
    ) -> bool:
        """Confirm a cross-language platform candidate using stable track IDs."""
        input_title_values = self._unique(input_titles)
        input_artist_values = self._unique(input_artists)
        candidate_title_values = self._unique(candidate_titles)
        candidate_artist_values = self._unique(candidate_artists)
        if self._find_cross_catalog(input_title_values, input_artist_values, candidate_title_values, candidate_artist_values):
            return True
        candidate_catalog = self._catalog_for_title(candidate_title_values, candidate_artist_values)
        if not candidate_catalog:
            return False
        catalog_titles = candidate_catalog.get("titles") or []
        catalog_artists = candidate_catalog.get("artists") or []
        title_score = best_title_similarity(input_title_values, catalog_titles)
        artist_score = self._loose_artist_similarity(input_artist_values, catalog_artists)
        candidate_artist_score = self._loose_artist_similarity(candidate_artist_values, catalog_artists)
        candidate_has_latin = any(re.search(r"[a-z]", value.casefold()) for value in candidate_artist_values)
        # The catalogue itself supplies the cross-language proof. Romanized
        # names can differ in word order (Ha Yea Song / Song Haye).
        return (
            title_score >= 0.94
            and artist_score >= 0.80
            and (not candidate_has_latin or candidate_artist_score >= 0.80)
        )

    def _find_cross_catalog(
        self,
        input_titles: list[str],
        input_artists: list[str],
        candidate_titles: list[str],
        candidate_artists: list[str],
    ) -> bool:
        if not input_titles or not candidate_titles:
            return False
        ids: dict[str, tuple[float, dict[str, Any]]] = {}
        for title in candidate_titles[:3]:
            for item in self._search_many(title):
                track_id = str(item.get("trackId") or "")
                candidate_title_score = best_title_similarity(candidate_titles, [str(item.get("trackName") or "")])
                if not track_id or candidate_title_score < 0.90:
                    continue
                candidate_artist_score = self._loose_artist_similarity(candidate_artists, [str(item.get("artistName") or "")])
                input_artist_score = self._loose_artist_similarity(input_artists, [str(item.get("artistName") or "")])
                quality = -0.20 if self._is_non_studio(item) else 0.08
                artist_evidence = max(candidate_artist_score, input_artist_score)
                ids[track_id] = (candidate_title_score * 0.82 + artist_evidence * 0.18 + quality, item)
            if len(ids) >= 30:
                break
        ranked_ids = sorted(ids.items(), key=lambda row: row[1][0], reverse=True)[:6]
        for track_id, (_candidate_score, _candidate_item) in ranked_ids:
            localized_titles: list[str] = []
            localized_artists: list[str] = []
            for item in self._lookup_many(track_id, countries=("US", "KR", "HK")):
                if not item:
                    continue
                localized_titles.append(str(item.get("trackName") or ""))
                localized_artists.append(str(item.get("artistName") or ""))
                candidate_artist_score = self._loose_artist_similarity(candidate_artists, localized_artists)
                candidate_has_latin = any(re.search(r"[a-z]", value.casefold()) for value in candidate_artists)
                if (
                    best_title_similarity(input_titles, localized_titles) >= 0.94
                    and self._loose_artist_similarity(input_artists, localized_artists) >= 0.80
                    and (not candidate_has_latin or candidate_artist_score >= 0.80)
                    and not self._is_non_studio(item)
                ):
                    return True
        return False

    def _catalog_for_title(self, titles: list[str], artists: list[str]) -> dict[str, Any] | None:
        if not titles:
            return None
        key = "title|" + normalize_match_text(titles[0]) + "|" + normalize_match_text(artists[0] if artists else "")
        cached = self.cache.get(key)
        if cached and time.time() - float(cached.get("updated_at") or 0) < self.ttl_seconds:
            return cached
        ranked: list[tuple[float, dict[str, Any]]] = []
        for title in titles[:3]:
            for item in self._search_many(title):
                track_id = str(item.get("trackId") or "")
                if not track_id:
                    continue
                item_title = str(item.get("trackName") or "")
                item_artist = str(item.get("artistName") or "")
                title_score = best_title_similarity(titles, [item_title])
                artist_score = best_artist_similarity(artists, [item_artist]) if artists else 0.0
                quality = -0.24 if self._is_non_studio(item) else 0.12
                ranked.append((title_score * 0.82 + artist_score * 0.18 + quality, item))
        ranked.sort(key=lambda row: row[0], reverse=True)
        if not ranked or best_title_similarity(titles, [str(ranked[0][1].get("trackName") or "")]) < 0.94:
            return None
        track_id = str(ranked[0][1].get("trackId") or "")
        resolved_titles: list[str] = []
        resolved_artists: list[str] = []
        for item in self._lookup_many(track_id, countries=("US", "KR", "HK")):
            if not item:
                continue
            resolved_titles.append(str(item.get("trackName") or ""))
            resolved_artists.append(str(item.get("artistName") or ""))
        result = {
            "updated_at": time.time(),
            "track_id": track_id,
            "titles": self._unique(resolved_titles),
            "artists": self._unique(resolved_artists),
        }
        with self.lock:
            self.cache[key] = result
            self._save()
        return result

    @staticmethod
    def _is_non_studio(item: dict[str, Any]) -> bool:
        text = " ".join(str(item.get(key) or "") for key in ("trackName", "collectionName")).casefold()
        return bool(re.search(r"\b(?:inst|instrumental|karaoke|cover|piano|mr|remix|live)\b|伴奏|钢琴|翻唱", text))

    def _find_seed(self, titles: list[str], artists: list[str]) -> dict[str, Any] | None:
        queries = self._unique([f"{titles[0]} {artists[0]}", titles[0]])[:2]
        requested_versions = version_tags(*titles)
        ranked: list[tuple[float, dict[str, Any]]] = []
        seen: set[str] = set()
        for query in queries:
            for item in self._search_many(query):
                track_id = str(item.get("trackId") or "")
                if not track_id or track_id in seen:
                    continue
                seen.add(track_id)
                title = str(item.get("trackName") or "")
                artist = str(item.get("artistName") or "")
                title_score = best_title_similarity(titles, [title])
                artist_score = self._loose_artist_similarity(artists, [artist])
                candidate_versions = version_tags(title)
                if requested_versions:
                    version_ok = bool(requested_versions & candidate_versions)
                else:
                    version_ok = not candidate_versions
                score = title_score * 0.72 + artist_score * 0.28 + (0.02 if version_ok else -0.08)
                ranked.append((score, item))
            if ranked and max(score for score, _item in ranked) >= 0.97:
                break
        ranked.sort(key=lambda row: row[0], reverse=True)
        if not ranked:
            return None
        score, item = ranked[0]
        title_score = best_title_similarity(titles, [str(item.get("trackName") or "")])
        artist_score = self._loose_artist_similarity(artists, [str(item.get("artistName") or "")])
        return item if score >= 0.82 and title_score >= 0.72 and artist_score >= 0.80 else None

    @staticmethod
    def _request(url: str) -> dict[str, Any]:
        request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "EmbeatUI/1.0"})
        with urllib.request.urlopen(request, timeout=4) as response:
            return json.loads(response.read().decode("utf-8"))

    def _search(self, query: str, country: str) -> list[dict[str, Any]]:
        try:
            params = urllib.parse.urlencode({"term": query, "entity": "song", "limit": 12, "country": country})
            return list(self._request(f"https://itunes.apple.com/search?{params}").get("results") or [])
        except Exception:
            return []

    def _search_many(self, query: str) -> list[dict[str, Any]]:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(self.SEARCH_COUNTRIES)) as pool:
            batches = pool.map(lambda country: self._search(query, country), self.SEARCH_COUNTRIES)
            return [item for batch in batches for item in batch]

    def _lookup(self, track_id: str, country: str) -> dict[str, Any] | None:
        try:
            params = urllib.parse.urlencode({"id": track_id, "country": country})
            results = self._request(f"https://itunes.apple.com/lookup?{params}").get("results") or []
            return results[0] if results else None
        except Exception:
            return None

    def _lookup_many(self, track_id: str, countries: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
        selected = countries or self.COUNTRIES
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(selected)) as pool:
            results = pool.map(lambda country: self._lookup(track_id, country), selected)
            return [item for item in results if item]

    @staticmethod
    def _unique(values: Iterable[str]) -> list[str]:
        output: list[str] = []
        seen: set[str] = set()
        for value in values:
            item = str(value or "").strip()
            key = normalize_match_text(item)
            if item and key not in seen:
                seen.add(key)
                output.append(item)
        return output

    @staticmethod
    def _key(titles: list[str], artists: list[str]) -> str:
        return "|".join((normalize_match_text(titles[0]), normalize_match_text(artists[0])))

    @staticmethod
    def _loose_artist_similarity(left: Iterable[str], right: Iterable[str]) -> float:
        best = best_artist_similarity(left, right)
        for left_value in left:
            left_norm = normalize_match_text(left_value)
            for right_value in right:
                right_norm = normalize_match_text(right_value)
                if not left_norm or not right_norm:
                    continue
                # Romanized names vary in token order and segmentation. A
                # character-multiset comparison handles Song Haye / Ha Yea Song
                # while the exact-title catalogue check prevents broad matches.
                best = max(best, SequenceMatcher(None, "".join(sorted(left_norm)), "".join(sorted(right_norm))).ratio())
        return best

    def _load(self) -> dict[str, dict[str, Any]]:
        try:
            value = json.loads(self.cache_file.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def _save(self) -> None:
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.cache_file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.cache, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.cache_file)
