from __future__ import annotations

from pathlib import Path
from urllib.parse import quote, urlencode

import requests

from .auth import get_login_state
from .common import _cookies_to_header, _resolve_cookie_list


def search_tickets(
    keyword: str,
    *,
    page: int = 1,
    pagesize: int = 16,
    platform: str = "web",
    cookies: list[dict[str, object]] | dict[str, object] | None = None,
    cookies_path: str | Path | None = None,
) -> dict[str, object]:
    if not keyword or not keyword.strip():
        raise ValueError("keyword is required")

    login_state = get_login_state(cookies=cookies, cookies_path=cookies_path)
    if not login_state.get("logged_in"):
        return {
            "ok": False,
            "keyword": keyword.strip(),
            "page": page,
            "pagesize": pagesize,
            "total": 0,
            "results": [],
            "requires_login": True,
            "error": "当前未登录，请先登录后再搜索",
            "next_action": "prompt_login",
            "username": login_state.get("username", "未登录"),
            "cookies_path": login_state.get("cookies_path"),
        }

    active_cookies = _resolve_cookie_list(cookies, cookies_path=cookies_path)
    params = urlencode(
        {
            "version": 134,
            "keyword": keyword.strip(),
            "pagesize": pagesize,
            "page": page,
            "platform": platform,
        }
    )
    headers = {
        "accept": "*/*",
        "accept-language": "zh-CN,zh;q=0.9",
        "referer": "https://show.bilibili.com/platform/search.html?searchValue={0}".format(
            quote(keyword.strip(), safe="")
        ),
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/146.0.0.0 Safari/537.36"
        ),
        "cookie": _cookies_to_header(active_cookies),
    }
    response = requests.get(
        "https://show.bilibili.com/api/ticket/search/list?{0}".format(params),
        headers=headers,
        timeout=10,
    ).json()
    errno = response.get("errno", response.get("code"))
    if errno != 0:
        raise RuntimeError(
            response.get("msg", response.get("message", "failed to search tickets"))
        )

    data = response.get("data") or {}
    results = data.get("result") or []
    return {
        "ok": True,
        "keyword": keyword.strip(),
        "page": page,
        "pagesize": pagesize,
        "total": data.get("total", len(results)),
        "results": results,
        "requires_login": False,
        "username": login_state.get("username", "未登录"),
        "cookies_path": login_state.get("cookies_path"),
    }


def format_ticket_search_results_text(
    search_result: dict[str, object],
    *,
    limit: int = 10,
) -> str:
    keyword = search_result.get("keyword", "")
    if search_result.get("requires_login"):
        return "搜索“{0}”前需要先登录当前会员购账号。你先完成登录，我再继续帮你搜。".format(
            keyword
        )

    results = list(search_result.get("results") or [])[:limit]
    if not results:
        return "没有找到和“{0}”相关的票务结果。".format(keyword)

    lines = ["搜索结果：{0}".format(keyword), ""]
    for idx, item in enumerate(results, start=1):
        price_low = item.get("price_low")
        price_high = item.get("price_high")
        if isinstance(price_low, int) and isinstance(price_high, int):
            if price_low == price_high:
                price_text = "￥{0}".format(price_low / 100)
            else:
                price_text = "￥{0} - ￥{1}".format(price_low / 100, price_high / 100)
        else:
            price_text = "价格未知"

        lines.extend(
            [
                "{0}. {1}".format(idx, item.get("title") or item.get("project_name") or "未知活动"),
                "   城市：{0}  场地：{1}".format(
                    item.get("city", "未知城市"),
                    item.get("venue_name", "未知场地"),
                ),
                "   时间：{0}".format(item.get("tlabel") or item.get("start_time", "未知时间")),
                "   价格：{0}  状态：{1}".format(price_text, item.get("sale_flag", "未知状态")),
                "   链接：{0}".format(item.get("url", "")),
                "",
            ]
        )
    return "\n".join(lines).rstrip()
