from __future__ import annotations

import copy
import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any
import subprocess
import sys

from .config import build_runtime_options, validate_config
from .types import BuyTaskRecord

_TASKS: dict[str, BuyTaskRecord] = {}
_TASKS_LOCK = threading.Lock()


def _package_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _managed_runs_root(root: str | Path | None = None) -> Path:
    target = Path(root) if root is not None else _package_root() / "btb_runs"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def _load_json(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


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


def start_managed_buy(
    config_or_path: str | Path | dict[str, Any],
    *,
    runtime_options: dict[str, Any] | None = None,
    run_id: str | None = None,
    runs_root: str | Path | None = None,
) -> dict[str, Any]:
    validation = validate_config(config_or_path)
    if not validation.ok:
        return {"ok": False, "validation": validation.to_dict(), "run": None}

    assert validation.normalized_config is not None
    runtime = build_runtime_options(show_qrcode=False)
    if runtime_options:
        runtime.update(build_runtime_options(**runtime_options))

    managed_root = _managed_runs_root(runs_root)
    assigned_run_id = run_id or uuid.uuid4().hex
    run_dir = managed_root / assigned_run_id
    if run_dir.exists():
        return {
            "ok": False,
            "validation": validation.to_dict(),
            "run": None,
            "error": "run_id already exists",
            "run_id": assigned_run_id,
        }
    run_dir.mkdir(parents=True, exist_ok=False)

    run_metadata = {
        "run_id": assigned_run_id,
        "created_at": time.time(),
    }
    _dump_json(run_dir / "run.json", run_metadata)
    _dump_json(run_dir / "config.json", validation.normalized_config)
    _dump_json(run_dir / "runtime.json", runtime)

    status = {
        "ok": True,
        "run_id": assigned_run_id,
        "status": "pending",
        "detail": validation.normalized_config.get("detail", assigned_run_id),
        "pid": None,
        "created_at": run_metadata["created_at"],
        "started_at": None,
        "updated_at": run_metadata["created_at"],
        "finished_at": None,
        "payment_qr_url": None,
        "error": None,
        "last_message": None,
        "logs_path": str(run_dir / "events.log"),
        "result_path": str(run_dir / "result.json"),
        "config_path": str(run_dir / "config.json"),
        "runtime_path": str(run_dir / "runtime.json"),
    }
    _dump_json(run_dir / "status.json", status)

    runner_path = _package_root() / "interface" / "managed_runner.py"
    command = [sys.executable, str(runner_path), str(run_dir)]
    env = os.environ.copy()
    env.setdefault("BTB_APP_LOG_NAME", "app-{0}.log".format(assigned_run_id))

    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )

    stdout_handle = open(run_dir / "stdout.log", "a", encoding="utf-8")
    stderr_handle = open(run_dir / "stderr.log", "a", encoding="utf-8")
    try:
        process = subprocess.Popen(
            command,
            cwd=str(_package_root()),
            stdout=stdout_handle,
            stderr=stderr_handle,
            env=env,
            creationflags=creationflags,
        )
    finally:
        stdout_handle.close()
        stderr_handle.close()

    status["pid"] = process.pid
    status["updated_at"] = time.time()
    _dump_json(run_dir / "status.json", status)

    return {
        "ok": True,
        "validation": validation.to_dict(),
        "run": {
            "run_id": assigned_run_id,
            "run_dir": str(run_dir),
            "status_path": str(run_dir / "status.json"),
            "result_path": str(run_dir / "result.json"),
            "logs_path": str(run_dir / "events.log"),
            "pid": process.pid,
        },
    }


def managed_task_status(
    run_id: str,
    *,
    runs_root: str | Path | None = None,
) -> dict[str, Any]:
    run_dir = _managed_runs_root(runs_root) / run_id
    status_path = run_dir / "status.json"
    if not status_path.exists():
        return {"ok": False, "error": "managed run not found", "run_id": run_id}
    status = _load_json(status_path)
    result_path = run_dir / "result.json"
    if result_path.exists():
        status["result"] = _load_json(result_path)
    return {"ok": True, "run": status}
