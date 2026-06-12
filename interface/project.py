from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from .common import _extract_project_id, _format_sale_status, _make_request

NEW_PROJECT_DETAIL_URL = "https://mall.bilibili.com/mall-search-items/items_detail/info"
OLD_PROJECT_DETAIL_URL = "https://show.bilibili.com/api/ticket/project/getV2"


def _normalize_new_project_payload(
    new_payload: dict[str, Any], project_id: int
) -> dict[str, Any]:
    normalized_project_id = int(
        new_payload.get("projectId") or new_payload.get("itemsId") or project_id
    )
    raw_screens = new_payload.get("screenList")
    if not isinstance(raw_screens, list) or not raw_screens:
        raise RuntimeError("new project response missing screenList")

    screens = copy.deepcopy(raw_screens)
    screen_start_times = [
        int(screen.get("start_time", 0))
        for screen in screens
        if isinstance(screen, dict) and str(screen.get("start_time", 0)).isdigit()
    ]
    venue_info = copy.deepcopy(new_payload.get("skuVenueInfo") or {})
    if not isinstance(venue_info, dict):
        venue_info = {}
    venue_info.setdefault("name", "")
    venue_info.setdefault("address_detail", "")
    sales_dates = new_payload.get("salesDates")
    end_time = int(
        new_payload.get("endTime")
        or (max(screen_start_times) if screen_start_times else 0)
    )

    for screen in screens:
        if not isinstance(screen, dict):
            continue
        screen.setdefault("project_id", normalized_project_id)
        screen.setdefault("express_fee", 0)
        for ticket in screen.get("ticket_list", []):
            if not isinstance(ticket, dict):
                continue
            ticket.setdefault("project_id", normalized_project_id)
            ticket.setdefault("screen_name", screen.get("name", ""))
            sale_flag = ticket.get("sale_flag") or {}
            if isinstance(sale_flag, dict):
                ticket.setdefault("sale_flag_number", sale_flag.get("number"))

    return {
        "id": normalized_project_id,
        "name": new_payload.get("projectName", ""),
        "hotProject": bool(new_payload.get("hotProject", False)),
        "has_eticket": not any(
            int(screen.get("express_fee", 0) or 0) > 0
            for screen in screens
            if isinstance(screen, dict)
        ),
        "screen_list": screens,
        "sales_dates": copy.deepcopy(
            sales_dates if isinstance(sales_dates, list) else []
        ),
        "venue_info": venue_info,
        "start_time": min(screen_start_times) if screen_start_times else 0,
        "end_time": end_time,
    }


def _fetch_project_payload_new(*, request: Any, project_id: int) -> dict[str, Any]:
    request_headers = getattr(request, "headers", None)
    old_headers = {}
    if isinstance(request_headers, dict):
        old_headers = {
            "origin": request_headers.get("origin"),
            "referer": request_headers.get("referer"),
        }
        request_headers.update(
            {
                "origin": "https://mall.bilibili.com",
                "referer": (
                    "https://mall.bilibili.com/neul-next/ticket-renovation/detail.html"
                    "?id={0}&from=pc_ticketlist&noTitleBar=1".format(project_id)
                ),
            }
        )
    try:
        response = request.post(
            url=NEW_PROJECT_DETAIL_URL,
            data={
                "itemsId": project_id,
                "itemsDetailPageType": 3,
            },
            isJson=True,
        ).json()
    finally:
        if isinstance(request_headers, dict):
            for key, value in old_headers.items():
                if value is None:
                    request_headers.pop(key, None)
                else:
                    request_headers[key] = value

    errno = response.get("code", response.get("errno"))
    if response.get("success") is False or errno not in (None, 0):
        raise RuntimeError(
            response.get("message", response.get("msg", "failed to fetch new project"))
        )
    data = response.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("new project response data is empty")
    return _normalize_new_project_payload(data, project_id)


def _fetch_project_payload_old(*, request: Any, project_id: int) -> dict[str, Any]:
    response = request.get(
        url=(
            "{0}?version=134&id={1}&project_id={1}".format(
                OLD_PROJECT_DETAIL_URL,
                project_id,
            )
        )
    ).json()
    errno = response.get("errno", response.get("code"))
    if errno != 0:
        raise RuntimeError(
            response.get("msg", response.get("message", "failed to fetch project"))
        )
    data = response.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("old project response data is empty")
    return data


