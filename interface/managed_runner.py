from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_json(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _dump_json(path: Path, payload: dict[str, Any]) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def _append_log(path: Path, message: str) -> None:
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(message)
        handle.write("\n")


def _heartbeat_loop(
    status_path: Path,
    status: dict[str, Any],
    lock: threading.Lock,
    stop_event: threading.Event,
    interval_seconds: float = 2.0,
) -> None:
    while not stop_event.wait(interval_seconds):
        with lock:
            if status.get("finished_at") is not None:
                return
            status["updated_at"] = time.time()
            _dump_json(status_path, status)


def main(run_dir_arg: str) -> int:
    from app_cmd.config.BuyConfig import BuyConfig
    from interface.config import RuntimeOptions
    from task.buy import Buy

    run_dir = Path(run_dir_arg)
    status_path = run_dir / "status.json"
    result_path = run_dir / "result.json"
    logs_path = run_dir / "events.log"

    metadata = _load_json(run_dir / "run.json")
    config = _load_json(run_dir / "config.json")
    runtime = RuntimeOptions.from_mapping(_load_json(run_dir / "runtime.json"))
    existing_status = _load_json(status_path)

    status = {
        "ok": True,
        "run_id": metadata["run_id"],
        "status": "running",
        "detail": config.get("detail", metadata["run_id"]),
        "pid": os.getpid(),
        "created_at": metadata["created_at"],
        "started_at": time.time(),
        "updated_at": time.time(),
        "finished_at": None,
        "payment_qr_url": None,
        "error": None,
        "last_message": None,
        "heartbeat_timeout_seconds": existing_status.get("heartbeat_timeout_seconds"),
        "logs_path": str(logs_path),
        "result_path": str(result_path),
        "config_path": str(run_dir / "config.json"),
        "runtime_path": str(run_dir / "runtime.json"),
    }
    _dump_json(status_path, status)
    status_lock = threading.Lock()
    heartbeat_stop = threading.Event()
    heartbeat_thread = threading.Thread(
        target=_heartbeat_loop,
        args=(status_path, status, status_lock, heartbeat_stop),
        daemon=True,
        name="biliTickerBuy-heartbeat",
    )
    heartbeat_thread.start()

    buy_job = Buy(
        config=BuyConfig.from_runtime_options(
            json.dumps(config, ensure_ascii=False),
            runtime,
            show_qrcode=False,
        ),
    )

    final_status = "completed"
    try:
        for event in buy_job.stream():
            message = event.message
            if message is not None:
                _append_log(logs_path, message)
            with status_lock:
                status["updated_at"] = time.time()
                if message is not None:
                    status["last_message"] = message
                    if "抢票成功" in message:
                        final_status = "succeeded"
                    if "有重复订单" in message:
                        final_status = "duplicate_order"
                    if message.startswith("PAYMENT_QR_URL="):
                        status["payment_qr_url"] = message.split("=", 1)[1]
                _dump_json(status_path, status)
    except BaseException as exc:
        with status_lock:
            status["status"] = "failed"
            status["error"] = repr(exc)
            status["last_message"] = "RUNNER_EXCEPTION={0!r}".format(exc)
            status["updated_at"] = time.time()
            status["finished_at"] = time.time()
        _append_log(logs_path, "RUNNER_EXCEPTION={0!r}".format(exc))
        _dump_json(status_path, status)
        _dump_json(
            result_path,
            {
                "ok": False,
                "run_id": metadata["run_id"],
                "status": "failed",
                "error": repr(exc),
                "payment_qr_url": status["payment_qr_url"],
                "logs_path": str(logs_path),
                "last_message": status["last_message"],
            },
        )
        heartbeat_stop.set()
        heartbeat_thread.join(timeout=3)
        return 1

    with status_lock:
        status["status"] = final_status
        status["updated_at"] = time.time()
        status["finished_at"] = time.time()
        _dump_json(status_path, status)
    _dump_json(
        result_path,
        {
            "ok": True,
            "run_id": metadata["run_id"],
            "status": final_status,
            "payment_qr_url": status["payment_qr_url"],
            "logs_path": str(logs_path),
            "last_message": status["last_message"],
        },
    )
    heartbeat_stop.set()
    heartbeat_thread.join(timeout=3)
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: managed_runner.py <run_dir>")
    raise SystemExit(main(sys.argv[1]))
