from __future__ import annotations

import copy
import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

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


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    normalized_config: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BuyTaskRecord:
    task_id: str
    status: str
    detail: str
    created_at: float
    started_at: float | None = None
    finished_at: float | None = None
    error: str | None = None
    payment_qr_url: str | None = None
    logs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_TASKS: dict[str, BuyTaskRecord] = {}
_TASKS_LOCK = threading.Lock()


def _load_json_file(path: str | Path) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def load_ticket_config(path: str | Path) -> dict[str, Any]:
    return _load_config(path)


def save_ticket_config(
    config: dict[str, Any],
    path: str | Path,
    *,
    ensure_ascii: bool = False,
    indent: int = 2,
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(config, handle, ensure_ascii=ensure_ascii, indent=indent)
    return target


def _deepcopy_dict(data: Any) -> dict[str, Any]:
    if isinstance(data, dict):
        return copy.deepcopy(data)
    raise TypeError("config must be a dict or a json file path")


def _load_config(config_or_path: str | Path | dict[str, Any]) -> dict[str, Any]:
    if isinstance(config_or_path, (str, Path)):
        return _deepcopy_dict(_load_json_file(config_or_path))
    return _deepcopy_dict(config_or_path)


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


def _normalize_buyer_info(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [copy.deepcopy(value)]
    if isinstance(value, list):
        return copy.deepcopy(value)
    return []


def generate_ticket_config(
    parameters: dict[str, Any],
    *,
    defaults: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config: dict[str, Any] = copy.deepcopy(defaults or {})
    config.update(copy.deepcopy(parameters))

    if "cookies" not in config and config.get("cookies_path"):
        config["cookies"] = _coerce_cookie_store(_load_json_file(config["cookies_path"]))
    elif "cookies" in config:
        config["cookies"] = _coerce_cookie_store(config["cookies"])

    if "buyer_info" in config:
        config["buyer_info"] = _normalize_buyer_info(config["buyer_info"])

    count = config.get("count")
    unit_price = config.pop("unit_price", None)
    if config.get("pay_money") in (None, "") and unit_price is not None and count:
        config["pay_money"] = int(unit_price) * int(count)

    config.setdefault("username", "unknown-user")
    config.setdefault("order_type", 1)
    config.setdefault("is_hot_project", False)
    config.setdefault("phone", "")

    if not config.get("detail"):
        config["detail"] = "{username}-project-{project_id}-screen-{screen_id}-sku-{sku_id}".format(
            username=config.get("username", "unknown-user"),
            project_id=config.get("project_id", "unknown"),
            screen_id=config.get("screen_id", "unknown"),
            sku_id=config.get("sku_id", "unknown"),
        )

    if config.get("link_id") in ("", None):
        config.pop("link_id", None)

    if config.get("cookies") is None:
        config.pop("cookies", None)

    return config


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


def _make_request(
    *,
    cookies: list[dict[str, Any]] | dict[str, Any] | None = None,
    cookies_path: str | Path | None = None,
) -> Any:
    from util.BiliRequest import BiliRequest

    return BiliRequest(cookies=cookies, cookies_config_path=cookies_path)


def get_login_state(
    *,
    cookies: list[dict[str, Any]] | dict[str, Any] | None = None,
    cookies_path: str | Path | None = None,
) -> dict[str, Any]:
    request = _make_request(cookies=cookies, cookies_path=cookies_path)
    has_cookies = request.cookieManager.have_cookies()
    username = request.get_request_name()
    logged_in = has_cookies and username != "未登录"
    return {
        "ok": True,
        "logged_in": logged_in,
        "username": username,
        "has_cookies": has_cookies,
        "next_action": "continue" if logged_in else "prompt_qr_login",
    }


def fetch_project_detail(
    project_input: str | int,
    *,
    cookies: list[dict[str, Any]] | dict[str, Any] | None = None,
    cookies_path: str | Path | None = None,
) -> dict[str, Any]:
    request = _make_request(cookies=cookies, cookies_path=cookies_path)
    project_id = _extract_project_id(project_input)
    payload = _fetch_project_payload(request=request, project_id=project_id)
    payload = copy.deepcopy(payload)
    payload["project_url"] = (
        "https://show.bilibili.com/platform/detail.html?id={0}".format(payload["id"])
    )
    return payload


def _fetch_project_payload(
    *,
    request: Any,
    project_id: int,
) -> dict[str, Any]:
    response = request.get(
        url=(
            "https://show.bilibili.com/api/ticket/project/getV2"
            "?version=134&id={0}&project_id={0}".format(project_id)
        )
    ).json()
    errno = response.get("errno", response.get("code"))
    if errno != 0:
        raise RuntimeError(
            response.get("msg", response.get("message", "failed to fetch project"))
        )
    return response["data"]


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


def fetch_ticket_options(
    project_input: str | int,
    *,
    cookies: list[dict[str, Any]] | dict[str, Any] | None = None,
    cookies_path: str | Path | None = None,
    selected_date: str | None = None,
) -> dict[str, Any]:
    request = _make_request(cookies=cookies, cookies_path=cookies_path)
    project_id = _extract_project_id(project_input)
    project_payload = _fetch_project_payload(request=request, project_id=project_id)
    options = _fetch_ticket_options(
        request=request,
        project_payload=project_payload,
        selected_date=selected_date,
    )
    return {
        "project_id": project_payload["id"],
        "project_name": project_payload.get("name", ""),
        "selected_date": selected_date,
        "sales_dates": [item["date"] for item in project_payload.get("sales_dates", [])],
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
    project_payload = _fetch_project_payload(request=request, project_id=project_id)
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
    addr_response = request.get(url="https://show.bilibili.com/api/ticket/addr/list").json()
    return {
        "addresses": addr_response.get("data", {}).get("addr_list", []),
    }


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
    project_payload = _fetch_project_payload(request=request, project_id=project_id)
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
        "sales_dates": [item["date"] for item in project_payload.get("sales_dates", [])],
        "selected_date": selected_date,
        "venue": project_payload.get("venue_info", {}),
        "ticket_options": ticket_options,
        "buyers": buyers,
        "addresses": addresses,
        "cookies": request.cookieManager.get_cookies(force=True),
    }


def build_runtime_options(
    *,
    interval: int = 1000,
    time_start: str = "",
    audio_path: str = "",
    pushplusToken: str = "",
    serverchanKey: str = "",
    barkToken: str = "",
    https_proxys: str = "none",
    serverchan3ApiUrl: str = "",
    ntfy_url: str = "",
    ntfy_username: str = "",
    ntfy_password: str = "",
    show_random_message: bool = True,
    show_qrcode: bool = False,
) -> dict[str, Any]:
    return {
        "interval": interval,
        "time_start": time_start,
        "audio_path": audio_path,
        "pushplusToken": pushplusToken,
        "serverchanKey": serverchanKey,
        "barkToken": barkToken,
        "https_proxys": https_proxys,
        "serverchan3ApiUrl": serverchan3ApiUrl,
        "ntfy_url": ntfy_url,
        "ntfy_username": ntfy_username,
        "ntfy_password": ntfy_password,
        "show_random_message": show_random_message,
        "show_qrcode": show_qrcode,
    }


def build_ticket_config_from_selection(
    purchase_context: dict[str, Any],
    selection: dict[str, Any],
    *,
    defaults: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ticket_options = purchase_context.get("ticket_options") or []
    buyers = purchase_context.get("buyers") or []
    addresses = purchase_context.get("addresses") or []

    ticket_index = selection.get("ticket_index")
    if not isinstance(ticket_index, int) or not (0 <= ticket_index < len(ticket_options)):
        raise ValueError("ticket_index is required and must point to a valid option")

    buyer_indices = selection.get("buyer_indices")
    if not isinstance(buyer_indices, list) or not buyer_indices:
        raise ValueError("buyer_indices must be a non-empty list")
    if any(
        not isinstance(idx, int) or idx < 0 or idx >= len(buyers) for idx in buyer_indices
    ):
        raise ValueError("buyer_indices contains an invalid buyer index")

    address_index = selection.get("address_index")
    if not isinstance(address_index, int) or not (0 <= address_index < len(addresses)):
        raise ValueError("address_index is required and must point to a valid address")

    buyer_name = selection.get("buyer")
    buyer_phone = selection.get("tel")
    if not buyer_name:
        raise ValueError("buyer is required")
    if not buyer_phone:
        raise ValueError("tel is required")

    ticket = copy.deepcopy(ticket_options[ticket_index])
    selected_buyers = [copy.deepcopy(buyers[idx]) for idx in buyer_indices]
    address = copy.deepcopy(addresses[address_index])
    buyer_names = "-".join(item.get("name", "") for item in selected_buyers)

    detail = (
        "{username}-{project_name}-{ticket_label}-{buyers}".format(
            username=purchase_context.get("username", "unknown-user"),
            project_name=purchase_context.get("project_name", "unknown-project"),
            ticket_label=ticket.get("display", "unknown-ticket"),
            buyers=buyer_names,
        )
    ).strip("-")

    parameters = {
        "username": purchase_context.get("username", "unknown-user"),
        "detail": detail,
        "count": len(selected_buyers),
        "screen_id": ticket["screen_id"],
        "project_id": ticket.get("project_id", purchase_context.get("project_id")),
        "is_hot_project": ticket.get(
            "is_hot_project",
            purchase_context.get("is_hot_project", False),
        ),
        "sku_id": ticket["id"],
        "order_type": 1,
        "pay_money": int(ticket["price"]) * len(selected_buyers),
        "buyer_info": selected_buyers,
        "buyer": buyer_name,
        "tel": buyer_phone,
        "deliver_info": {
            "name": address.get("name", ""),
            "tel": address.get("phone", ""),
            "addr_id": address.get("id", 0),
            "addr": "{prov}{city}{area}{addr}".format(
                prov=address.get("prov", ""),
                city=address.get("city", ""),
                area=address.get("area", ""),
                addr=address.get("addr", ""),
            ),
        },
        "cookies": purchase_context.get("cookies"),
        "phone": selection.get("phone", purchase_context.get("phone", "")),
    }
    if ticket.get("link_id") not in (None, ""):
        parameters["link_id"] = ticket["link_id"]

    return generate_ticket_config(parameters, defaults=defaults)


def validate_config(config_or_path: str | Path | dict[str, Any]) -> ValidationResult:
    try:
        config = generate_ticket_config(_load_config(config_or_path))
    except Exception as exc:
        return ValidationResult(ok=False, errors=[str(exc)])

    errors: list[str] = []
    warnings: list[str] = []

    for key in REQUIRED_FIELDS:
        if key not in config or config[key] in (None, "", []):
            errors.append("missing required field: {0}".format(key))

    for key in ("count", "screen_id", "project_id", "sku_id", "pay_money"):
        if key in config and config[key] not in (None, ""):
            try:
                config[key] = int(config[key])
            except (TypeError, ValueError):
                errors.append("{0} must be an integer".format(key))

    if isinstance(config.get("count"), int) and config["count"] <= 0:
        errors.append("count must be greater than 0")

    buyer_info = config.get("buyer_info")
    if not isinstance(buyer_info, list) or not buyer_info:
        errors.append("buyer_info must be a non-empty list")
    else:
        for idx, buyer in enumerate(buyer_info):
            if not isinstance(buyer, dict):
                errors.append("buyer_info[{0}] must be an object".format(idx))
                continue
            for field_name in BUYER_REQUIRED_FIELDS:
                if not buyer.get(field_name):
                    errors.append(
                        "buyer_info[{0}] missing field: {1}".format(idx, field_name)
                    )

    deliver_info = config.get("deliver_info")
    if not isinstance(deliver_info, dict):
        errors.append("deliver_info must be an object")
    else:
        for field_name in DELIVER_REQUIRED_FIELDS:
            if deliver_info.get(field_name) in (None, ""):
                errors.append("deliver_info missing field: {0}".format(field_name))

    cookies = config.get("cookies")
    if not isinstance(cookies, list) or not cookies:
        errors.append("cookies must be a non-empty list")
    else:
        for idx, cookie in enumerate(cookies):
            if not isinstance(cookie, dict):
                errors.append("cookies[{0}] must be an object".format(idx))
                continue
            for field_name in COOKIE_REQUIRED_FIELDS:
                if cookie.get(field_name) in (None, ""):
                    errors.append("cookies[{0}] missing field: {1}".format(idx, field_name))

    if config.get("phone") in (None, ""):
        warnings.append("phone is empty; this is allowed but some flows may rely on it")

    return ValidationResult(
        ok=not errors,
        errors=errors,
        warnings=warnings,
        normalized_config=config,
    )


def _append_log(task_id: str, message: str) -> None:
    with _TASKS_LOCK:
        record = _TASKS[task_id]
        record.logs.append(message)
        if len(record.logs) > 200:
            record.logs = record.logs[-200:]


def _update_task(task_id: str, **fields: Any) -> None:
    with _TASKS_LOCK:
        record = _TASKS[task_id]
        for key, value in fields.items():
            setattr(record, key, value)


def _run_buy_task(
    task_id: str,
    config: dict[str, Any],
    runtime_options: dict[str, Any],
) -> None:
    from task.buy import buy_stream
    from util.Notifier import NotifierConfig

    notifier_config = NotifierConfig(
        serverchan_key=runtime_options.get("serverchanKey", ""),
        serverchan3_api_url=runtime_options.get("serverchan3ApiUrl", ""),
        pushplus_token=runtime_options.get("pushplusToken", ""),
        bark_token=runtime_options.get("barkToken", ""),
        ntfy_url=runtime_options.get("ntfy_url", ""),
        ntfy_username=runtime_options.get("ntfy_username", ""),
        ntfy_password=runtime_options.get("ntfy_password", ""),
        audio_path=runtime_options.get("audio_path", ""),
    )
    _update_task(task_id, status="running", started_at=time.time())
    succeeded = False
    try:
        for message in buy_stream(
            json.dumps(config, ensure_ascii=False),
            runtime_options.get("time_start", ""),
            runtime_options.get("interval", 1000),
            notifier_config,
            runtime_options.get("https_proxys", "none"),
            runtime_options.get("show_random_message", True),
            runtime_options.get("show_qrcode", False),
        ):
            _append_log(task_id, message)
            if "抢票成功" in message:
                succeeded = True
            if message.startswith("PAYMENT_QR_URL="):
                _update_task(task_id, payment_qr_url=message.split("=", 1)[1])

        _update_task(
            task_id,
            status="succeeded" if succeeded else "completed",
            finished_at=time.time(),
        )
    except Exception as exc:
        _append_log(task_id, "task exception: {0!r}".format(exc))
        _update_task(
            task_id,
            status="failed",
            finished_at=time.time(),
            error=repr(exc),
        )


def start_buy(
    config_or_path: str | Path | dict[str, Any],
    *,
    runtime_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    validation = validate_config(config_or_path)
    if not validation.ok:
        return {
            "ok": False,
            "validation": validation.to_dict(),
            "task": None,
        }

    assert validation.normalized_config is not None
    runtime = {
        "interval": 1000,
        "time_start": "",
        "audio_path": "",
        "pushplusToken": "",
        "serverchanKey": "",
        "barkToken": "",
        "https_proxys": "none",
        "serverchan3ApiUrl": "",
        "ntfy_url": "",
        "ntfy_username": "",
        "ntfy_password": "",
        "show_random_message": True,
        "show_qrcode": False,
    }
    if runtime_options:
        runtime.update(copy.deepcopy(runtime_options))

    task_id = uuid.uuid4().hex
    record = BuyTaskRecord(
        task_id=task_id,
        status="pending",
        detail=validation.normalized_config.get("detail", "unknown-task"),
        created_at=time.time(),
    )
    with _TASKS_LOCK:
        _TASKS[task_id] = record

    thread = threading.Thread(
        target=_run_buy_task,
        args=(task_id, validation.normalized_config, runtime),
        daemon=True,
        name="bilitickerbuy-task-{0}".format(task_id[:8]),
    )
    thread.start()

    return {
        "ok": True,
        "validation": validation.to_dict(),
        "task": record.to_dict(),
    }


def task_status(task_id: str) -> dict[str, Any]:
    with _TASKS_LOCK:
        record = _TASKS.get(task_id)
        if record is None:
            return {
                "ok": False,
                "error": "task not found",
                "task_id": task_id,
            }
        return {
            "ok": True,
            "task": record.to_dict(),
        }


def run_buy_sync(
    config_or_path: str | Path | dict[str, Any],
    *,
    runtime_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from task.buy import buy_stream
    from util.Notifier import NotifierConfig

    validation = validate_config(config_or_path)
    if not validation.ok:
        return {
            "ok": False,
            "validation": validation.to_dict(),
            "logs": [],
            "payment_qr_url": None,
        }

    assert validation.normalized_config is not None
    runtime = build_runtime_options()
    if runtime_options:
        runtime.update(copy.deepcopy(runtime_options))

    notifier_config = NotifierConfig(
        serverchan_key=runtime.get("serverchanKey", ""),
        serverchan3_api_url=runtime.get("serverchan3ApiUrl", ""),
        pushplus_token=runtime.get("pushplusToken", ""),
        bark_token=runtime.get("barkToken", ""),
        ntfy_url=runtime.get("ntfy_url", ""),
        ntfy_username=runtime.get("ntfy_username", ""),
        ntfy_password=runtime.get("ntfy_password", ""),
        audio_path=runtime.get("audio_path", ""),
    )

    logs: list[str] = []
    payment_qr_url: str | None = None
    succeeded = False
    for message in buy_stream(
        json.dumps(validation.normalized_config, ensure_ascii=False),
        runtime.get("time_start", ""),
        runtime.get("interval", 1000),
        notifier_config,
        runtime.get("https_proxys", "none"),
        runtime.get("show_random_message", True),
        runtime.get("show_qrcode", False),
    ):
        logs.append(message)
        if "抢票成功" in message:
            succeeded = True
        if message.startswith("PAYMENT_QR_URL="):
            payment_qr_url = message.split("=", 1)[1]

    return {
        "ok": True,
        "validation": validation.to_dict(),
        "status": "succeeded" if succeeded else "completed",
        "logs": logs,
        "payment_qr_url": payment_qr_url,
    }


__all__ = [
    "BuyTaskRecord",
    "ValidationResult",
    "build_runtime_options",
    "build_ticket_config_from_selection",
    "fetch_addresses",
    "fetch_buyers",
    "fetch_purchase_context",
    "fetch_project_detail",
    "fetch_ticket_options",
    "generate_ticket_config",
    "get_login_state",
    "load_ticket_config",
    "run_buy_sync",
    "save_ticket_config",
    "start_buy",
    "task_status",
    "validate_config",
]
