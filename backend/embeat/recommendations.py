"""Recommendation and discovery mixin (single, multi-seed, artist, genre, weekly)."""

from __future__ import annotations

import hashlib
import time
from typing import Any

from artist_aliases import normalize_artist_key
from aliases import ARTIST_ZH_ALIASES
from text_utils import to_simplified

from Embeat import qdrant_models  # noqa: E402


class RecommendationsMixin:
    def recommend_artist(self, artist_name: str, limit: int = 20) -> dict[str, Any]:
        artist_name = artist_name.strip()
        if not artist_name:
            raise ValueError("歌手名不能为空")

        started = time.perf_counter()

        def perform(database):
            resolved = self._resolve_artist(database, artist_name)
            representative = database.find_query_record_by_artist(
                artist_idx=resolved["artist_idx"]
            )
            if representative is None:
                raise LookupError("数据库中没有足够的该歌手歌曲用于生成推荐")
            representative_payload = representative.payload or {}
            representative_id = str(representative_payload.get("track_id") or "")
            if representative_id:
                result = database.search_entry(track_id=representative_id, top_k=limit)
            else:
                result = database.search_entry(
                    artist_idx=resolved["artist_idx"], top_k=limit
                )
            return resolved, representative, result

        resolved, representative, result = self._qdrant_call(perform)
        resolved_name = str(resolved["artist_name"])
        artist_name_zh = ARTIST_ZH_ALIASES.get(
            normalize_artist_key(resolved_name),
            to_simplified(resolved_name),
        )
        representative_track = self._pack_track(representative.payload or {})
        return {
            "mode": "artist",
            "artist": {
                "input_name": artist_name,
                "artist_idx": int(resolved["artist_idx"]),
                "artist_name": resolved_name,
                "artist_name_zh": artist_name_zh,
                "artist_genres": representative_track.get("artist_genres", ""),
            },
            "representative_track": representative_track,
            "tracks": [self._pack_track(item) for item in result],
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
        }

    def recommend(self, track_id: str, limit: int = 20) -> dict[str, Any]:
        track_id = track_id.strip()
        if not track_id:
            raise ValueError("Spotify Track ID 不能为空")

        started = time.perf_counter()

        def perform(database):
            seed_record = database.find_query_record_by_track(track_id=track_id)
            if seed_record is None:
                raise LookupError("数据库中未找到该歌曲")
            result = database.search_entry(track_id=track_id, top_k=limit)
            return seed_record, result

        seed_record, result = self._qdrant_call(perform)

        seed = self._pack_track(seed_record.payload or {})
        tracks = [self._pack_track(item) for item in result]
        return {
            "seed": seed,
            "tracks": tracks,
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
        }

    def recommend_multi(self, track_ids: list[str], limit: int = 50) -> dict[str, Any]:
        seed_ids = list(dict.fromkeys(str(item).strip() for item in track_ids if str(item).strip()))[:30]
        if not seed_ids:
            raise ValueError("请至少提供一首种子歌曲")
        started = time.perf_counter()
        seeds: list[dict[str, Any]] = []
        merged: dict[str, dict[str, Any]] = {}
        candidate_limit = min(50, max(limit, 30))

        def perform(database) -> None:
            for seed_id in seed_ids:
                seed_record = database.find_query_record_by_track(track_id=seed_id)
                if seed_record is None:
                    continue
                seed_payload = seed_record.payload or {}
                seeds.append(self._pack_track(seed_payload))
                recommendations = database.search_entry(track_id=seed_id, top_k=candidate_limit)
                for rank, item in enumerate(recommendations):
                    candidate_id = str(item.get("track_id") or "")
                    if not candidate_id or candidate_id in seed_ids:
                        continue
                    entry = merged.setdefault(candidate_id, {
                        "payload": dict(item), "score_sum": 0.0, "hits": 0,
                        "sources": set(), "best_score": 0.0,
                    })
                    item_score = float(item.get("score") or 0.0)
                    rank_score = 1.0 / (1.0 + rank * 0.12)
                    contribution = item_score * 0.72 + rank_score * 0.28
                    entry["score_sum"] += contribution
                    entry["hits"] += 1
                    entry["best_score"] = max(entry["best_score"], item_score)
                    entry["sources"].update(item.get("sources") or [])
        self._qdrant_call(perform)

        if not seeds:
            raise LookupError("数据库中未找到有效种子歌曲")
        output = []
        seed_count = len(seeds)
        for entry in merged.values():
            coverage = entry["hits"] / seed_count
            fused = (entry["score_sum"] / entry["hits"]) * 0.78 + coverage * 0.17 + entry["best_score"] * 0.05
            payload = entry["payload"]
            payload["score"] = min(1.0, fused)
            payload["sources"] = sorted(entry["sources"])
            payload["seed_hits"] = entry["hits"]
            packed = self._pack_track(payload)
            packed["seed_hits"] = entry["hits"]
            output.append(packed)
        output.sort(key=lambda item: (item["score"], item["seed_hits"], item["popularity"]), reverse=True)
        return {
            "seeds": seeds,
            "tracks": output[:limit],
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
        }

    def discover_genre(self, genre: str, limit: int = 50) -> dict[str, Any]:
        genre = genre.strip().casefold()
        if not genre:
            raise ValueError("流派不能为空")
        genre_idx = int(getattr(self.database, "genre_index_dict", {}).get(genre, 0) or 0)
        if genre_idx <= 0:
            matches = [
                (name, idx) for name, idx in getattr(self.database, "genre_index_dict", {}).items()
                if genre in name.casefold()
            ]
            if matches:
                matches.sort(key=lambda item: (len(item[0]), item[0]))
                genre, genre_idx = matches[0]
        if genre_idx <= 0:
            raise LookupError("未找到该流派")

        def perform(database):
            records, _ = database.client.scroll(
                collection_name=database.collection_name,
                scroll_filter=qdrant_models.Filter(must=[
                    qdrant_models.FieldCondition(key="artist_genre_idx", match=qdrant_models.MatchValue(value=genre_idx)),
                    qdrant_models.FieldCondition(key="popularity", range=qdrant_models.Range(gte=0.15)),
                ]),
                limit=min(200, max(limit * 3, 100)),
                with_payload=True,
                with_vectors=False,
            )
            return records

        records = self._qdrant_call(perform)
        tracks = [self._pack_track(record.payload or {}) for record in records]
        tracks.sort(key=lambda item: item["popularity"], reverse=True)
        return {"genre": genre, "tracks": tracks[:limit]}

    def weekly_discovery(self, limit: int = 50) -> dict[str, Any]:
        week_key = time.strftime("%G-W%V")

        def perform(database):
            records, _ = database.client.scroll(
                collection_name=database.collection_name,
                scroll_filter=qdrant_models.Filter(must=[
                    qdrant_models.FieldCondition(key="popularity", range=qdrant_models.Range(gte=0.18, lte=0.72)),
                    qdrant_models.FieldCondition(key="artist_genre_idx", range=qdrant_models.Range(gte=1)),
                ]),
                limit=min(300, max(limit * 5, 150)),
                with_payload=True,
                with_vectors=False,
            )
            return records

        records = self._qdrant_call(perform)
        tracks = [self._pack_track(record.payload or {}) for record in records]
        tracks.sort(key=lambda item: hashlib.sha256(f"{week_key}:{item['track_id']}".encode()).hexdigest())
        selected, artist_counts, genre_counts = [], {}, {}
        for track in tracks:
            artist = track["artist_name"]
            if not track["artist_genres"].strip():
                continue
            split_genre = track["artist_genres"].split(",")[0].strip()
            if artist_counts.get(artist, 0) >= 2 or genre_counts.get(split_genre, 0) >= 5:
                continue
            selected.append(track)
            artist_counts[artist] = artist_counts.get(artist, 0) + 1
            genre_counts[split_genre] = genre_counts.get(split_genre, 0) + 1
            if len(selected) >= limit:
                break
        return {"week": week_key, "tracks": selected, "note": "按周轮换的发现榜，不代表本周发行"}

    def genres(self, limit: int = 100) -> list[str]:
        genres = {str(name).strip() for name in getattr(self.database, "genre_index_dict", {}) if str(name).strip()}
        preferred = [
            "mandopop", "cantopop", "taiwan pop", "chinese indie", "singaporean mandopop",
            "pop", "rock", "indie pop", "indie rock", "alternative rock", "folk", "r&b",
            "hip hop", "electronic", "dance pop", "j-pop", "k-pop", "j-rock", "jazz",
            "classical", "metal", "punk", "country", "soul", "reggae", "blues", "soundtrack",
        ]
        ordered = [name for name in preferred if name in genres]
        ordered.extend(sorted(genres.difference(ordered)))
        return ordered[:limit]

    def playlist_seeds(self, platform: str, playlist_id: str, max_seeds: int = 30, client: Any = None) -> dict[str, Any]:
        platform = platform.strip().casefold()
        if platform == "netease":
            songs = (client or self.netease).playlist_tracks(playlist_id)
            platform_name = "网易云"
        elif platform == "kugou":
            songs = (client or self.kugou).playlist_seed_tracks(playlist_id)
            platform_name = "酷狗"
        else:
            raise ValueError("歌单平台仅支持 netease 或 kugou")
        if not songs:
            raise LookupError(f"{platform_name}歌单中没有可用歌曲")
        max_seeds = max(1, min(max_seeds, 30))
        if len(songs) <= max_seeds:
            sampled = songs
        elif max_seeds == 1:
            sampled = [songs[0]]
        else:
            indices = sorted({round(index * (len(songs) - 1) / (max_seeds - 1)) for index in range(max_seeds)})
            sampled = [songs[index] for index in indices]
        matched: dict[str, dict[str, Any]] = {}
        unmatched = []
        for song in sampled:
            candidates = self.search(song["name"], song["artist"], limit=5)
            if candidates:
                candidate = candidates[0]
                matched[candidate["track_id"]] = candidate
            else:
                unmatched.append(song)
        return {
            "seeds": list(matched.values()), "playlist_total": len(songs),
            "sampled": len(sampled), "unmatched": unmatched,
            "platform": platform,
        }