def fetch_project_payload(
    request: Any,
    project_id: int,
) -> dict[str, Any]:
    try:
        return _fetch_project_payload_new(request=request, project_id=project_id)
    except Exception as new_error:
        try:
            return _fetch_project_payload_old(request=request, project_id=project_id)
        except Exception as old_error:
            raise RuntimeError(
                "failed to fetch project detail from new and old APIs: "
                "new={0}; old={1}".format(new_error, old_error)
            ) from old_error


def _build_ticket_option(
    *,
    screen: dict[str, Any],
    ticket: dict[str, Any],
    hot_project: bool,
    has_eticket: bool,
) -> dict[str, Any]:
    express_fee = 0 if has_eticket else max(int(screen.get("express_fee", 0)), 0)
    price = int(ticket.get("price", 0)) + express_fee
    option = copy.deepcopy(ticket)
    option["price"] = price
    option["screen"] = screen.get("name", "")
    option["screen_id"] = screen.get("id")
    option["is_hot_project"] = hot_project
    option["project_id"] = screen.get("project_id")
    option["sale_status"] = _format_sale_status(ticket)
    option["display"] = (
        "{screen} - {desc} - ￥{price} - {status} - 【起售时间：{sale_start}】".format(
            screen=screen.get("name", ""),
            desc=ticket.get("desc", ""),
            price=price / 100,
            status=option["sale_status"],
            sale_start=ticket.get("sale_start", ""),
        )
    )
    if screen.get("link_id") not in (None, ""):
        option["link_id"] = screen["link_id"]
    return option


def _merge_link_goods(
    *,
    request: Any,
    screen_list: list[dict[str, Any]],
    project_id: int,
) -> list[dict[str, Any]]:
    merged = copy.deepcopy(screen_list)
    try:
        good_list = request.get(
            url=(
                "https://show.bilibili.com/api/ticket/linkgoods/list"
                "?project_id={0}&page_type=0".format(project_id)
            )
        ).json()
        good_ids = [item["id"] for item in good_list.get("data", {}).get("list", [])]
        for good_id in good_ids:
            detail = request.get(
                url=(
                    "https://show.bilibili.com/api/ticket/linkgoods/detail"
                    "?link_id={0}".format(good_id)
                )
            ).json()
            good_data = detail.get("data") or {}
            item_id = good_data.get("item_id")
            for item in good_data.get("specs_list", []):
                enriched = copy.deepcopy(item)
                enriched["project_id"] = item_id
                enriched["link_id"] = good_id
                merged.append(enriched)
    except Exception:
        return merged
    return merged


def _fetch_ticket_options(
    *,
    request: Any,
    project_payload: dict[str, Any],
    selected_date: str | None,
) -> list[dict[str, Any]]:
    hot_project = bool(project_payload.get("hotProject"))
    has_eticket = bool(project_payload.get("has_eticket"))
    project_id = int(project_payload["id"])

    if selected_date:
        date_payload = request.get(
            url=(
                "https://show.bilibili.com/api/ticket/project/infoByDate"
                "?id={0}&date={1}".format(project_id, selected_date)
            )
        ).json()
        screens = date_payload.get("data", {}).get("screen_list", [])
    else:
        screens = _merge_link_goods(
            request=request,
            screen_list=project_payload.get("screen_list", []),
            project_id=project_id,
        )

    options: list[dict[str, Any]] = []
    for screen in screens:
        if "name" not in screen:
            continue
        screen_copy = copy.deepcopy(screen)
        screen_copy["project_id"] = screen_copy.get("project_id", project_id)
        for ticket in screen.get("ticket_list", []):
            options.append(
                _build_ticket_option(
                    screen=screen_copy,
                    ticket=ticket,
                    hot_project=hot_project,
                    has_eticket=has_eticket,
                )
            )
    return options


