from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse


from config import CONFIG  # noqa: E402

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
EMBEAT_ROOT = CONFIG.embeat_root
EMBEAT_INFER_DIR = CONFIG.embeat_infer_dir

if str(EMBEAT_INFER_DIR) not in sys.path:
    sys.path.insert(0, str(EMBEAT_INFER_DIR))

from Embeat import EmbeatDatabase, qdrant_models  # noqa: E402
from export_manager import ExportManager  # noqa: E402
from app_database import AppDatabase  # noqa: E402
from artist_aliases import (  # noqa: E402
    build_artist_alias_maps,
    load_curated_aliases,
    load_musicbrainz_aliases,
    merge_artist_alias_sources,
    normalize_artist_key,
)
from kugou_client import KugouClient  # noqa: E402
from music_metadata import MusicMetadataResolver  # noqa: E402
from music_matching import (  # noqa: E402
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


class EmbeatService:
    def __init__(self) -> None:
        self.app_db = AppDatabase(APP_DIR)
        self.database = EmbeatDatabase(
            qdrant_url=CONFIG.qdrant_url,
            qdrant_api_key=CONFIG.qdrant_api_key,
            collection_name=CONFIG.qdrant_collection,
            qdrant_timeout=CONFIG.qdrant_timeout,
            verbose_log=False,
        )
        self.database.verbose_log = False
        self.lock = threading.Lock()
        self.netease = NetEaseClient(metadata_resolver=METADATA_RESOLVER)
        self.kugou = KugouClient(
            APP_DIR / "data" / ".disabled_credentials.json",
            alias_map={**ARTIST_ZH_ALIASES, **ARTIST_EN_ALIASES},
            to_simplified=lambda value: zh_convert(value, locale="zh-cn") if zh_convert else value,
            proxy_url=CONFIG.proxy_url,
            metadata_resolver=METADATA_RESOLVER,
            persist_credentials=False,
        )
        self.export_manager = ExportManager(self.netease, self.kugou)

    def _credential_client(self, user_id: int, platform: str) -> Any:
        values = self.app_db.get_credential(user_id, platform)
        if not values or not values.get("cookie"):
            if platform == "kugou":
                return KugouClient(APP_DIR / "data" / ".disabled_credentials.json", alias_map={**ARTIST_ZH_ALIASES, **ARTIST_EN_ALIASES}, to_simplified=lambda value: zh_convert(value, locale="zh-cn") if zh_convert else value, proxy_url=CONFIG.proxy_url, metadata_resolver=METADATA_RESOLVER, persist_credentials=False)
            return NetEaseClient(metadata_resolver=METADATA_RESOLVER)
        if platform == "kugou":
            client = KugouClient(APP_DIR / "data" / ".disabled_credentials.json", alias_map={**ARTIST_ZH_ALIASES, **ARTIST_EN_ALIASES}, to_simplified=lambda value: zh_convert(value, locale="zh-cn") if zh_convert else value, proxy_url=values.get("proxy_url") or CONFIG.proxy_url, metadata_resolver=METADATA_RESOLVER, persist_credentials=False)
            client.api_url = str(values.get("api_url") or client.api_url).rstrip("/")
            client.proxy_url = str(values.get("proxy_url") or client.proxy_url)
            client.cookie = str(values.get("cookie") or "")
            cookie_fields = {}
            for part in client.cookie.split(";"):
                key, separator, item = part.strip().partition("=")
                if separator and key:
                    cookie_fields[key.casefold()] = item
            client.token = str(cookie_fields.get("token") or "")
            client.userid = str(cookie_fields.get("userid") or values.get("uid") or "")
            client.dfid = str(cookie_fields.get("dfid") or "")
            client.mid = str(cookie_fields.get("mid") or cookie_fields.get("kugou_api_mid") or "")
            return client
        client = NetEaseClient(metadata_resolver=METADATA_RESOLVER)
        client.api_url = str(values.get("api_url") or "").rstrip("/")
        client.proxy_url = str(values.get("proxy_url") or "")
        client.cookie = str(values.get("cookie") or "")
        client.uid = str(values.get("uid") or "")
        return client

    def platform_status(self, user_id: int, platform: str) -> dict[str, Any]:
        client = self._credential_client(user_id, platform)
        status = client.status()
        stored = self.app_db.get_credential(user_id, platform) or {}
        status.pop("cookie", None)
        status.pop("has_cookie", None)
        status["configured"] = bool(stored) and bool(status.get("configured"))
        status["api_url"] = str(stored.get("api_url") or status.get("api_url") or "")
        status["proxy_url"] = str(stored.get("proxy_url") or status.get("proxy_url") or "")
        status["phone"] = str(stored.get("phone") or "")
        return status

    def configure_platform(self, user_id: int, platform: str, values: dict[str, Any]) -> dict[str, Any]:
        current = self.app_db.get_credential(user_id, platform) or {}
        cookie = str(values.get("cookie") or current.get("cookie") or "")
        api_url = str(values.get("api_url") or current.get("api_url") or (CONFIG.kugou_api_url if platform == "kugou" else ""))
        proxy_url = str(values.get("proxy_url") if values.get("proxy_url") is not None else current.get("proxy_url") or "")
        client = KugouClient(APP_DIR / "data" / ".disabled_credentials.json", alias_map={**ARTIST_ZH_ALIASES, **ARTIST_EN_ALIASES}, to_simplified=lambda value: zh_convert(value, locale="zh-cn") if zh_convert else value, proxy_url=proxy_url, metadata_resolver=METADATA_RESOLVER, persist_credentials=False) if platform == "kugou" else NetEaseClient(metadata_resolver=METADATA_RESOLVER)
        result = client.configure(api_url, cookie, proxy_url)
        values_to_save = {"api_url": api_url, "proxy_url": proxy_url, "cookie": cookie, **result}
        if values.get("phone"):
            values_to_save["phone"] = str(values.get("phone"))
        if platform == "kugou":
            values_to_save.update({"token": client.token, "userid": client.userid, "dfid": client.dfid, "mid": client.mid})
        self.app_db.save_credential(user_id, platform, values_to_save)
        result = dict(result)
        result["configured"] = True
        result.pop("cookie", None)
        return result

    def send_phone_captcha(self, platform: str, api_url: str, proxy_url: str, phone: str, country_code: str = "86") -> dict[str, Any]:
        phone = re.sub(r"\s+", "", phone)
        if not phone or not phone.isdigit():
            raise ValueError("请输入有效手机号")
        if platform == "netease":
            payload, _ = self._public_api_request(api_url, "/captcha/sent", {"phone": phone, "ctcode": country_code or "86"}, proxy_url, method="POST")
            code = payload.get("code")
            if code not in (None, 200):
                raise RuntimeError(str(payload.get("message") or payload.get("msg") or f"网易云验证码发送失败 ({code})"))
        elif platform == "kugou":
            payload, _ = self._public_api_request(api_url, "/captcha/sent", {"mobile": phone}, proxy_url, method="GET")
            error_code = int(payload.get("error_code", 0) or 0)
            if error_code:
                raise RuntimeError(str(payload.get("error_msg") or f"酷狗验证码发送失败 ({error_code})"))
        else:
            raise ValueError("不支持的音乐平台")
        return {"sent": True, "phone": phone}

    def login_phone_captcha(self, user_id: int, platform: str, api_url: str, proxy_url: str, phone: str, code: str, country_code: str = "86") -> dict[str, Any]:
        phone = re.sub(r"\s+", "", phone)
        code = code.strip()
        if not phone.isdigit() or not code:
            raise ValueError("手机号和验证码不能为空")
        if platform == "netease":
            payload, cookies = self._public_api_request(api_url, "/login/cellphone", {"phone": phone, "captcha": code, "countrycode": country_code or "86", "ctcode": country_code or "86"}, proxy_url, method="POST")
            response_code = payload.get("code")
            if response_code not in (None, 200):
                raise RuntimeError(str(payload.get("message") or payload.get("msg") or f"网易云验证码登录失败 ({response_code})"))
        elif platform == "kugou":
            payload, cookies = self._public_api_request(api_url, "/login/cellphone", {"mobile": phone, "code": code}, proxy_url, method="GET")
            error_code = int(payload.get("error_code", 0) or 0)
            if error_code:
                raise RuntimeError(str(payload.get("error_msg") or f"酷狗验证码登录失败 ({error_code})"))
        else:
            raise ValueError("不支持的音乐平台")
        cookie = self._extract_login_cookie(payload, cookies, platform)
        if not cookie:
            raise RuntimeError("登录成功响应中没有可保存的 Cookie 或 Token")
        return self.configure_platform(user_id, platform, {"api_url": api_url, "proxy_url": proxy_url, "cookie": cookie, "phone": phone})

    @staticmethod
    def _public_api_request(api_url: str, path: str, params: dict[str, Any], proxy_url: str = "", method: str = "GET") -> tuple[dict[str, Any], list[str]]:
        parsed = urlparse(api_url.strip())
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("API 地址必须是有效的 http/https URL")
        base_url = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
        query = {**params, "timestamp": int(time.time() * 1000)}
        url = base_url + path
        data = None
        headers = {"Accept": "application/json", "User-Agent": "EmbeatUI/1.0"}
        if method == "POST":
            url += "?" + urlencode({"timestamp": query["timestamp"]})
            data = json.dumps(query, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        else:
            url += "?" + urlencode(query)
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})) if proxy_url else urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(request, timeout=35) as response:
                raw = response.read().decode("utf-8", errors="replace")
                cookies = response.headers.get_all("Set-Cookie") or []
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            cookies = exc.headers.get_all("Set-Cookie") or []
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(f"音乐 API 网络请求失败：{getattr(exc, 'reason', exc)}") from exc
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end >= start:
            raw = raw[start:end + 1]
        try:
            payload = json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise RuntimeError("音乐 API 返回了无效 JSON") from exc
        return payload if isinstance(payload, dict) else {}, cookies

    @classmethod
    def _extract_login_cookie(cls, payload: dict[str, Any], header_cookies: list[str], platform: str) -> str:
        raw_cookie = cls._find_login_value(payload, {"cookie", "cookies"})
        if isinstance(raw_cookie, list):
            cookie = "; ".join(str(item).split(";", 1)[0] for item in raw_cookie if item)
        elif isinstance(raw_cookie, str):
            cookie = raw_cookie.strip()
        else:
            cookie = ""
        if not cookie and header_cookies:
            cookie = "; ".join(str(item).split(";", 1)[0] for item in header_cookies if "=" in str(item))
        if platform == "kugou":
            fields = {}
            for name in ("token", "userid", "dfid", "mid"):
                value = cls._find_login_value(payload, {name, "user_id" if name == "userid" else name})
                if value not in (None, ""):
                    fields[name] = str(value)
            existing = {part.split("=", 1)[0].strip().casefold() for part in cookie.split(";") if "=" in part}
            additions = [f"{name}={value}" for name, value in fields.items() if name not in existing]
            cookie = "; ".join([item for item in (cookie, *additions) if item])
        return cookie

    @classmethod
    def _find_login_value(cls, value: Any, names: set[str]) -> Any:
        if isinstance(value, dict):
            for key, item in value.items():
                if str(key).casefold() in names and item not in (None, ""):
                    return item
            for item in value.values():
                found = cls._find_login_value(item, names)
                if found not in (None, ""):
                    return found
        elif isinstance(value, list):
            for item in value:
                found = cls._find_login_value(item, names)
                if found not in (None, ""):
                    return found
        return None

    def _new_database(self) -> EmbeatDatabase:
        database = EmbeatDatabase(verbose_log=False)
        database.verbose_log = False
        return database

    def reconnect_qdrant(self) -> None:
        with self.lock:
            self.database = self._new_database()

    def _qdrant_call(self, operation: Any) -> Any:
        """Retry one Qdrant operation after rebuilding stale clients."""
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

    @staticmethod
    def _variants(value: str) -> list[str]:
        variants = [value.strip()]
        if zh_convert and value.strip():
            for locale in ("zh-hk", "zh-cn"):
                converted = zh_convert(value.strip(), locale=locale)
                if converted not in variants:
                    variants.append(converted)
        return [item for item in variants if item]

    @staticmethod
    def _similarity(left: str, right: str) -> float:
        if not left or not right:
            return 0.0
        return SequenceMatcher(None, left.casefold(), right.casefold()).ratio()

    def health(self) -> dict[str, Any]:
        info = self._qdrant_call(lambda database: database.client.get_collection(database.collection_name))
        return {
            "status": str(info.status),
            "collection": self.database.collection_name,
            "points": int(info.points_count or 0),
            "qdrant_url": self.database.qdrant_url,
        }

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
        def perform(database: EmbeatDatabase) -> None:
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
            packed = self._pack_track(payload, match_score=rank_score)
            packed["_artist_exact"] = artist_exact
            ranked.append(packed)

        if artist_variants and any(item["_artist_exact"] for item in ranked):
            ranked = [item for item in ranked if item["_artist_exact"]]
        for item in ranked:
            item.pop("_artist_exact", None)

        ranked.sort(key=lambda item: (item["match_score"], item["popularity"]), reverse=True)
        return ranked[:limit]

    @staticmethod
    def _artist_variants(value: str) -> list[str]:
        variants = EmbeatService._variants(value)
        lookup_key = normalize_artist_key(value)
        mapped_zh = ARTIST_ZH_ALIASES.get(lookup_key)
        mapped_en = ARTIST_EN_ALIASES.get(lookup_key)
        for item in (mapped_zh, mapped_en):
            if item and item not in variants:
                variants.append(item)
        return variants

    def _resolve_artist(self, database: EmbeatDatabase, artist_name: str) -> dict[str, Any]:
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

    def recommend_artist(self, artist_name: str, limit: int = 20) -> dict[str, Any]:
        artist_name = artist_name.strip()
        if not artist_name:
            raise ValueError("歌手名不能为空")

        started = time.perf_counter()

        def perform(database: EmbeatDatabase) -> tuple[dict[str, Any], Any, list[dict[str, Any]]]:
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
            zh_convert(resolved_name, locale="zh-cn") if zh_convert else resolved_name,
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
        def perform(database: EmbeatDatabase) -> tuple[Any, list[dict[str, Any]]]:
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
        def perform(database: EmbeatDatabase) -> None:
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

        def perform(database: EmbeatDatabase) -> list[Any]:
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
        def perform(database: EmbeatDatabase) -> list[Any]:
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

    @staticmethod
    def _pack_track(payload: dict[str, Any], match_score: float | None = None) -> dict[str, Any]:
        sources = payload.get("sources") or []
        if not isinstance(sources, list):
            sources = [str(sources)]
        track_name = str(payload.get("track_name") or "未知歌曲")
        artist_name = str(payload.get("artist_name") or "未知艺人")
        artist_name_zh = ARTIST_ZH_ALIASES.get(normalize_artist_key(artist_name), zh_convert(artist_name, locale="zh-cn") if zh_convert else artist_name)
        packed = {
            "track_id": str(payload.get("track_id") or ""),
            "track_name": track_name,
            "artist_name": artist_name,
            "track_name_zh": zh_convert(track_name, locale="zh-cn") if zh_convert else track_name,
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

