from __future__ import annotations

import copy
import datetime
import random
import re
import time
from collections.abc import Generator
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests

from app_cmd.config.BwsConfig import BwsConfig
from interface.common import _resolve_cookie_list
from task.buy_helpers import wait_until_start

BWS_RESERVE_BASE_URL = "https://api.bilibili.com/x/activity/bws/online/park/reserve"
BWS_MY_RESERVE_URL = "https://api.bilibili.com/x/activity/bws/online/park/myreserve"
BWS_NAV_URL = "https://api.bilibili.com/x/web-interface/nav"
BWS_OFFICIAL_URL = "https://bw.bilibili.com/"
BWS_EVENT_PAGE_TEMPLATE = "https://www.bilibili.com/blackboard/era/bws{event_year}-event.html"
BWS_REFERER = "https://www.bilibili.com/blackboard/era/bws2025-event.html?native.theme=1&night=0"
BWS_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/540.36 (KHTML, like Gecko)"
)
DEFAULT_BWS_YEAR = "202601"
DEFAULT_BWS_RESERVE_DATES = "20260710,20260711,20260712"
BWS_RESERVE_DATES_BY_YEAR = {
    "202501": "20250711,20250712,20250713",
    "202601": DEFAULT_BWS_RESERVE_DATES,
}
OFFICIAL_TERMINAL_CODES = {
    0: "预约成功",
    75574: "预约已被抢空",
    76647: "您的预约数已达上限",
}
OFFICIAL_RETRYABLE_CODES = {
    -702: "请求频率太快",
    412: "当前预约火爆，请稍后重试",
    76650: "操作频繁",
    76651: "当前预约火爆，请稍后重试",
    429: "请求被限流",
}
HISTORICAL_TERMINAL_CODES = {
    76674: "预约已达上限",
}
HISTORICAL_RETRYABLE_CODES = {
    75637: "尚未开放",
}
TERMINAL_CODES = {**HISTORICAL_TERMINAL_CODES, **OFFICIAL_TERMINAL_CODES}
RETRYABLE_CODES = {**HISTORICAL_RETRYABLE_CODES, **OFFICIAL_RETRYABLE_CODES}
UNKNOWN_CODE_MARKER = "!!! 【未知返回码】"


def _bws_code_meaning(code: int) -> str:
    return (
        OFFICIAL_TERMINAL_CODES.get(code)
        or OFFICIAL_RETRYABLE_CODES.get(code)
        or HISTORICAL_TERMINAL_CODES.get(code)
        or HISTORICAL_RETRYABLE_CODES.get(code)
        or "未知返回码（按可重试处理）"
    )


def _is_known_bws_code(code: int) -> bool:
    return code in TERMINAL_CODES or code in RETRYABLE_CODES


def _is_terminal_bws_code(code: int) -> bool:
    return code in TERMINAL_CODES


@dataclass(frozen=True)
class BwsOfficialSchedule:
    year: str
    reserve_dates: str
    event_year: int
    source_url: str


