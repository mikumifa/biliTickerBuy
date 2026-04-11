from __future__ import annotations

import copy
import json
import math
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .common import (
    BUYER_REQUIRED_FIELDS,
    COOKIE_REQUIRED_FIELDS,
    DELIVER_REQUIRED_FIELDS,
    REQUIRED_FIELDS,
    _coerce_cookie_store,
    _load_config,
    _load_json_file,
)
from .types import ValidationResult


def normalize_time_start(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%dT%H:%M:%S")

    text = str(value).strip()
    if not text:
        return ""

    for fmt in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
    ):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.strftime("%Y-%m-%dT%H:%M:%S" if "%S" in fmt else "%Y-%m-%dT%H:%M")
        except ValueError:
            continue

    match = re.fullmatch(r"(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?", text)
    if not match:
        raise ValueError(
            "time_start must be ISO-like datetime or HH:MM[:SS], for example 2026-04-12T00:36 or 00:36"
        )

    hour = int(match.group(1))
    minute = int(match.group(2))
    second = int(match.group(3) or 0)
    if hour > 23 or minute > 59 or second > 59:
        raise ValueError("time_start clock value is out of range")

    now = datetime.now()
    parsed = now.replace(hour=hour, minute=minute, second=second, microsecond=0)
    if parsed <= now:
        parsed += timedelta(days=1)
    if match.group(3) is None:
        return parsed.strftime("%Y-%m-%dT%H:%M")
    return parsed.strftime("%Y-%m-%dT%H:%M:%S")


def normalize_interval(value: Any) -> int:
    if value in (None, ""):
        return 1000
    if isinstance(value, bool):
        raise ValueError("interval must be a positive duration")
    if isinstance(value, int):
        if value <= 0:
            raise ValueError("interval must be greater than 0")
        return value
    if isinstance(value, float):
        if not math.isfinite(value) or value <= 0:
            raise ValueError("interval must be greater than 0")
        return int(round(value))

    text = str(value).strip().lower()
    if not text:
        return 1000
    if text.isdigit():
        parsed = int(text)
        if parsed <= 0:
            raise ValueError("interval must be greater than 0")
        return parsed

    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*(ms|s|sec|secs|m|min|mins)?", text)
    if not match:
        raise ValueError(
            "interval must be milliseconds or a duration like 500, 500ms, 0.5s, 0.36m"
        )
    amount = float(match.group(1))
    unit = match.group(2) or "ms"
    if amount <= 0:
        raise ValueError("interval must be greater than 0")
    multiplier = {
        "ms": 1,
        "s": 1000,
        "sec": 1000,
        "secs": 1000,
        "m": 60000,
        "min": 60000,
        "mins": 60000,
    }[unit]
    return max(1, int(round(amount * multiplier)))


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
        "interval": normalize_interval(interval),
        "time_start": normalize_time_start(time_start),
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
                    errors.append("buyer_info[{0}] missing field: {1}".format(idx, field_name))

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
