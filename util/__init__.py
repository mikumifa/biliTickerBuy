from collections import namedtuple
from dataclasses import dataclass, field
import os
import re
import sys
import time
from urllib.parse import urlsplit, urlunsplit
import loguru
from util.BiliRequest import BiliRequest
from util.KVDatabase import KVDatabase
from util.LogConfig import loguru_config
from util.TimeUtil import TimeUtil


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
ERRNO_DICT = {
    0: "成功",
    3: "下单过于频繁，请稍后再试",
    100001: "暂无可售票或登录状态异常",
    100041: "未到开票时间",
    100044: "需要完成人机验证",
    100003: "验证码过期",
    100016: "项目不可售",
    100039: "活动收摊啦,下次要快点哦",
    100048: "已经下单，有尚未完成订单",
    100017: "票种不可售",
    100051: "订单准备过期，重新验证",
    100034: "票价错误",
    100009: "库存不足",
    219: "下单失败，请重试",
    221: "下单请求过多，请稍后再试",
    900001: "下单过快，被系统限制",
    900002: "当前请求较多，请稍后再试",
}

__all__ = [
    "TEMP_PATH",
    "EXE_PATH",
    "ERRNO_DICT",
    "build_public_url",
    "ConfigDB",
    "GLOBAL_COOKIE_PATH",
    "main_request",
    "set_main_request",
    "time_service",
    "LOG_DIR",
    "GlobalStatusInstance",
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
time_service.set_timeoffset(time_service.compute_timeoffset())


def build_public_url(local_url: str, server_name: str | None = None) -> str:
    if not local_url:
        return local_url

    if not server_name or not str(server_name).strip():
        return local_url

    parsed_local = urlsplit(local_url)
    if not parsed_local.scheme or not parsed_local.netloc:
        return local_url

    raw_server_name = str(server_name).strip()
    parsed_server = urlsplit(raw_server_name)
    host = parsed_server.hostname or raw_server_name
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"

    port = parsed_local.port
    netloc = host if port is None else f"{host}:{port}"
    return urlunsplit(
        (
            parsed_local.scheme,
            netloc,
            parsed_local.path,
            parsed_local.query,
            parsed_local.fragment,
        )
    )


Endpoint = namedtuple("Endpoint", ["endpoint", "detail", "update_at"])


@dataclass
class TaskLogEntry:
    title: str
    mode: str
    log_file: str
    created_at: float
    pid: int | None = None


@dataclass
class GlobalStatus:
    nowTask: str = "none"
    master_endpoint_url: str = ""
    endpoint_details: dict[str, Endpoint] = field(default_factory=dict)
    task_logs: list[TaskLogEntry] = field(default_factory=list)

    def available_endpoints(self) -> list[Endpoint]:
        return [
            t
            for endpoint, t in self.endpoint_details.items()
            if time.time() - t.update_at < 4
        ]

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
            ),
        )
        self.task_logs = self.task_logs[:50]

    def get_task_logs(self) -> list[TaskLogEntry]:
        return list(self.task_logs)


GlobalStatusInstance = GlobalStatus()