def _http_get_text(url: str, *, timeout: float = 10.0) -> str:
    response = requests.get(
        url,
        headers={"User-Agent": BWS_USER_AGENT},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.text


def _extract_js_urls(html: str, base_url: str) -> list[str]:
    urls: list[str] = []
    for src in re.findall(r"<script[^>]+src=[\"']([^\"']+\.js)[\"']", html):
        url = urljoin(base_url, src)
        if url not in urls:
            urls.append(url)
    return urls


def _extract_event_year(text: str) -> int | None:
    candidates = [int(item) for item in re.findall(r"\bBW\s*(20\d{2})\b", text, re.I)]
    if not candidates:
        candidates = [
            int(item) for item in re.findall(r"bws?(20\d{2})(?:[-_/]|event)", text, re.I)
        ]
    return max(candidates) if candidates else None


def _extract_act_days(text: str) -> list[str]:
    days: list[str] = []
    for match in re.finditer(r"ACT_DAYS\s*=\s*\[([^\]]+)\]", text):
        days.extend(re.findall(r"[\"'](20\d{6})[\"']", match.group(1)))
    if not days:
        days.extend(re.findall(r"[\"'](20\d{6})[\"']", text))
    unique: list[str] = []
    for day in days:
        if day not in unique:
            unique.append(day)
    return unique


def _extract_bws_year_param(text: str, event_year: int) -> str:
    candidates = re.findall(r"isPre\?\d{6}:(20\d{4})", text)
    candidates.extend(re.findall(r"\byear\s*[:=]\s*[\"']?(20\d{4})", text))
    prefix = str(event_year)
    for candidate in candidates:
        if candidate.startswith(prefix):
            return candidate
    return f"{event_year}01"


def _schedule_from_event_page(event_year: int) -> BwsOfficialSchedule:
    page_url = BWS_EVENT_PAGE_TEMPLATE.format(event_year=event_year)
    html = _http_get_text(page_url)
    combined = [html]
    for js_url in _extract_js_urls(html, page_url):
        try:
            combined.append(_http_get_text(js_url, timeout=20.0))
        except Exception:
            continue
    text = "\n".join(combined)
    days = _extract_act_days(text)
    if not days:
        raise RuntimeError("official BW event page did not expose ACT_DAYS")
    year = _extract_bws_year_param(text, event_year)
    return BwsOfficialSchedule(
        year=year,
        reserve_dates=",".join(days),
        event_year=event_year,
        source_url=page_url,
    )


def _schedule_from_homepage_dates(event_year: int, html: str) -> BwsOfficialSchedule:
    combined = [html]
    for js_url in _extract_js_urls(html, BWS_OFFICIAL_URL):
        try:
            combined.append(_http_get_text(js_url, timeout=20.0))
        except Exception:
            continue
    text = "\n".join(combined)
    raw_days = re.findall(r"date\s*:\s*[\"'](\d{1,2})\.(\d{1,2})[\"']", text)
    days: list[str] = []
    for month, day in raw_days:
        try:
            date_value = datetime.date(event_year, int(month), int(day))
        except ValueError:
            continue
        normalized = date_value.strftime("%Y%m%d")
        if normalized not in days:
            days.append(normalized)
    if not days:
        raise RuntimeError("official BW homepage did not expose display dates")
    return BwsOfficialSchedule(
        year=f"{event_year}01",
        reserve_dates=",".join(days),
        event_year=event_year,
        source_url=BWS_OFFICIAL_URL,
    )


@lru_cache(maxsize=8)
def discover_bws_official_schedule(
    year_hint: str = "",
) -> BwsOfficialSchedule:
    year_hint = str(year_hint or "").strip()
    event_year = None
    if len(year_hint) >= 4 and year_hint[:4].isdigit():
        event_year = int(year_hint[:4])
    if event_year is None:
        html = _http_get_text(BWS_OFFICIAL_URL)
        event_year = _extract_event_year(html)
        if event_year is None:
            raise RuntimeError("could not detect latest BW year from official site")
        try:
            return _schedule_from_event_page(event_year)
        except Exception:
            return _schedule_from_homepage_dates(event_year, html)
    return _schedule_from_event_page(event_year)


def default_bws_year(now: datetime.datetime | None = None) -> str:
    try:
        return discover_bws_official_schedule().year
    except Exception:
        return DEFAULT_BWS_YEAR


def infer_bws_reserve_dates(year: str = "") -> str:
    year_text = str(year or "").strip()
    if year_text:
        if year_text in BWS_RESERVE_DATES_BY_YEAR:
            return BWS_RESERVE_DATES_BY_YEAR[year_text]
        try:
            return discover_bws_official_schedule(year_text).reserve_dates
        except Exception:
            return DEFAULT_BWS_RESERVE_DATES
    try:
        return discover_bws_official_schedule().reserve_dates
    except Exception:
        return DEFAULT_BWS_RESERVE_DATES


def resolve_bws_reserve_dates(reserve_dates: str = "", year: str = "") -> str:
    dates = str(reserve_dates or "").replace("，", ",").strip()
    return dates or infer_bws_reserve_dates(year)


def _cookie_value(cookies: list[dict[str, Any]] | None, name: str) -> str | None:
    for cookie in cookies or []:
        if cookie.get("name") == name:
            value = cookie.get("value")
            return str(value) if value is not None else None
    return None


def _cookies_to_dict(cookies: list[dict[str, Any]] | None) -> dict[str, str]:
    cookie_dict: dict[str, str] = {}
    for cookie in cookies or []:
        name = cookie.get("name")
        value = cookie.get("value")
        if name and value is not None:
            cookie_dict[str(name)] = str(value)
    return cookie_dict


def _resolve_bws_cookies(
    *,
    cookies: list[dict[str, Any]] | dict[str, Any] | None = None,
    cookies_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    cookie_list = _resolve_cookie_list(cookies, cookies_path=cookies_path)
    if not cookie_list:
        raise RuntimeError("当前未登录，请先在本体完成登录")
    return cookie_list


def _response_json(response: requests.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except Exception as exc:
        raise RuntimeError(
            f"BW 乐园接口返回非 JSON 响应，HTTP 状态：{response.status_code}"
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeError("BW 乐园接口返回格式异常")
    return payload


def _raise_api_error(payload: dict[str, Any], *, action: str) -> None:
    code = int(payload.get("code", payload.get("errno", -1)) or 0)
    if code == 0:
        return
    message = payload.get("message", payload.get("msg", "未知错误"))
    raise RuntimeError(f"{action}失败: [{code}] {message}")


class BwsApiClient:
    """Starsbon_bws_ticket style BW park API client."""

    def __init__(self, cookies: list[dict[str, Any]], *, timeout: float = 10.0):
        self.cookies = cookies
        self.cookie_dict = _cookies_to_dict(cookies)
        self.csrf_token = self.cookie_dict.get("bili_jct", "")
        if not self.csrf_token:
            raise RuntimeError("Cookie 中缺少 bili_jct，无法调用 BW 乐园预约接口")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": BWS_USER_AGENT,
                "accept": "*/*",
                "accept-language": "zh-CN,zh;q=0.9",
                "referer": BWS_REFERER,
            }
        )

    def get_username(self) -> str:
        try:
            response = self.session.get(
                BWS_NAV_URL,
                cookies=self.cookie_dict,
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = _response_json(response)
            data = payload.get("data")
            if payload.get("code") == 0 and isinstance(data, dict):
                username = str(data.get("uname") or "").strip()
                if username and data.get("isLogin"):
                    return username
        except Exception:
            pass
        return "未登录"

    def get_reservation_info(
        self,
        *,
        reserve_dates: str = DEFAULT_BWS_RESERVE_DATES,
        reserve_type: int = -1,
        year: str = DEFAULT_BWS_YEAR,
    ) -> dict[str, Any]:
        response = self.session.get(
            f"{BWS_RESERVE_BASE_URL}/info",
            params={
                "csrf": self.csrf_token,
                "reserve_date": reserve_dates,
                "reserve_type": int(reserve_type),
                "year": year or DEFAULT_BWS_YEAR,
            },
            cookies=self.cookie_dict,
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = _response_json(response)
        _raise_api_error(payload, action="获取 BW 乐园预约信息")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise RuntimeError("BW 乐园预约信息为空")
        return data

    def get_my_reservations(self, *, year: str = DEFAULT_BWS_YEAR) -> dict[str, Any]:
        response = self.session.get(
            BWS_MY_RESERVE_URL,
            params={
                "csrf": self.csrf_token,
                "year": year or DEFAULT_BWS_YEAR,
            },
            cookies=self.cookie_dict,
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = _response_json(response)
        _raise_api_error(payload, action="获取我的 BW 乐园预约")
        data = payload.get("data")
        return data if isinstance(data, dict) else {}

    def make_reservation(
        self,
        *,
        ticket_no: str,
        reserve_id: int,
        year: str = DEFAULT_BWS_YEAR,
    ) -> dict[str, Any]:
        response = self.session.post(
            f"{BWS_RESERVE_BASE_URL}/do",
            data={
                "ticket_no": ticket_no,
                "csrf": self.csrf_token,
                "inter_reserve_id": int(reserve_id),
                "year": year or DEFAULT_BWS_YEAR,
                "ts": int(time.time() * 1000),
                "_": random.randint(10000, 99999),
            },
            cookies=self.cookie_dict,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return _response_json(response)


def _make_bws_client(
    *,
    cookies: list[dict[str, Any]] | dict[str, Any] | None = None,
    cookies_path: str | Path | None = None,
) -> BwsApiClient:
    cookie_list = _resolve_bws_cookies(cookies=cookies, cookies_path=cookies_path)
    return BwsApiClient(cookie_list)


def fetch_bws_reserve_info(
    *,
    reserve_dates: str = "",
    reserve_type: int = -1,
    year: str = "",
    cookies: list[dict[str, Any]] | dict[str, Any] | None = None,
    cookies_path: str | Path | None = None,
    request: BwsApiClient | None = None,
) -> dict[str, Any]:
    year = year or default_bws_year()
    reserve_dates = resolve_bws_reserve_dates(reserve_dates, year)
    client = request or _make_bws_client(cookies=cookies, cookies_path=cookies_path)
    return client.get_reservation_info(
        reserve_dates=reserve_dates,
        reserve_type=reserve_type,
        year=year,
    )


def fetch_bws_my_reservations(
    *,
    year: str = "",
    cookies: list[dict[str, Any]] | dict[str, Any] | None = None,
    cookies_path: str | Path | None = None,
    request: BwsApiClient | None = None,
) -> dict[str, Any]:
    client = request or _make_bws_client(cookies=cookies, cookies_path=cookies_path)
    return client.get_my_reservations(year=year or default_bws_year())


def _normalize_date(value: str) -> str:
    return str(value or "").replace("-", "").strip()


def _iter_dates_from_info(info: dict[str, Any]) -> list[str]:
    dates: list[str] = []
    for key in ("user_reserve_info", "user_ticket_info", "reserve_list"):
        value = info.get(key)
        if isinstance(value, dict):
            for date in value.keys():
                normalized = _normalize_date(date)
                if normalized and normalized not in dates:
                    dates.append(normalized)
    return dates


def _ticket_days(info: dict[str, Any]) -> list[str]:
    user_reserve_info = info.get("user_reserve_info")
    if isinstance(user_reserve_info, dict) and user_reserve_info:
        return [_normalize_date(date) for date in user_reserve_info.keys()]
    user_ticket_info = info.get("user_ticket_info")
    if isinstance(user_ticket_info, dict) and user_ticket_info:
        return [_normalize_date(date) for date in user_ticket_info.keys()]
    return _iter_dates_from_info(info)


def _find_activity(info: dict[str, Any], reserve_id: int) -> tuple[str, dict[str, Any]]:
    reserve_list = info.get("reserve_list")
    if not isinstance(reserve_list, dict):
        raise RuntimeError("BW 乐园预约信息缺少 reserve_list")
    ticket_dates = _ticket_days(info)
    searched_dates: set[str] = set()
    for date in ticket_dates:
        searched_dates.add(date)
        activities = reserve_list.get(date, [])
        if not isinstance(activities, list):
            continue
        for activity in activities:
            if not isinstance(activity, dict):
                continue
            if int(activity.get("reserve_id", 0) or 0) == int(reserve_id):
                return date, copy.deepcopy(activity)
    for date, activities in reserve_list.items():
        normalized_date = _normalize_date(date)
        if normalized_date in searched_dates or not isinstance(activities, list):
            continue
        for activity in activities:
            if not isinstance(activity, dict):
                continue
            if int(activity.get("reserve_id", 0) or 0) == int(reserve_id):
                return normalized_date, copy.deepcopy(activity)
    raise RuntimeError(f"未找到预约项目 reserve_id={reserve_id}")


def _activity_date(activity: dict[str, Any], fallback: str) -> str:
    try:
        start_time = int(activity.get("act_begin_time"))
    except (TypeError, ValueError):
        return fallback
    return datetime.datetime.fromtimestamp(start_time).strftime("%Y%m%d")


def _is_vip_ticket(activity: dict[str, Any]) -> bool:
    return int(activity.get("is_vip_ticket") or 0) == 1


def _is_user_vip_for_date(info: dict[str, Any], date: str) -> bool:
    ticket_info_map = info.get("user_ticket_info")
    if not isinstance(ticket_info_map, dict):
        return False
    ticket_info = ticket_info_map.get(_normalize_date(date))
    if not isinstance(ticket_info, dict):
        return False
    return bool(ticket_info.get("is_vip"))


def effective_bws_reserve_begin_time(
    activity: dict[str, Any],
    ticket_info: dict[str, Any] | None = None,
) -> int:
    try:
        reserve_time = int(activity.get("reserve_begin_time") or 0)
    except (TypeError, ValueError):
        reserve_time = 0
    if not _is_vip_ticket(activity):
        return reserve_time
    if isinstance(ticket_info, dict) and ticket_info.get("is_vip"):
        return reserve_time
    next_reserve = activity.get("next_reserve")
    if isinstance(next_reserve, dict):
        try:
            next_reserve_time = int(next_reserve.get("reserve_begin_time") or 0)
        except (TypeError, ValueError):
            next_reserve_time = 0
        if next_reserve_time > 0:
            return next_reserve_time
    return reserve_time


def _reserved_activity_ids(my_reservations: dict[str, Any] | None) -> set[int]:
    reserve_list = (
        my_reservations.get("reserve_list")
        if isinstance(my_reservations, dict)
        else None
    )
    if not isinstance(reserve_list, dict):
        return set()
    ids: set[int] = set()
    for activities in reserve_list.values():
        if not isinstance(activities, list):
            continue
        for activity in activities:
            if not isinstance(activity, dict):
                continue
            try:
                ids.add(int(activity.get("reserve_id")))
            except (TypeError, ValueError):
                continue
    return ids


def verify_bws_ticket_activation(
    info: dict[str, Any],
    *,
    reserve_id: int,
    reserve_date: str = "",
) -> dict[str, Any]:
    activity_day, activity = _find_activity(info, reserve_id)
    target_date = _normalize_date(reserve_date) or _activity_date(activity, activity_day)
    ticket_info_map = info.get("user_ticket_info")
    if not isinstance(ticket_info_map, dict):
        raise RuntimeError("账号未返回 BW 门票信息，请确认已登录并已激活预约日期门票")
    ticket_info = ticket_info_map.get(target_date)
    if not isinstance(ticket_info, dict):
        available = ", ".join(_ticket_days(info)) or "无"
        raise RuntimeError(
            "当前账号没有激活目标预约日期的 BW 门票: {0}。可用日期: {1}".format(
                target_date,
                available,
            )
        )
    ticket_no = str(ticket_info.get("ticket") or "").strip()
    if not ticket_no:
        raise RuntimeError(f"目标日期 {target_date} 的 BW 门票未返回有效电子票号")
    return {
        "date": target_date,
        "ticket_no": ticket_no,
        "ticket_info": copy.deepcopy(ticket_info),
        "activity": activity,
    }


def submit_bws_reservation(
    *,
    reserve_id: int,
    ticket_no: str,
    request: BwsApiClient,
    year: str = DEFAULT_BWS_YEAR,
) -> dict[str, Any]:
    return request.make_reservation(ticket_no=ticket_no, reserve_id=reserve_id, year=year)


def _activity_title(activity: dict[str, Any]) -> str:
    title = activity.get("act_title") or activity.get("title") or ""
    return str(title).replace("\n", "").strip() or "未知项目"


def _format_timestamp(value: Any) -> str:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return "-"
    return datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def _configured_start_time(config: BwsConfig, activity: dict[str, Any]) -> str:
    if config.time_start.strip():
        return config.time_start.strip()
    reserve_begin_time = activity.get("effective_reserve_begin_time")
    if reserve_begin_time is None:
        reserve_begin_time = activity.get("reserve_begin_time")
    try:
        timestamp = int(reserve_begin_time) + (int(config.start_delay_ms) / 1000.0)
    except (TypeError, ValueError):
        return ""
    return datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def bws_reserve_stream(config: BwsConfig) -> Generator[str, None, None]:
    if int(config.reserve_id or 0) <= 0:
        raise ValueError("reserve_id is required")
    year = config.year or default_bws_year()
    reserve_dates = resolve_bws_reserve_dates(
        config.reserve_dates or config.reserve_date,
        year,
    )
    client = _make_bws_client(cookies_path=config.cookies_path or None)
    yield f"当前账号: {client.get_username()}"

    info = client.get_reservation_info(
        reserve_dates=reserve_dates,
        reserve_type=config.reserve_type,
        year=year,
    )
    try:
        reserved_ids = _reserved_activity_ids(client.get_my_reservations(year=year))
    except Exception:
        reserved_ids = set()
    if int(config.reserve_id) in reserved_ids:
        yield f"该项目 ID={config.reserve_id} 已在当前账号的预约列表中，停止重复预约"
        return
    verified = verify_bws_ticket_activation(
        info,
        reserve_id=config.reserve_id,
        reserve_date=config.reserve_date,
    )
    activity = verified["activity"]
    ticket_info = verified["ticket_info"]
    ticket_no = verified["ticket_no"]
    target_date = verified["date"]
    activity["effective_reserve_begin_time"] = effective_bws_reserve_begin_time(
        activity,
        ticket_info,
    )
    title = _activity_title(activity)
    yield "验权通过: 日期 {0} 已激活门票 {1}".format(target_date, ticket_no)
    if config.show_detail:
        yield "目标项目: {0} | ID={1} | 预约开始={2}".format(
            title,
            config.reserve_id,
            _format_timestamp(activity.get("effective_reserve_begin_time")),
        )
        if _is_vip_ticket(activity):
            vip_message = (
                "VIP 优先购项目，当前票种为 VIP，使用 VIP 预约时间"
                if ticket_info.get("is_vip")
                else "VIP 优先购项目，当前票种非 VIP，使用普通预约时间"
            )
            yield vip_message
        yield "门票信息: {0} - {1}".format(
            ticket_info.get("screen_name", ""),
            ticket_info.get("sku_name", ""),
        )

    start_time = _configured_start_time(config, activity)
    if start_time:
        for wait_state in wait_until_start(start_time):
            message = wait_state.get("message")
            countdown = wait_state.get("countdown")
            if message:
                yield str(message)
            elif countdown:
                yield f"距离开始还有 {countdown}"

    retry_limit = max(0, int(config.retry_limit or 0))
    interval_seconds = max(0, int(config.interval or 0)) / 1000.0
    attempt = 0
    while retry_limit <= 0 or attempt < retry_limit:
        attempt += 1
        result = client.make_reservation(
            reserve_id=config.reserve_id,
            ticket_no=ticket_no,
            year=year,
        )
        code = int(result.get("code", result.get("errno", -1)) or 0)
        message = str(result.get("message", result.get("msg", "")) or "")
        if not _is_known_bws_code(code):
            yield "{0} 检测到未标记 BW 返回码: [{1}]，已自动按可重试处理。完整返回: {2}".format(
                UNKNOWN_CODE_MARKER,
                code,
                result,
            )
        yield "第 {0} 次预约结果: [{1}] {2} | {3}".format(
            attempt,
            code,
            _bws_code_meaning(code),
            message or result,
        )
        if _is_terminal_bws_code(code):
            return
        if code == 412:
            time.sleep(max(interval_seconds, 180.0))
            continue
        if interval_seconds > 0:
            time.sleep(interval_seconds)
    yield f"已达到最大重试次数 {retry_limit}，预约未成功"


def run_bws_reserve_sync(config: BwsConfig | dict[str, Any]) -> dict[str, Any]:
    if isinstance(config, dict):
        config = BwsConfig.from_mapping(config, source_name="runtime")
    logs: list[str] = []
    status = "completed"
    try:
        for message in bws_reserve_stream(config):
            logs.append(message)
            if "预约成功" in message:
                status = "succeeded"
        return {"ok": status == "succeeded", "status": status, "logs": logs}
    except Exception as exc:
        logs.append(str(exc))
        return {"ok": False, "status": "failed", "error": str(exc), "logs": logs}


def get_bws_reserve_context(
    *,
    reserve_dates: str = "",
    reserve_type: int = -1,
    year: str = "",
    cookies: list[dict[str, Any]] | dict[str, Any] | None = None,
    cookies_path: str | Path | None = None,
) -> dict[str, Any]:
    year = year or default_bws_year()
    reserve_dates = resolve_bws_reserve_dates(reserve_dates, year)
    client = _make_bws_client(cookies=cookies, cookies_path=cookies_path)
    info = client.get_reservation_info(
        reserve_dates=reserve_dates,
        reserve_type=reserve_type,
        year=year,
    )
    try:
        my_reservations = client.get_my_reservations(year=year)
    except Exception:
        my_reservations = {}
    return {
        "username": client.get_username(),
        "reserve_dates": reserve_dates,
        "year": year,
        "reserve_info": info,
        "my_reservations": my_reservations,
        "csrf_present": bool(_cookie_value(client.cookies, "bili_jct")),
    }