def fetch_project_detail(
    project_input: str | int,
    *,
    cookies: list[dict[str, Any]] | dict[str, Any] | None = None,
    cookies_path: str | Path | None = None,
) -> dict[str, Any]:
    request = _make_request(cookies=cookies, cookies_path=cookies_path)
    project_id = _extract_project_id(project_input)
    payload = fetch_project_payload(request=request, project_id=project_id)
    payload["project_url"] = (
        "https://show.bilibili.com/platform/detail.html?id={0}".format(payload["id"])
    )
    return payload


def fetch_ticket_options(
    project_input: str | int,
    *,
    cookies: list[dict[str, Any]] | dict[str, Any] | None = None,
    cookies_path: str | Path | None = None,
    selected_date: str | None = None,
) -> dict[str, Any]:
    request = _make_request(cookies=cookies, cookies_path=cookies_path)
    project_id = _extract_project_id(project_input)
    project_payload = fetch_project_payload(request=request, project_id=project_id)
    options = _fetch_ticket_options(
        request=request,
        project_payload=project_payload,
        selected_date=selected_date,
    )
    return {
        "project_id": project_payload["id"],
        "project_name": project_payload.get("name", ""),
        "selected_date": selected_date,
        "sales_dates": [
            item["date"] for item in project_payload.get("sales_dates", [])
        ],
        "ticket_options": options,
    }


def fetch_buyers(
    project_input: str | int,
    *,
    cookies: list[dict[str, Any]] | dict[str, Any] | None = None,
    cookies_path: str | Path | None = None,
) -> dict[str, Any]:
    request = _make_request(cookies=cookies, cookies_path=cookies_path)
    project_id = _extract_project_id(project_input)
    project_payload = fetch_project_payload(request=request, project_id=project_id)
    buyer_response = request.get(
        url=(
            "https://show.bilibili.com/api/ticket/buyer/list"
            "?is_default&projectId={0}".format(project_payload["id"])
        )
    ).json()
    buyers = buyer_response.get("data", {}).get("list", [])
    return {
        "project_id": project_payload["id"],
        "project_name": project_payload.get("name", ""),
        "buyers": buyers,
    }


def fetch_addresses(
    *,
    cookies: list[dict[str, Any]] | dict[str, Any] | None = None,
    cookies_path: str | Path | None = None,
) -> dict[str, Any]:
    request = _make_request(cookies=cookies, cookies_path=cookies_path)
    addr_response = request.get(
        url="https://show.bilibili.com/api/ticket/addr/list"
    ).json()
    return {"addresses": addr_response.get("data", {}).get("addr_list", [])}


def fetch_purchase_context(
    project_input: str | int,
    *,
    cookies: list[dict[str, Any]] | dict[str, Any] | None = None,
    cookies_path: str | Path | None = None,
    selected_date: str | None = None,
    phone: str = "",
) -> dict[str, Any]:
    project_id = _extract_project_id(project_input)
    request = _make_request(cookies=cookies, cookies_path=cookies_path)
    project_payload = fetch_project_payload(request=request, project_id=project_id)
    ticket_options = _fetch_ticket_options(
        request=request,
        project_payload=project_payload,
        selected_date=selected_date,
    )

    buyer_response = request.get(
        url=(
            "https://show.bilibili.com/api/ticket/buyer/list"
            "?is_default&projectId={0}".format(project_payload["id"])
        )
    ).json()
    addr_response = request.get(
        url="https://show.bilibili.com/api/ticket/addr/list"
    ).json()

    buyers = buyer_response.get("data", {}).get("list", [])
    addresses = addr_response.get("data", {}).get("addr_list", [])

    return {
        "project_id": project_payload["id"],
        "project_name": project_payload.get("name", ""),
        "project_url": (
            "https://show.bilibili.com/platform/detail.html?id={0}".format(
                project_payload["id"]
            )
        ),
        "username": request.get_request_name(),
        "phone": phone or request.cookieManager.get_config_value("phone", ""),
        "is_hot_project": bool(project_payload.get("hotProject")),
        "has_eticket": bool(project_payload.get("has_eticket")),
        "sales_dates": [
            item["date"] for item in project_payload.get("sales_dates", [])
        ],
        "selected_date": selected_date,
        "venue": project_payload.get("venue_info", {}),
        "ticket_options": ticket_options,
        "buyers": buyers,
        "addresses": addresses,
        "cookies": request.cookieManager.get_cookies(force=True),
    }
