from dataclasses import dataclass, field
from functools import wraps
import os
import re
import sys
import time
from typing import Any, Callable
import loguru
from util.Storage.KVDatabase import KVDatabase
from util.log.LogConfig import loguru_config
from util.TimeUtil import TimeUtil
from util.ErrorCodes import ERRNO_DICT
from util.request.BiliRequest import BiliRequest


def get_application_path() -> str:
    if getattr(sys, "frozen", False):
        application_path = getattr(
            sys,
            "_MEIPASS",
            os.path.abspath(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            ),
        )
    else:
        application_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    return application_path


def get_exec_path() -> str:
    if len(sys.argv[0]) > 0 and sys.argv[0].endswith(
        ".py"
    ):  # sometime, argv[0] of `python main.py` is main.py
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    else:
        return os.path.dirname(os.path.realpath(sys.executable))


EXE_PATH: str = get_exec_path()  # 应用目录


def get_application_tmp_path() -> str:
    os.makedirs(os.path.join(EXE_PATH, "tmp"), exist_ok=True)
    return os.path.join(EXE_PATH, "tmp")


TEMP_PATH: str = get_application_tmp_path()  # 临时目录
os.environ["GRADIO_TEMP_DIR"] = TEMP_PATH
LOG_DIR: str = os.environ.get("BTB_LOG_DIR", os.path.join(EXE_PATH, "btb_logs"))
os.makedirs(LOG_DIR, exist_ok=True)
log_file_name = os.environ.get("BTB_APP_LOG_NAME", "app.log")
log_file_name = re.sub(r"[^\w.\-]", "_", log_file_name) or "app.log"
loguru_config(LOG_DIR, log_file_name, enable_console=True, file_colorize=False)

__all__ = [
    "TEMP_PATH",
    "EXE_PATH",
    "ERRNO_DICT",
    "ConfigDB",
    "GLOBAL_COOKIE_PATH",
    "main_request",
    "set_main_request",
    "time_service",
    "LOG_DIR",
    "GlobalStatusInstance",
    "runtime_state_reader",
    "runtime_state_writer",
]
loguru.logger.debug(f"设置路径EXE_PATH={EXE_PATH}")
CONFIG_DB_PATH = os.environ.get(
    "BTB_CONFIG_PATH", os.path.join(EXE_PATH, "config.json")
)
GLOBAL_COOKIE_PATH = os.environ.get(
    "BTB_COOKIES_PATH", os.path.join(EXE_PATH, "cookies.json")
)
ConfigDB = KVDatabase(CONFIG_DB_PATH)
if ConfigDB.get("cookies_path") is None:
    ConfigDB.insert("cookies_path", GLOBAL_COOKIE_PATH)
main_request = BiliRequest(cookies_config_path=ConfigDB.get("cookies_path"))


def set_main_request(request):
    global main_request
    main_request = request


time_service = TimeUtil()
if os.environ.get("BTB_SKIP_INITIAL_TIME_SYNC") == "1":
    time_service.set_timeoffset("0")
else:
    time_service.sync_time(check_bili=False)


@dataclass
class TaskLogEntry:
    title: str
    mode: str
    log_file: str
    created_at: float
    pid: int | None = None
    status: str = "运行中"
    finished_at: float | None = None
    payment_qr_url: str | None = None


@dataclass
class RuntimeStateStore:
    values: dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any) -> None:
        self.values[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def delete(self, key: str) -> None:
        self.values.pop(key, None)

    def set_path_list(self, key: str, files: list[str] | None, limit: int = 50) -> None:
        normalized: list[str] = []
        for file in files or []:
            if not file or not isinstance(file, str):
                continue
            if not os.path.exists(file):
                continue
            normalized.append(file)
        self.values[key] = normalized[:limit]

    def get_path_list(self, key: str, limit: int = 50) -> list[str]:
        files = self.values.get(key, [])
        if not isinstance(files, list):
            return []
        normalized = [
            file for file in files if isinstance(file, str) and os.path.exists(file)
        ][:limit]
        self.values[key] = normalized
        return list(normalized)


@dataclass
class GlobalStatus:
    nowTask: str = "none"
    task_logs: list[TaskLogEntry] = field(default_factory=list)
    runtime_state: RuntimeStateStore = field(default_factory=RuntimeStateStore)

    def state_set(self, key: str, value: Any) -> None:
        self.runtime_state.set(key, value)

    def state_get(self, key: str, default: Any = None) -> Any:
        return self.runtime_state.get(key, default)

    def state_delete(self, key: str) -> None:
        self.runtime_state.delete(key)

    def state_set_path_list(
        self, key: str, files: list[str] | None, limit: int = 50
    ) -> None:
        self.runtime_state.set_path_list(key, files, limit=limit)

    def state_get_path_list(self, key: str, limit: int = 50) -> list[str]:
        return self.runtime_state.get_path_list(key, limit=limit)

    def set_uploaded_config_files(self, files: list[str] | None) -> None:
        self.state_set_path_list("go.uploaded_config_files", files)

    def get_uploaded_config_files(self) -> list[str]:
        return self.state_get_path_list("go.uploaded_config_files")

    def register_task_log(
        self, title: str, mode: str, log_file: str, pid: int | None = None
    ) -> None:
        self.task_logs.insert(
            0,
            TaskLogEntry(
                title=title,
                mode=mode,
                log_file=log_file,
                created_at=time.time(),
                pid=pid,
                status="运行中",
            ),
        )
        self.task_logs = self.task_logs[:50]

    def get_task_logs(self) -> list[TaskLogEntry]:
        return list(self.task_logs)

    def get_task_log(self, pid: int) -> TaskLogEntry | None:
        for entry in self.task_logs:
            if entry.pid == pid:
                return entry
        return None

    def remove_task_log(self, pid: int) -> None:
        self.task_logs = [entry for entry in self.task_logs if entry.pid != pid]

    def remove_task_logs_by_paths(self, log_files: list[str] | set[str]) -> None:
        normalized = {os.path.abspath(path) for path in log_files}
        self.task_logs = [
            entry
            for entry in self.task_logs
            if os.path.abspath(entry.log_file) not in normalized
        ]

    def update_task_log_status(self, pid: int, status: str) -> None:
        for entry in self.task_logs:
            if entry.pid == pid:
                entry.status = status
                if status != "运行中":
                    entry.finished_at = time.time()
                return


GlobalStatusInstance = GlobalStatus()


def runtime_state_reader(
    key: str,
    *,
    kind: str = "value",
    default: Any = None,
    limit: int = 50,
):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            fallback = func(*args, **kwargs)
            if kind == "path_list":
                files = GlobalStatusInstance.state_get_path_list(key, limit=limit)
                return files if files else (fallback or [])
            value = GlobalStatusInstance.state_get(key, default)
            return fallback if value is None else value

        return wrapper

    return decorator


def runtime_state_writer(
    key: str,
    *,
    kind: str = "value",
    arg_index: int = 0,
    limit: int = 50,
    value_getter: Callable[[tuple[Any, ...], dict[str, Any], Any], Any] | None = None,
):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            if value_getter is not None:
                value = value_getter(args, kwargs, result)
            elif len(args) > arg_index:
                value = args[arg_index]
            else:
                value = None

            if kind == "path_list":
                GlobalStatusInstance.state_set_path_list(key, value, limit=limit)
            else:
                GlobalStatusInstance.state_set(key, value)
            return result

        return wrapper

    return decorator
