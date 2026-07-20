"""Mobile ticket-page availability gate used before creating an order."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlparse

from requests import RequestException


MOBILE_TICKET_PAGE_URL = (
    "https://mall.bilibili.com/neul-next/ticket-renovation/detail.html?id={project_id}"
)
MOBILE_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
    "Mobile/15E148 Safari/604.1"
)
BUY_BUTTON_TEXTS = ("立即购票", "立即购买")
TICKET_PAGE_STATE_URL = "https://mall.bilibili.com/mall-search-items/items_detail/info"


@dataclass(frozen=True, slots=True)
class TicketPageAvailability:
    url: str
    ready: bool
    status_code: int | None = None
    matched_text: str | None = None
    error: str | None = None

    @property
    def message(self) -> str:
        if self.ready:
            return "购票页校验：检测到「{0}」，允许开始抢票。".format(
                self.matched_text or "立即购票"
            )
        if self.error:
            return "购票页校验请求失败，继续等待：{0}".format(self.error)
        return "购票页校验：尚未检测到「立即购票」。"


def mobile_ticket_page_url(project_id: int | str) -> str:
    """Build the canonical mobile ticket page URL for a project."""

    try:
        normalized_id = int(project_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("抢票链接缺少有效的活动 id") from exc
    if normalized_id <= 0:
        raise ValueError("抢票链接缺少有效的活动 id")
    return MOBILE_TICKET_PAGE_URL.format(project_id=normalized_id)


def normalize_mobile_ticket_page_url(value: str) -> str:
    """Convert Bilibili desktop/mobile detail URLs to the mobile ticket page."""

    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("抢票链接必须是完整的 http(s) 活动链接")
    if not parsed.hostname or not parsed.hostname.lower().endswith("bilibili.com"):
        raise ValueError("抢票链接必须属于 bilibili.com")

    query = parse_qs(parsed.query)
    project_id = (query.get("id") or query.get("project_id") or [""])[0]
    return mobile_ticket_page_url(project_id)


def _project_id_from_mobile_ticket_page_url(page_url: str) -> int:
    query = parse_qs(urlparse(page_url).query)
    return int((query.get("id") or [""])[0])


def _ticket_page_state_is_ready(
    session: Any,
    *,
    page_url: str,
    headers: dict[str, str],
    cookies: dict[str, str],
    timeout_seconds: float,
) -> TicketPageAvailability | None:
    """Read the official state payload used by the mobile ticket page UI."""

    if not hasattr(session, "post"):
        return None
    try:
        project_id = _project_id_from_mobile_ticket_page_url(page_url)
        state_headers = {
            "accept": "application/json, text/plain, */*",
            "origin": "https://mall.bilibili.com",
            "referer": page_url,
            "user-agent": MOBILE_USER_AGENT,
        }
        response = session.post(
            TICKET_PAGE_STATE_URL,
            json={"itemsId": project_id, "itemsDetailPageType": 3},
            headers=state_headers,
            cookies=cookies,
            timeout=max(0.5, float(timeout_seconds)),
        )
        response.raise_for_status()
        payload = response.json()
    except (RequestException, ValueError, TypeError) as exc:
        return TicketPageAvailability(
            url=page_url,
            ready=False,
            error="购票页状态请求失败：{0}: {1}".format(exc.__class__.__name__, exc),
        )

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        code = payload.get("code", payload.get("errno", "unknown")) if isinstance(payload, dict) else "unknown"
        message = payload.get("message", payload.get("msg", "")) if isinstance(payload, dict) else ""
        return TicketPageAvailability(
            url=page_url,
            ready=False,
            error="购票页状态响应缺少 data（code={0}, message={1}）".format(
                code,
                message or "无",
            ),
        )
    # `canClick` is the official detail-page state that drives the enabled
    # immediate-buy control seen in the mobile UI.
    if data.get("canClick") is True:
        return TicketPageAvailability(
            url=page_url,
            ready=True,
            status_code=response.status_code,
            matched_text="立即购票（页面状态）",
        )
    return TicketPageAvailability(
        url=page_url,
        ready=False,
        status_code=response.status_code,
    )


def check_ticket_page_availability(
    request: Any,
    page_url: str,
    *,
    timeout_seconds: float = 4.0,
) -> TicketPageAvailability:
    """Fetch the rendered mobile page and look for its immediate-buy button text.

    This intentionally uses the existing request session directly: ``BiliRequest``
    expects JSON responses, while this endpoint returns HTML.  Reusing its session
    retains the configured proxy and the ticket account's cookies.
    """

    try:
        normalized_url = normalize_mobile_ticket_page_url(page_url)
    except ValueError as exc:
        return TicketPageAvailability(
            url=str(page_url or ""), ready=False, error=str(exc)
        )

    session = getattr(request, "session", None)
    if session is None or not hasattr(session, "get"):
        return TicketPageAvailability(
            url=normalized_url,
            ready=False,
            error="当前请求会话不可用",
        )

    # Do not inherit BiliRequest's desktop browser fingerprint here.  Mixing
    # desktop `sec-ch-*` headers with a mobile User-Agent can make the mall
    # detail API return `data: null` even when the mobile UI shows the button.
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "accept-language": "zh-CN,zh;q=0.9",
        "referer": normalized_url,
        "user-agent": MOBILE_USER_AGENT,
    }
    cookies: dict[str, str] = {}
    cookie_manager = getattr(request, "cookieManager", None)
    if cookie_manager is not None:
        for cookie in cookie_manager.get_cookies(force=True) or []:
            name = cookie.get("name")
            value = cookie.get("value")
            if name and value is not None:
                cookies[str(name)] = str(value)

    try:
        response = session.get(
            normalized_url,
            headers=headers,
            cookies=cookies,
            timeout=max(0.5, float(timeout_seconds)),
        )
        response.raise_for_status()
    except (RequestException, ValueError) as exc:
        return TicketPageAvailability(
            url=normalized_url,
            ready=False,
            error="{0}: {1}".format(exc.__class__.__name__, exc),
        )

    body = response.text or ""
    for text in BUY_BUTTON_TEXTS:
        if text in body:
            return TicketPageAvailability(
                url=normalized_url,
                ready=True,
                status_code=response.status_code,
                matched_text=text,
            )
    page_state = _ticket_page_state_is_ready(
        session,
        page_url=normalized_url,
        headers=headers,
        cookies=cookies,
        timeout_seconds=timeout_seconds,
    )
    if page_state is not None:
        return page_state
    return TicketPageAvailability(
        url=normalized_url,
        ready=False,
        status_code=response.status_code,
    )
