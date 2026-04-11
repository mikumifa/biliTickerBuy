from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests

REQUIRED_FIELDS = (
    "detail",
    "count",
    "screen_id",
    "project_id",
    "sku_id",
    "pay_money",
    "buyer_info",
    "buyer",
    "tel",
    "deliver_info",
    "cookies",
)
BUYER_REQUIRED_FIELDS = ("name", "personal_id")
DELIVER_REQUIRED_FIELDS = ("name", "tel", "addr_id", "addr")
COOKIE_REQUIRED_FIELDS = ("name", "value")
SALES_FLAG_NUMBER_MAP = {
    1: "不可售",
    2: "预售",
    3: "停售",
    4: "售罄",
    5: "不可用",
    6: "库存紧张",
    8: "暂时售罄",
    9: "不在白名单",
    101: "未开始",
    102: "已结束",
    103: "未完成",
    105: "下架",
    106: "已取消",
}


def _load_json_file(path: str | Path) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _read_tinydb_value(path: str | Path, key: str) -> Any:
    target = Path(path)
    if not target.exists():
        return None
    try:
        raw = _load_json_file(target)
    except Exception:
        return None
    if isinstance(raw, dict):
        default_group = raw.get("_default")
        if isinstance(default_group, dict):
            for item in default_group.values():
                if isinstance(item, dict) and item.get("key") == key:
                    return item.get("value")
        if raw.get("key") == key:
            return raw.get("value")
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and item.get("key") == key:
                return item.get("value")
    return None


def _cookie_store_path(cookies_path: str | Path | None) -> str | None:
    if cookies_path is not None:
        return str(Path(cookies_path))

    package_root = Path(__file__).resolve().parents[1]
    config_path = package_root / "config.json"
    configured = _read_tinydb_value(config_path, "cookies_path")
    if configured:
        return str(Path(configured))
    return str(package_root / "cookies.json")


def _coerce_cookie_store(raw: Any) -> list[dict[str, Any]] | None:
    if raw is None:
        return None
    if isinstance(raw, list):
        return copy.deepcopy(raw)
    if isinstance(raw, dict):
        if isinstance(raw.get("cookie"), list):
            return copy.deepcopy(raw["cookie"])
        default_group = raw.get("_default")
        if isinstance(default_group, dict):
            for item in default_group.values():
                if isinstance(item, dict) and item.get("key") == "cookie":
                    value = item.get("value")
                    if isinstance(value, list):
                        return copy.deepcopy(value)
    return None


def _resolve_cookie_list(
    cookies: list[dict[str, Any]] | dict[str, Any] | None = None,
    *,
    cookies_path: str | Path | None = None,
) -> list[dict[str, Any]] | None:
    if cookies is not None:
        return _coerce_cookie_store(cookies)

    store_path = _cookie_store_path(cookies_path)
    if not store_path:
        return None
    try:
        return _coerce_cookie_store(_load_json_file(store_path))
    except Exception:
        return None


def _cookies_to_header(cookies: list[dict[str, Any]] | None) -> str:
    if not cookies:
        return ""
    parts: list[str] = []
    for cookie in cookies:
        name = cookie.get("name")
        value = cookie.get("value")
        if name and value is not None:
            parts.append("{0}={1}".format(name, value))
    return "; ".join(parts)


def _fetch_username_silently(
    cookies: list[dict[str, Any]] | None,
    *,
    timeout: float = 10.0,
) -> str:
    if not cookies:
        return "Not login"
    headers = {
        "accept": "*/*",
        "accept-language": "zh-CN,zh;q=0.9",
        "referer": "https://show.bilibili.com/",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        ),
        "cookie": _cookies_to_header(cookies),
    }
    try:
        response = requests.get(
            "https://api.bilibili.com/x/web-interface/nav",
            headers=headers,
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data") or {}
        username = data.get("uname")
        if isinstance(username, str) and username.strip():
            return username.strip()
    except Exception:
        return "Not login"
    return "Not login"


def _deepcopy_dict(data: Any) -> dict[str, Any]:
    if isinstance(data, dict):
        return copy.deepcopy(data)
    raise TypeError("config must be a dict or a json file path")


def _load_config(config_or_path: str | Path | dict[str, Any]) -> dict[str, Any]:
    if isinstance(config_or_path, (str, Path)):
        return _deepcopy_dict(_load_json_file(config_or_path))
    return _deepcopy_dict(config_or_path)


def _extract_project_id(project_input: str | int) -> int:
    if isinstance(project_input, int):
        return project_input

    text = str(project_input).strip()
    if not text:
        raise ValueError("project_input is empty")
    if text.isdigit():
        return int(text)

    parsed = urlparse(text)
    query = parse_qs(parsed.query)
    project_ids = query.get("id", [])
    if project_ids and project_ids[0].isdigit():
        return int(project_ids[0])
    raise ValueError("could not extract project id from input")


def _format_sale_status(ticket: dict[str, Any]) -> str:
    sale_flag_number = ticket.get("sale_flag_number")
    if sale_flag_number in SALES_FLAG_NUMBER_MAP:
        return SALES_FLAG_NUMBER_MAP[sale_flag_number]
    if "clickable" in ticket:
        return "可购买" if ticket.get("clickable") else "不可购买"
    return "未知状态"


def _make_request(
    *,
    cookies: list[dict[str, Any]] | dict[str, Any] | None = None,
    cookies_path: str | Path | None = None,
) -> Any:
    from util.BiliRequest import BiliRequest

    return BiliRequest(
        cookies=cookies,
        cookies_config_path=_cookie_store_path(cookies_path),
    )
