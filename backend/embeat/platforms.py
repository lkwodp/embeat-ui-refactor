"""Platform credential, configuration and phone-login mixin."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse

from aliases import ARTIST_EN_ALIASES, ARTIST_ZH_ALIASES, METADATA_RESOLVER
from config import CONFIG
from kugou_client import KugouClient
from netease_client import NetEaseClient

APP_DIR = Path(__file__).resolve().parent


class PlatformsMixin:
    def _credential_client(self, user_id: int, platform: str) -> Any:
        values = self.app_db.get_credential(user_id, platform)
        if not values or not values.get("cookie"):
            if platform == "kugou":
                return KugouClient(APP_DIR / "data" / ".disabled_credentials.json", alias_map={**ARTIST_ZH_ALIASES, **ARTIST_EN_ALIASES}, to_simplified=self._to_simplified, proxy_url=CONFIG.proxy_url, metadata_resolver=METADATA_RESOLVER, persist_credentials=False)
            return NetEaseClient(metadata_resolver=METADATA_RESOLVER)
        if platform == "kugou":
            client = KugouClient(APP_DIR / "data" / ".disabled_credentials.json", alias_map={**ARTIST_ZH_ALIASES, **ARTIST_EN_ALIASES}, to_simplified=self._to_simplified, proxy_url=values.get("proxy_url") or CONFIG.proxy_url, metadata_resolver=METADATA_RESOLVER, persist_credentials=False)
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
        client = KugouClient(APP_DIR / "data" / ".disabled_credentials.json", alias_map={**ARTIST_ZH_ALIASES, **ARTIST_EN_ALIASES}, to_simplified=self._to_simplified, proxy_url=proxy_url, metadata_resolver=METADATA_RESOLVER, persist_credentials=False) if platform == "kugou" else NetEaseClient(metadata_resolver=METADATA_RESOLVER)
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