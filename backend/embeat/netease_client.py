"""In-memory Netease API client with track matching and playlist export."""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.request
import uuid
from typing import Any
from urllib.parse import urlencode

from aliases import ARTIST_EN_ALIASES, ARTIST_ZH_ALIASES
from artist_aliases import normalize_artist_key
from music_matching import (
    artist_search_aliases,
    best_artist_similarity,
    best_title_similarity,
    combined_match_score,
    confident_match,
    normalize_match_text,
    track_title_aliases,
    title_search_variants,
    version_tags,
)

try:
    from zhconv import convert as zh_convert
except ImportError:
    zh_convert = None


class NetEaseClient:
    """Small in-memory proxy for a compatible Netease API service."""

    def __init__(self, metadata_resolver: Any = None) -> None:
        self.api_url = ""
        self.cookie = ""
        self.uid = ""
        self.proxy_url = ""
        self.metadata_resolver = metadata_resolver
        self.lock = threading.Lock()
        self.jobs: dict[str, dict[str, Any]] = {}
        self.jobs_lock = threading.Lock()

    def configure(self, api_url: str, cookie: str, proxy_url: str = "") -> dict[str, Any]:
        self.api_url = api_url.strip().rstrip("/")
        self.cookie = cookie.strip()
        self.proxy_url = proxy_url.strip()
        if not self.api_url:
            raise ValueError("网易云 API 地址不能为空")
        if not self.cookie:
            raise ValueError("网易云 Cookie 不能为空")
        status = self._post("/login/status", {})
        profile = ((status.get("data") or {}).get("profile") or {})
        uid = profile.get("userId") or ((status.get("account") or {}).get("id"))
        if not uid:
            raise ValueError("Cookie 无效或已过期")
        self.uid = str(uid)
        return {"uid": self.uid, "proxy_url": self.proxy_url}

    def status(self) -> dict[str, Any]:
        return {"configured": bool(self.api_url and self.cookie and self.uid), "uid": self.uid}

    def playlists(self) -> list[dict[str, Any]]:
        self._require()
        result = self._post("/user/playlist", {"uid": self.uid, "limit": 100})
        if result.get("code") != 200:
            raise RuntimeError(result.get("message") or "获取网易云歌单失败")
        return [
            {"id": str(item.get("id")), "name": str(item.get("name") or "未命名歌单"), "trackCount": int(item.get("trackCount") or 0)}
            for item in result.get("playlist", [])
            if str(item.get("userId")) == self.uid
        ]

    def playlist_tracks(self, playlist_id: str) -> list[dict[str, str]]:
        self._require()
        result = self._post("/playlist/track/all", {"id": str(playlist_id), "limit": 1000, "offset": 0})
        if result.get("code") != 200:
            raise RuntimeError(result.get("message") or "读取网易云歌单歌曲失败")
        songs = result.get("songs") or result.get("data") or []
        output = []
        for song in songs:
            artists = song.get("ar") or song.get("artists") or []
            artist_name = " / ".join(str(item.get("name") or "") for item in artists if isinstance(item, dict))
            output.append({"name": str(song.get("name") or ""), "artist": artist_name})
        return [item for item in output if item["name"]]

    def start_export(self, tracks: list[dict[str, Any]], playlist_id: str = "NEW", playlist_name: str = "") -> dict[str, Any]:
        self._require()
        if not tracks:
            raise ValueError("请至少选择一首歌曲")
        job_id = uuid.uuid4().hex
        job = {
            "id": job_id,
            "status": "queued",
            "phase": "准备导入",
            "current": "",
            "processed": 0,
            "total": len(tracks),
            "percent": 0,
            "result": None,
            "error": "",
        }
        with self.jobs_lock:
            self.jobs[job_id] = job
        threading.Thread(
            target=self._run_export_job,
            args=(job_id, tracks, playlist_id, playlist_name),
            name=f"netease-export-{job_id[:8]}",
            daemon=True,
        ).start()
        return {"job_id": job_id}

    def export_status(self, job_id: str) -> dict[str, Any]:
        with self.jobs_lock:
            job = self.jobs.get(job_id)
            if not job:
                raise LookupError("导入任务不存在或已过期")
            return dict(job)

    def _update_job(self, job_id: str, **values: Any) -> None:
        with self.jobs_lock:
            if job_id in self.jobs:
                self.jobs[job_id].update(values)

    def _run_export_job(self, job_id: str, tracks: list[dict[str, Any]], playlist_id: str, playlist_name: str) -> None:
        try:
            with self.lock:
                result = self.export(
                    tracks,
                    playlist_id,
                    playlist_name,
                    progress=lambda **values: self._update_job(job_id, **values),
                )
            self._update_job(job_id, status="completed", phase="导入完成", current="", percent=100, result=result)
        except Exception as exc:
            self._update_job(job_id, status="failed", phase="导入失败", current="", error=str(exc))

    def export(
        self,
        tracks: list[dict[str, Any]],
        playlist_id: str = "NEW",
        playlist_name: str = "",
        progress: Any = None,
    ) -> dict[str, Any]:
        self._require()
        if not tracks:
            raise ValueError("请至少选择一首歌曲")
        if progress:
            progress(status="running", phase="准备目标歌单", percent=2)
        if playlist_id == "NEW":
            if not playlist_name.strip():
                raise ValueError("新歌单名称不能为空")
            created = self._post("/playlist/create", {"name": playlist_name.strip()})
            code = created.get("code") or created.get("status") or ((created.get("body") or {}).get("code"))
            if code != 200:
                raise RuntimeError(created.get("message") or "创建网易云歌单失败")
            playlist_id = str(created.get("id") or (created.get("playlist") or {}).get("id") or "")
            if not playlist_id:
                raise RuntimeError("网易云 API 未返回新歌单 ID")

        existing = self._post("/playlist/track/all", {"id": playlist_id})
        existing_songs = existing.get("songs") or existing.get("data") or []
        playlist_existing_ids = {str(song.get("id")) for song in existing_songs if song.get("id") is not None}
        batch_matched_ids: set[str] = set()
        matched, matched_details, failed, skipped_existing = [], [], [], []
        total = len(tracks)
        for index, track in enumerate(tracks, start=1):
            name = str(track.get("track_name") or "")
            artist = str(track.get("artist_name") or "")
            display_name = str(track.get("track_name_zh") or name)
            display_artist = str(track.get("artist_name_zh") or artist)
            if progress:
                progress(
                    status="running",
                    phase="匹配网易云曲库",
                    current=f"{display_name} - {display_artist}",
                    processed=index - 1,
                    percent=8 + int((index - 1) / max(total, 1) * 78),
                )
            if not name:
                failed.append({"track_name": name, "artist_name": artist, "reason": "缺少歌曲名"})
                continue
            match = self._match_song(track, excluded_ids=batch_matched_ids)
            if not match:
                failed.append({"track_name": display_name, "artist_name": display_artist, "reason": "网易云未找到可信匹配"})
                continue
            song_id = match["netease_id"]
            if song_id in playlist_existing_ids:
                skipped_existing.append({"track_name": display_name, "artist_name": display_artist, **match})
            else:
                matched.append(song_id)
                batch_matched_ids.add(song_id)
                matched_details.append({"track_name": display_name, "artist_name": display_artist, **match})
            if progress:
                progress(processed=index, percent=8 + int(index / max(total, 1) * 78))

        if matched:
            if progress:
                progress(phase="写入网易云歌单", current=f"正在添加 {len(matched)} 首歌曲", percent=90)
            for start in range(0, len(matched), 100):
                chunk = matched[start:start + 100]
                response = self._post("/playlist/tracks", {"op": "add", "pid": playlist_id, "tracks": ",".join(chunk)})
                code = response.get("code") or response.get("status") or ((response.get("body") or {}).get("code"))
                if code in (301, -462):
                    raise RuntimeError("网易云 Cookie 已失效或触发安全验证")
        return {
            "playlist_id": str(playlist_id),
            "added": len(matched),
            "skipped": len(skipped_existing),
            "skipped_existing": skipped_existing,
            "matched": matched_details,
            "failed": failed,
        }

    def _match_song(self, track: dict[str, Any], excluded_ids: set[str]) -> dict[str, Any] | None:
        name = str(track.get("track_name") or "").strip()
        artist = str(track.get("artist_name") or "").strip()
        original_titles = self._unique_texts(name, str(track.get("track_name_zh") or ""))
        original_artists = self._unique_texts(artist, str(track.get("artist_name_zh") or ""))
        name_zh = str(track.get("track_name_zh") or self._to_simplified(name)).strip()
        direct_zh_alias = ARTIST_ZH_ALIASES.get(normalize_artist_key(artist))
        artist_zh = str(track.get("artist_name_zh") or direct_zh_alias or self._to_simplified(artist)).strip()
        artist_aliases = self._artist_aliases(artist, artist_zh)
        input_artists = self._unique_texts(
            direct_zh_alias,
            artist_zh,
            artist,
            *artist_aliases,
            *artist_search_aliases(artist, artist_zh, *artist_aliases),
        )
        raw_titles = [value for value in (name, name_zh) if value]
        input_titles = self._unique_texts(
            *track_title_aliases(raw_titles, input_artists),
            *raw_titles,
        )
        requested_versions = version_tags(*input_titles)

        queries: list[str] = []
        search_titles = title_search_variants(*input_titles, limit=12)
        primary_artist = input_artists[0] if input_artists else ""
        for search_title in search_titles:
            query = f"{search_title} {primary_artist}".strip()
            if query and query not in queries:
                queries.append(query)
            if len(queries) >= 6:
                break
        for search_artist in input_artists[1:3]:
            for search_title in search_titles[:2]:
                query = f"{search_title} {search_artist}".strip()
                if query and query not in queries:
                    queries.append(query)
                if len(queries) >= 8:
                    break
            if len(queries) >= 8:
                break
        for search_title in search_titles:
            if search_title and search_title not in queries:
                queries.append(search_title)
            if len(queries) >= 10:
                break

        candidates: dict[str, dict[str, Any]] = {}
        for query_index, query in enumerate(queries):
            response = self._post("/cloudsearch", {"keywords": query, "type": 1, "limit": 30})
            strong_hit = False
            for song in ((response.get("result") or {}).get("songs") or []):
                song_id = str(song.get("id") or "")
                if song_id:
                    candidates[song_id] = song
                if not song_id or song_id in excluded_ids:
                    continue
                candidate_titles = [str(song.get("name") or "")]
                candidate_titles.extend(str(item) for item in (song.get("alia") or song.get("alias") or []) if item)
                candidate_artists = [
                    str(item.get("name") or "")
                    for item in (song.get("ar") or song.get("artists") or [])
                    if isinstance(item, dict)
                ]
                title_score = best_title_similarity(input_titles, candidate_titles, self._to_simplified)
                artist_score = best_artist_similarity(input_artists, candidate_artists, self._to_simplified) if input_artists else 1.0
                album = song.get("al") or song.get("album") or {}
                album_name = str(album.get("name") or "") if isinstance(album, dict) else str(album or "")
                candidate_versions = version_tags(*candidate_titles, album_name)
                version_ok = bool(requested_versions & candidate_versions) if requested_versions else not candidate_versions
                if title_score >= 0.96 and artist_score >= 0.98 and version_ok:
                    strong_hit = True
            if strong_hit:
                break
            # Multilingual matches may only appear after the romanized, Korean,
            # and Chinese artist spellings have each been tried. Do not stop on
            # a large batch of unrelated exact-English-title candidates.
            if query_index >= 7 and len(candidates) >= 20:
                break

        candidate_order = {candidate_id: index for index, candidate_id in enumerate(candidates)}
        ranked = []
        for song_id, song in candidates.items():
            if song_id in excluded_ids:
                continue
            candidate_titles = [str(song.get("name") or "")]
            candidate_titles.extend(str(item) for item in (song.get("alia") or song.get("alias") or []) if item)
            artists = song.get("ar") or song.get("artists") or []
            candidate_artists = [str(item.get("name") or "") for item in artists if isinstance(item, dict)]
            album = song.get("al") or song.get("album") or {}
            album_name = str(album.get("name") or "") if isinstance(album, dict) else str(album or "")
            title_score = best_title_similarity(input_titles, candidate_titles, self._to_simplified)
            artist_score = best_artist_similarity(input_artists, candidate_artists, self._to_simplified) if input_artists else 0.5
            score, version_match = combined_match_score(
                title_score,
                artist_score,
                requested_versions,
                version_tags(*candidate_titles, album_name),
            )
            ranked.append((score, version_match, title_score, artist_score, song_id, song, candidate_artists))

        ranked.sort(key=lambda item: (item[0], item[1], item[2], item[3]), reverse=True)
        if not ranked:
            if self.metadata_resolver and not track.get("_metadata_retry"):
                resolved_titles, resolved_artists = self.metadata_resolver.resolve(original_titles, original_artists)
                original_title_keys = {normalize_match_text(item) for item in original_titles}
                original_artist_keys = {normalize_match_text(item) for item in original_artists}
                alternate_title = next((value for value in resolved_titles if normalize_match_text(value) not in original_title_keys), "")
                alternate_artist = next((value for value in resolved_artists if normalize_match_text(value) not in original_artist_keys), "")
                if alternate_title:
                    retry_track = dict(track)
                    retry_track.update({"track_name_zh": alternate_title, "artist_name_zh": alternate_artist, "_metadata_retry": True})
                    return self._match_song(retry_track, excluded_ids)
            return None
        score, _version_match, title_score, artist_score, song_id, song, candidate_artists = ranked[0]
        if not confident_match(title_score, artist_score, score, artist_required=bool(input_artists and candidate_artists)):
            if self.metadata_resolver:
                if not track.get("_metadata_retry"):
                    resolved_titles, resolved_artists = self.metadata_resolver.resolve(original_titles, original_artists)
                    alternate_title = next(
                        (value for value in resolved_titles if normalize_match_text(value) not in {normalize_match_text(item) for item in original_titles}),
                        "",
                    )
                    alternate_artist = next(
                        (value for value in resolved_artists if normalize_match_text(value) not in {normalize_match_text(item) for item in original_artists}),
                        "",
                    )
                    if alternate_title:
                        retry_track = dict(track)
                        retry_track.update({"track_name_zh": alternate_title, "artist_name_zh": alternate_artist, "_metadata_retry": True})
                        return self._match_song(retry_track, excluded_ids)
                fallback_ranked = sorted(ranked, key=lambda item: candidate_order.get(item[4], 10**9))
                localized_title = str(track.get("track_name_zh") or "").strip() if track.get("_metadata_retry") else ""
                if localized_title:
                    localized_is_non_latin = not bool(re.search(r"[A-Za-z]", localized_title))
                    fallback_ranked = sorted(
                        ranked,
                        key=lambda item: (
                            best_title_similarity([localized_title], [str(item[5].get("name") or "")], self._to_simplified),
                            int(localized_is_non_latin and not any(re.search(r"[A-Za-z]", value) for value in item[6])),
                            -candidate_order.get(item[4], 10**9),
                        ),
                        reverse=True,
                    )
                for fallback in fallback_ranked[:4]:
                    fallback_score, _vm, _ts, _as, fallback_id, fallback_song, fallback_artists = fallback
                    fallback_titles = [str(fallback_song.get("name") or "")]
                    fallback_titles.extend(str(item) for item in (fallback_song.get("alia") or fallback_song.get("alias") or []) if item)
                    if self.metadata_resolver.verify_candidate(
                        original_titles,
                        original_artists,
                        fallback_titles,
                        fallback_artists,
                    ):
                        return {
                            "netease_id": fallback_id,
                            "netease_name": str(fallback_song.get("name") or ""),
                            "netease_artist": " / ".join(fallback_artists),
                            "match_score": round(max(fallback_score, 0.9), 4),
                        }
            return None
        return {
            "netease_id": song_id,
            "netease_name": str(song.get("name") or ""),
            "netease_artist": " / ".join(candidate_artists),
            "match_score": round(score, 4),
        }

    @classmethod
    def _best_similarity(cls, left_values: set[str], right_values: list[str], clean_title: bool) -> float:
        if clean_title:
            return best_title_similarity(left_values, right_values, cls._to_simplified)
        return best_artist_similarity(left_values, right_values, cls._to_simplified)

    @classmethod
    def _normalize(cls, value: str) -> str:
        return normalize_match_text(value, cls._to_simplified)

    @staticmethod
    def _clean_title(value: str) -> str:
        variants = title_search_variants(value, limit=1)
        return variants[0] if variants else value.strip()

    @staticmethod
    def _to_simplified(value: str) -> str:
        return zh_convert(value, locale="zh-cn") if zh_convert else value

    @staticmethod
    def _artist_aliases(*values: str) -> list[str]:
        aliases: list[str] = []
        for value in values:
            clean_value = str(value or "").strip()
            if not clean_value:
                continue
            for mapping in (ARTIST_ZH_ALIASES, ARTIST_EN_ALIASES):
                mapped = mapping.get(normalize_artist_key(clean_value))
                if not mapped or mapped == clean_value:
                    continue
                aliases.append(mapped)
                if mapped.casefold() not in clean_value.casefold() and clean_value.casefold() not in mapped.casefold():
                    aliases.extend((f"{clean_value}{mapped}", f"{mapped}{clean_value}"))
        return NetEaseClient._unique_texts(*aliases)

    @staticmethod
    def _unique_texts(*values: str) -> list[str]:
        output: list[str] = []
        seen: set[str] = set()
        for value in values:
            item = str(value or "").strip()
            key = normalize_artist_key(item)
            if item and key not in seen:
                seen.add(key)
                output.append(item)
        return output

    def _require(self) -> None:
        if not self.api_url or not self.cookie or not self.uid:
            raise ValueError("请先配置并校验网易云 Cookie")

    def _post(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        if not self.api_url:
            raise ValueError("网易云 API 地址不能为空")
        body = dict(data)
        timestamp = int(time.time() * 1000)
        body["timestamp"] = timestamp
        body["cookie"] = self.cookie
        cache_buster = {"timestamp": timestamp}
        if path == "/cloudsearch" and body.get("keywords"):
            cache_buster["keywords"] = str(body["keywords"])
        request_url = self.api_url + path + "?" + urlencode(cache_buster)
        request = urllib.request.Request(
            request_url,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Cache-Control": "no-cache", "Pragma": "no-cache"},
            method="POST",
        )
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": self.proxy_url, "https": self.proxy_url})
        ) if self.proxy_url else urllib.request.build_opener(urllib.request.ProxyHandler({}))
        last_error: BaseException | None = None
        for attempt in range(2):
            try:
                with opener.open(request, timeout=30) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                raise RuntimeError(f"网易云 API HTTP {exc.code}") from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
                if attempt == 0:
                    time.sleep(0.35)
        reason = getattr(last_error, "reason", last_error)
        raise RuntimeError(f"网易云 API 网络请求失败：{reason}") from last_error