from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode, urlparse

from music_matching import (
    artist_search_aliases,
    best_artist_similarity,
    best_title_similarity,
    combined_match_score,
    confident_match,
    track_title_aliases,
    title_search_variants,
    version_tags,
)


DEFAULT_KUGOU_URL = ""


def _find(value: Any, names: set[str]) -> Any:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).casefold() in names and item not in (None, ""):
                return item
        for item in value.values():
            found = _find(item, names)
            if found not in (None, ""):
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find(item, names)
            if found not in (None, ""):
                return found
    return None


def _parse_cookie(value: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for part in str(value or "").split(";"):
        if "=" not in part:
            continue
        key, item = part.split("=", 1)
        if key.strip():
            result[key.strip().casefold()] = item.strip()
    return result


class KugouClient:
    """Read/search/write client for the verified lite KuGou API deployment."""

    def __init__(
        self,
        auth_file: Path,
        alias_map: dict[str, str] | None = None,
        to_simplified: Callable[[str], str] | None = None,
        proxy_url: str = "",
        metadata_resolver: Any = None,
        persist_credentials: bool = True,
    ) -> None:
        self.auth_file = auth_file
        self.auth_log = auth_file.with_name("auth.log")
        self.alias_map = {
            re.sub(r"\s+", " ", str(key or "").strip()).casefold(): str(value)
            for key, value in (alias_map or {}).items()
            if str(key or "").strip() and str(value or "").strip()
        }
        self.to_simplified = to_simplified or (lambda value: value)
        self.default_proxy_url = proxy_url.strip()
        self.metadata_resolver = metadata_resolver
        self.persist_credentials = persist_credentials
        self.api_url = ""
        self.proxy_url = ""
        self.cookie = ""
        self.token = ""
        self.userid = ""
        self.dfid = ""
        self.mid = ""
        self.lock = threading.Lock()
        self.reload()

    def reload(self) -> None:
        try:
            stored = json.loads(self.auth_file.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            stored = {}
        if not isinstance(stored, dict):
            stored = {}
        self.api_url = str(stored.get("base_url") or DEFAULT_KUGOU_URL).strip().rstrip("/")
        self.proxy_url = str(stored.get("proxy_url", self.default_proxy_url)).strip()
        self.cookie = str(stored.get("cookie") or "").strip()
        fields = _parse_cookie(self.cookie)
        self.token = str(stored.get("token") or fields.get("token") or "")
        self.userid = str(stored.get("userid") or fields.get("userid") or "")
        self.dfid = str(stored.get("dfid") or fields.get("dfid") or "")
        self.mid = str(stored.get("mid") or fields.get("mid") or fields.get("kugou_api_mid") or "")

    def status(self) -> dict[str, Any]:
        if self.persist_credentials:
            self.reload()
        return {
            "configured": bool(self.api_url and self.cookie and self.token and self.userid),
            "api_url": self.api_url,
            "proxy_url": self.proxy_url,
            "userid": self.userid,
            "has_cookie": bool(self.cookie),
        }

    def configure(self, api_url: str, cookie: str, proxy_url: str = "") -> dict[str, Any]:
        parsed = urlparse(api_url.strip())
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("酷狗 API 地址必须是有效的 http/https URL")
        fields = _parse_cookie(cookie)
        if not fields.get("token") or not fields.get("userid"):
            raise ValueError("酷狗 Cookie 必须包含 token 和 userid")
        previous = (self.api_url, self.proxy_url, self.cookie, self.token, self.userid, self.dfid, self.mid)
        self.api_url = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
        self.proxy_url = proxy_url.strip()
        self.cookie = cookie.strip()
        self.token = fields["token"]
        self.userid = fields["userid"]
        self.dfid = fields.get("dfid", "")
        self.mid = fields.get("mid", fields.get("kugou_api_mid", ""))
        try:
            self.playlists()
        except Exception:
            self.api_url, self.proxy_url, self.cookie, self.token, self.userid, self.dfid, self.mid = previous
            raise
        if self.persist_credentials:
            self._persist("manual_config")
        return self.status()

    def playlists(self) -> list[dict[str, Any]]:
        self._require()
        payload = self._request("/user/playlist", {"page": 1, "pagesize": 100})
        data = payload.get("data") or {}
        if isinstance(data.get("data"), dict):
            data = data["data"]
        info = data.get("info") or []
        result = []
        for item in info if isinstance(info, list) else []:
            list_id = item.get("listid")
            if list_id is None:
                continue
            result.append({
                "id": str(list_id),
                "name": str(item.get("name") or "未命名歌单"),
                "trackCount": int(item.get("count") or item.get("m_count") or item.get("per_count") or 0),
                "globalId": str(item.get("global_collection_id") or ""),
                "isMine": bool(item.get("is_mine") or str(item.get("list_create_userid")) == self.userid),
            })
        return result

    def playlist_tracks(self, playlist_id: str) -> list[dict[str, Any]]:
        self._require()
        page = 1
        result: list[dict[str, Any]] = []
        while page <= 20:
            try:
                payload = self._request("/playlist/track/all/new", {"listid": playlist_id, "page": page, "pagesize": 100})
            except RuntimeError as exc:
                if "30228" in str(exc) and page == 1:
                    return []
                raise
            data = payload.get("data") or {}
            if isinstance(data.get("data"), dict):
                data = data["data"]
            info = data.get("info") or []
            if not isinstance(info, list) or not info:
                break
            result.extend(info)
            if len(info) < 100:
                break
            page += 1
        return result

    def playlist_seed_tracks(self, playlist_id: str) -> list[dict[str, str]]:
        """Return the small name/artist shape used by the Embeat matcher.

        KuGou has returned several field spellings across API deployments. Keep
        that normalization here so playlist radio does not depend on one raw
        response version.
        """
        output: list[dict[str, str]] = []
        for item in self.playlist_tracks(playlist_id):
            if not isinstance(item, dict):
                continue
            name = self._first_text(item, (
                "OriSongName", "SongName", "songname", "song_name", "name",
                "audio_name", "AudioName", "FileName", "filename",
            ))
            artist = self._first_text(item, (
                "SingerName", "singername", "singer_name", "AuthorName",
                "author_name", "artist", "artist_name",
            ))
            if not artist:
                singers = item.get("Singers") or item.get("singers") or []
                if isinstance(singers, list):
                    artist = " / ".join(
                        self._first_text(singer, ("name", "Name", "singername", "SingerName"))
                        for singer in singers if isinstance(singer, dict)
                    ).strip(" /")
            name = re.sub(r"\.[A-Za-z0-9]{2,5}$", "", name).strip()
            if not artist and " - " in name:
                possible_artist, possible_name = name.split(" - ", 1)
                if possible_artist.strip() and possible_name.strip():
                    artist, name = possible_artist.strip(), possible_name.strip()
            if name and artist:
                output.append({"name": name, "artist": artist})
        return output

    @staticmethod
    def _first_text(item: dict[str, Any], keys: tuple[str, ...]) -> str:
        for key in keys:
            value = item.get(key)
            if value not in (None, ""):
                return str(value).strip()
        return ""

    def export(
        self,
        tracks: list[dict[str, Any]],
        playlist_id: str = "NEW",
        playlist_name: str = "",
        progress: Callable[..., None] | None = None,
    ) -> dict[str, Any]:
        self._require()
        if not tracks:
            raise ValueError("请至少选择一首歌曲")
        if progress:
            progress(status="running", phase="准备酷狗歌单", percent=2)
        if playlist_id == "NEW":
            playlist_id = self._create_playlist(playlist_name)
        existing = self.playlist_tracks(playlist_id)
        existing_hashes = {str(item.get("hash") or "").casefold() for item in existing if item.get("hash")}
        batch_hashes: set[str] = set()
        matched: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        total = len(tracks)
        for index, track in enumerate(tracks, start=1):
            name = str(track.get("track_name") or "").strip()
            artist = str(track.get("artist_name") or "").strip()
            display_name = str(track.get("track_name_zh") or name)
            display_artist = str(track.get("artist_name_zh") or artist)
            if progress:
                progress(status="running", phase="匹配酷狗曲库", current=f"{display_name} - {display_artist}", processed=index - 1, percent=8 + int((index - 1) / max(total, 1) * 78))
            match = self._match_song(track, {item["hash"].casefold() for item in matched} | batch_hashes)
            if not match:
                failed.append({"track_name": display_name, "artist_name": display_artist, "reason": "酷狗未找到可信匹配"})
            elif match["hash"].casefold() in existing_hashes or match["hash"].casefold() in batch_hashes:
                skipped.append({"track_name": display_name, "artist_name": display_artist, **match})
            else:
                matched.append({"track_name": display_name, "artist_name": display_artist, **match})
                batch_hashes.add(match["hash"].casefold())
            if progress:
                progress(processed=index, percent=8 + int(index / max(total, 1) * 78))

        added = 0
        if matched:
            if progress:
                progress(phase="写入酷狗歌单", current=f"正在添加 {len(matched)} 首歌曲", percent=90)
            for start in range(0, len(matched), 50):
                chunk = matched[start : start + 50]
                values = []
                for item in chunk:
                    values.append("|".join([
                        item["kugou_name"], item["hash"], item.get("album_id", ""), item.get("mixsongid", ""),
                    ]))
                self._request("/playlist/tracks/add", {"listid": playlist_id, "data": ",".join(values)})
                added += len(chunk)
        return {"playlist_id": str(playlist_id), "added": added, "skipped": len(skipped), "skipped_existing": skipped, "matched": matched, "failed": failed}

    def _create_playlist(self, name: str) -> str:
        name = name.strip()
        if not name:
            raise ValueError("酷狗新歌单名称不能为空")
        payload = self._request("/playlist/add", {"name": name, "type": 0, "is_pri": 0, "list_create_userid": self.userid, "list_create_listid": 0})
        list_id = _find(payload, {"listid", "list_id"})
        if list_id is not None:
            return str(list_id)
        for item in self.playlists():
            if item["name"] == name:
                return item["id"]
        raise RuntimeError("酷狗 API 未返回新歌单 ID")

    def _match_song(self, track: dict[str, Any], excluded_hashes: set[str]) -> dict[str, Any] | None:
        name = str(track.get("track_name") or "").strip()
        artist = str(track.get("artist_name") or "").strip()
        original_titles = self._unique_texts(name, str(track.get("track_name_zh") or ""))
        original_artists = self._unique_texts(artist, str(track.get("artist_name_zh") or ""))
        name_zh = str(track.get("track_name_zh") or self.to_simplified(name)).strip()
        artist_alias = self.alias_map.get(re.sub(r"\s+", " ", artist).strip().casefold())
        supplied_artist_zh = str(track.get("artist_name_zh") or "").strip()
        reverse_alias = self.alias_map.get(re.sub(r"\s+", " ", supplied_artist_zh).casefold()) if supplied_artist_zh else ""
        artist_has_cjk = bool(re.search(r"[\u3400-\u9fff]", artist))
        artist_zh = str(supplied_artist_zh or (artist if artist_has_cjk else artist_alias) or self.to_simplified(artist)).strip()
        input_artists = self._unique_texts(
            artist_alias,
            artist_zh,
            artist,
            reverse_alias,
            *artist_search_aliases(artist_alias, artist_zh, artist, reverse_alias),
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
            response = self._request("/search", {"keywords": query, "type": "song", "page": 1, "pagesize": 30})
            data = response.get("data") or {}
            if isinstance(data.get("data"), dict):
                data = data["data"]
            strong_hit = False
            for item in data.get("lists") or []:
                song_hash = str(item.get("FileHash") or item.get("Hash") or "").strip()
                if song_hash:
                    candidates[song_hash.casefold()] = item
                if not song_hash or song_hash.casefold() in excluded_hashes:
                    continue
                title = str(item.get("OriSongName") or item.get("SongName") or item.get("FileName") or "")
                title = re.sub(r"\.[A-Za-z0-9]{2,5}$", "", title).strip()
                singer = str(item.get("SingerName") or "")
                if not singer and item.get("Singers"):
                    singer = " / ".join(str(singer_item.get("name") or "") for singer_item in item["Singers"] if isinstance(singer_item, dict))
                title_score = best_title_similarity(input_titles, [title], self.to_simplified)
                artist_score = best_artist_similarity(input_artists, [singer], self.to_simplified) if singer else 0.0
                candidate_versions = version_tags(title, str(item.get("AlbumName") or ""))
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
        candidate_order = {candidate_hash: index for index, candidate_hash in enumerate(candidates)}
        ranked = []
        for song_hash, song in candidates.items():
            if song_hash in excluded_hashes:
                continue
            title = str(song.get("OriSongName") or song.get("SongName") or song.get("FileName") or "")
            title = re.sub(r"\.[A-Za-z0-9]{2,5}$", "", title).strip()
            singer = str(song.get("SingerName") or "")
            if not singer and song.get("Singers"):
                singer = " / ".join(str(item.get("name") or "") for item in song["Singers"] if isinstance(item, dict))
            album_name = str(song.get("AlbumName") or "")
            title_score = best_title_similarity(input_titles, [title], self.to_simplified)
            artist_score = best_artist_similarity(input_artists, [singer], self.to_simplified) if singer else 0.0
            score, version_match = combined_match_score(
                title_score,
                artist_score,
                requested_versions,
                version_tags(title, album_name),
            )
            ranked.append((score, version_match, title_score, artist_score, song_hash, song, title, singer))
        ranked.sort(key=lambda item: (item[0], item[1], item[2], item[3]), reverse=True)
        if not ranked:
            if self.metadata_resolver and not track.get("_metadata_retry"):
                resolved_titles, resolved_artists = self.metadata_resolver.resolve(original_titles, original_artists)
                original_title_keys = {re.sub(r"[^\w\u3400-\u9fff]+", "", item.casefold()) for item in original_titles}
                original_artist_keys = {re.sub(r"[^\w\u3400-\u9fff]+", "", item.casefold()) for item in original_artists}
                alternate_title = next((value for value in resolved_titles if re.sub(r"[^\w\u3400-\u9fff]+", "", value.casefold()) not in original_title_keys), "")
                alternate_artist = next((value for value in resolved_artists if re.sub(r"[^\w\u3400-\u9fff]+", "", value.casefold()) not in original_artist_keys), "")
                if alternate_title:
                    retry_track = dict(track)
                    retry_track.update({"track_name_zh": alternate_title, "artist_name_zh": alternate_artist, "_metadata_retry": True})
                    return self._match_song(retry_track, excluded_hashes)
            return None
        score, _version_match, title_score, artist_score, song_hash, song, title, singer = ranked[0]
        if not confident_match(title_score, artist_score, score, artist_required=bool(input_artists and singer)):
            if self.metadata_resolver:
                if not track.get("_metadata_retry"):
                    resolved_titles, resolved_artists = self.metadata_resolver.resolve(original_titles, original_artists)
                    original_title_keys = {re.sub(r"[^\w\u3400-\u9fff]+", "", item.casefold()) for item in original_titles}
                    original_artist_keys = {re.sub(r"[^\w\u3400-\u9fff]+", "", item.casefold()) for item in original_artists}
                    alternate_title = next(
                        (value for value in resolved_titles if re.sub(r"[^\w\u3400-\u9fff]+", "", value.casefold()) not in original_title_keys),
                        "",
                    )
                    alternate_artist = next(
                        (value for value in resolved_artists if re.sub(r"[^\w\u3400-\u9fff]+", "", value.casefold()) not in original_artist_keys),
                        "",
                    )
                    if alternate_title:
                        retry_track = dict(track)
                        retry_track.update({"track_name_zh": alternate_title, "artist_name_zh": alternate_artist, "_metadata_retry": True})
                        return self._match_song(retry_track, excluded_hashes)
                fallback_ranked = sorted(ranked, key=lambda item: candidate_order.get(item[4], 10**9))
                localized_title = str(track.get("track_name_zh") or "").strip() if track.get("_metadata_retry") else ""
                if localized_title:
                    localized_is_non_latin = not bool(re.search(r"[A-Za-z]", localized_title))
                    fallback_ranked = sorted(
                        ranked,
                        key=lambda item: (
                            best_title_similarity([localized_title], [item[6]], self.to_simplified),
                            int(localized_is_non_latin and not re.search(r"[A-Za-z]", item[7])),
                            -candidate_order.get(item[4], 10**9),
                        ),
                        reverse=True,
                    )
                for fallback in fallback_ranked[:4]:
                    fallback_score, _vm, _ts, _as, fallback_hash, fallback_song, fallback_title, fallback_singer = fallback
                    if self.metadata_resolver.verify_candidate(
                        original_titles,
                        original_artists,
                        [fallback_title],
                        [fallback_singer],
                    ):
                        return {
                            "hash": str(fallback_song.get("FileHash") or fallback_hash).upper(),
                            "kugou_name": fallback_title or name,
                            "kugou_artist": fallback_singer,
                            "album_id": str(fallback_song.get("AlbumID") or fallback_song.get("AlbumId") or ""),
                            "mixsongid": str(fallback_song.get("MixSongID") or fallback_song.get("SongID") or ""),
                            "match_score": round(max(fallback_score, 0.9), 4),
                        }
            return None
        return {
            "hash": str(song.get("FileHash") or song_hash).upper(),
            "kugou_name": title or name,
            "kugou_artist": singer,
            "album_id": str(song.get("AlbumID") or song.get("AlbumId") or ""),
            "mixsongid": str(song.get("MixSongID") or song.get("SongID") or ""),
            "match_score": round(score, 4),
        }

    @staticmethod
    def _clean_title(value: str) -> str:
        variants = title_search_variants(value, limit=1)
        return variants[0] if variants else value.strip()

    @staticmethod
    def _similarity_set(left: set[str], right: list[str]) -> float:
        return best_title_similarity(left, right)

    @staticmethod
    def _unique_texts(*values: str) -> list[str]:
        output: list[str] = []
        seen: set[str] = set()
        for value in values:
            item = str(value or "").strip()
            key = re.sub(r"\s+", " ", item).casefold()
            if item and key not in seen:
                seen.add(key)
                output.append(item)
        return output

    def _require(self) -> None:
        if not self.api_url or not self.cookie or not self.token or not self.userid:
            raise ValueError("请先配置并校验酷狗 Cookie")

    def _request(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._require()
        query = dict(params or {})
        query["timestamp"] = int(time.time() * 1000)
        query["cookie"] = self.cookie
        url = self.api_url + path + "?" + urlencode(query)
        request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "EmbeatUI/1.0"})
        last_error: BaseException | None = None
        for attempt in range(2):
            try:
                opener = urllib.request.build_opener(
                    urllib.request.ProxyHandler({"http": self.proxy_url, "https": self.proxy_url})
                ) if self.proxy_url else urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with opener.open(request, timeout=35) as response:
                    body = response.read().decode("utf-8", errors="replace")
                last_error = None
                break
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                last_error = None
                break
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
                if attempt == 0:
                    time.sleep(0.35)
        if last_error:
            raise RuntimeError(f"酷狗 API 网络请求失败：{last_error}") from last_error
        start, end = body.find("{"), body.rfind("}")
        if start >= 0 and end >= start:
            body = body[start : end + 1]
        try:
            result = json.loads(body)
        except (ValueError, TypeError) as exc:
            raise RuntimeError("酷狗 API 返回了无效 JSON") from exc
        code = int(result.get("error_code", 0) or 0)
        if code:
            if code == 152:
                raise RuntimeError("酷狗 Cookie 已失效或搜索接口要求重新登录")
            raise RuntimeError(str(result.get("error_msg") or f"酷狗 API 错误 {code}"))
        return result

    def _persist(self, event: str) -> None:
        self.auth_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            stored = json.loads(self.auth_file.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            stored = {}
        if not isinstance(stored, dict):
            stored = {}
        stored.update({"base_url": self.api_url, "proxy_url": self.proxy_url, "cookie": self.cookie, "token": self.token, "userid": self.userid, "dfid": self.dfid, "mid": self.mid, "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
        tmp = self.auth_file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.auth_file)
        with self.auth_log.open("a", encoding="utf-8") as log:
            log.write(json.dumps({"event": event, **stored}, ensure_ascii=False) + "\n")
