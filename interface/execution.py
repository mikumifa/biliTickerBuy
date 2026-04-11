from __future__ import annotations

import copy
import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .config import build_runtime_options, validate_config
from .types import BuyTaskRecord

_TASKS: dict[str, BuyTaskRecord] = {}
_TASKS_LOCK = threading.Lock()


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
        return {"ok": False, "validation": validation.to_dict(), "task": None}

    assert validation.normalized_config is not None
    runtime = build_runtime_options()
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
        name="biliTickerBuy-task-{0}".format(task_id[:8]),
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
            return {"ok": False, "error": "task not found", "task_id": task_id}
        return {"ok": True, "task": record.to_dict()}


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
