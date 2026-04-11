from __future__ import annotations

import copy
import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

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


__all__ = [
    "BuyTaskRecord",
    "ValidationResult",
    "generate_ticket_config",
    "start_buy",
    "task_status",
    "validate_config",
]
