"""Track and artist search against the Qdrant collection."""

from __future__ import annotations

from typing import Any

from artist_aliases import normalize_artist_key
from text_utils import pack_track, similarity

from Embeat import qdrant_models  # noqa: E402


class SearchMixin:
    def search(self, track_name: str, artist_name: str = "", limit: int = 20) -> list[dict[str, Any]]:
        track_name = track_name.strip()
        artist_name = artist_name.strip()
        if not track_name:
            return []

        candidates: dict[str, dict[str, Any]] = {}
        query_variants = self._variants(track_name)
        artist_variants = self._artist_variants(artist_name) if artist_name else []
        normalized_artist_variants = {
            normalize_artist_key(item) for item in artist_variants
        }

        def perform(database) -> None:
            for query in query_variants:
                records, _ = database.client.scroll(
                    collection_name=database.collection_name,
                    scroll_filter=qdrant_models.Filter(
                        must=[
                            qdrant_models.FieldCondition(
                                key="track_name",
                                match=qdrant_models.MatchText(text=query),
                            )
                        ]
                    ),
                    limit=max(30, limit * 3),
                    with_payload=True,
                    with_vectors=False,
                )
                for record in records:
                    payload = record.payload or {}
                    track_id = str(payload.get("track_id") or "")
                    if track_id:
                        candidates[track_id] = payload
        self._qdrant_call(perform)

        ranked = []
        for payload in candidates.values():
            candidate_track = str(payload.get("track_name") or "")
            candidate_artist = str(payload.get("artist_name") or "")
            track_score = max(self._similarity(query, candidate_track) for query in query_variants)
            artist_score = 0.0
            artist_exact = False
            if artist_variants:
                artist_exact = normalize_artist_key(candidate_artist) in normalized_artist_variants
                artist_score = max(
                    self._similarity(query, candidate_artist)
                    for query in artist_variants
                )
                if not artist_exact and artist_score < 0.72:
                    continue
            popularity = float(payload.get("popularity") or 0.0)
            rank_score = track_score * 0.72 + artist_score * 0.23 + popularity * 0.05
            packed = pack_track(payload, match_score=rank_score)
            packed["_artist_exact"] = artist_exact
            ranked.append(packed)

        if artist_variants and any(item["_artist_exact"] for item in ranked):
            ranked = [item for item in ranked if item["_artist_exact"]]
        for item in ranked:
            item.pop("_artist_exact", None)

        ranked.sort(key=lambda item: (item["match_score"], item["popularity"]), reverse=True)
        return ranked[:limit]

    def _resolve_artist(self, database, artist_name: str) -> dict[str, Any]:
        variants = self._artist_variants(artist_name)
        normalized_variants = {normalize_artist_key(item) for item in variants}
        candidates: dict[int, dict[str, Any]] = {}
        for query in variants:
            records, _ = database.client.scroll(
                collection_name=database.collection_name,
                scroll_filter=qdrant_models.Filter(
                    must=[
                        qdrant_models.FieldCondition(
                            key="artist_name",
                            match=qdrant_models.MatchText(text=query),
                        )
                    ]
                ),
                limit=100,
                with_payload=True,
                with_vectors=False,
            )
            for record in records:
                payload = record.payload or {}
                artist_idx = int(payload.get("artist_idx") or 0)
                resolved_name = str(payload.get("artist_name") or "").strip()
                if artist_idx <= 0 or not resolved_name:
                    continue
                score = max(self._similarity(item, resolved_name) for item in variants)
                exact = normalize_artist_key(resolved_name) in normalized_variants
                popularity = float(payload.get("popularity") or 0.0)
                current = candidates.get(artist_idx)
                if current is None or (exact, score, popularity) > (
                    current["exact"],
                    current["score"],
                    current["popularity"],
                ):
                    candidates[artist_idx] = {
                        "artist_idx": artist_idx,
                        "artist_name": resolved_name,
                        "exact": exact,
                        "score": score,
                        "popularity": popularity,
                    }

        ranked = sorted(
            candidates.values(),
            key=lambda item: (item["exact"], item["score"], item["popularity"]),
            reverse=True,
        )
        if not ranked or (not ranked[0]["exact"] and ranked[0]["score"] < 0.62):
            raise LookupError("数据库中未找到该歌手")
        if (
            len(ranked) > 1
            and not ranked[0]["exact"]
            and ranked[0]["score"] - ranked[1]["score"] < 0.04
        ):
            names = "、".join(item["artist_name"] for item in ranked[:3])
            raise LookupError(f"歌手名称存在歧义，请输入更完整的名称：{names}")
        return ranked[0]