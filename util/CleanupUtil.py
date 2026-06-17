from __future__ import annotations

import os
import shutil
import time
from pathlib import Path


def _trim_old_paths(paths: list[Path], *, max_count: int) -> list[Path]:
    if max_count <= 0 or len(paths) <= max_count:
        return []
    sorted_paths = sorted(paths, key=lambda item: item.stat().st_mtime, reverse=True)
    return sorted_paths[max_count:]


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
        return
    try:
        path.unlink(missing_ok=True)
    except TypeError:
        if path.exists():
            path.unlink()


def cleanup_runtime_artifacts(
    *,
    logs_dir: str | Path,
    runs_dir: str | Path,
    retention_days: int = 7,
    max_log_files: int = 200,
    max_run_dirs: int = 100,
) -> dict[str, int]:
    now = time.time()
    cutoff = now - max(1, int(retention_days)) * 86400
    logs_root = Path(logs_dir)
    runs_root = Path(runs_dir)
    removed_logs = 0
    removed_runs = 0

    if logs_root.exists():
        log_files = [path for path in logs_root.iterdir() if path.is_file()]
        for path in list(log_files):
            if path.stat().st_mtime < cutoff:
                _remove_path(path)
                removed_logs += 1
        remaining_logs = [path for path in logs_root.iterdir() if path.is_file()]
        for path in _trim_old_paths(
            remaining_logs, max_count=max(1, int(max_log_files))
        ):
            _remove_path(path)
            removed_logs += 1

    if runs_root.exists():
        run_dirs = [path for path in runs_root.iterdir() if path.is_dir()]
        for path in list(run_dirs):
            if path.stat().st_mtime < cutoff:
                _remove_path(path)
                removed_runs += 1
        remaining_runs = [path for path in runs_root.iterdir() if path.is_dir()]
        for path in _trim_old_paths(
            remaining_runs, max_count=max(1, int(max_run_dirs))
        ):
            _remove_path(path)
            removed_runs += 1

    return {
        "removed_logs": removed_logs,
        "removed_runs": removed_runs,
        "logs_dir_exists": int(os.path.exists(logs_root)),
        "runs_dir_exists": int(os.path.exists(runs_root)),
    }
