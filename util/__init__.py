from collections import namedtuple
from dataclasses import dataclass, field
import os
import sys
import time
import loguru
import importlib
from typing import Any, Optional
from loguru import logger
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


FILES_ROOT_PATH: str = get_application_path()  # 文件根目录


def get_application_tmp_path() -> str:
    os.makedirs(os.path.join(FILES_ROOT_PATH, "tmp"), exist_ok=True)
    return os.path.join(FILES_ROOT_PATH, "tmp")

def get_exec_path() -> str:
    if len(sys.argv[0]) > 0 and sys.argv[0].endswith(".py"):    # sometime, argv[0] of `python main.py` is main.py
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    else:
        return os.path.dirname(os.path.realpath(sys.executable))


EXE_PATH: str = get_exec_path()  # 应用目录

TEMP_PATH: str = get_application_tmp_path()  # 临时目录
LOG_DIR: str = os.path.join(EXE_PATH, "btb_logs")
loguru_config(LOG_DIR, "app.log", enable_console=True, file_colorize=False)
ERRNO_DICT = {
    0: "成功",
    3: "抢票CD中",
    100009: "库存不足,暂无余票",
    100001: "无票",
    100041: "对未发售的票进行抢票",
    100003: "验证码过期",
    100016: "项目不可售",
    100039: "活动收摊啦,下次要快点哦",
    100048: "已经下单，有尚未完成订单",
    100017: "票种不可售",
    100051: "订单准备过期，重新验证",
    100034: "票价错误",
}

__all__ = [
    "FILES_ROOT_PATH",
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
]
loguru.logger.debug(
    f"设置路径, FILES_ROOT_PATH={FILES_ROOT_PATH} TEMP_PATH={TEMP_PATH} EXE_PATH={EXE_PATH}"
)
ConfigDB = KVDatabase(os.path.join(EXE_PATH, "config.json"))
GLOBAL_COOKIE_PATH = os.path.join(EXE_PATH, "cookies.json")
if ConfigDB.get("cookies_path") is None:
    ConfigDB.insert("cookies_path", GLOBAL_COOKIE_PATH)
main_request = BiliRequest(cookies_config_path=ConfigDB.get("cookies_path"))


def set_main_request(request):
    global main_request
    main_request = request


time_service = TimeUtil()
time_service.set_timeoffset(time_service.compute_timeoffset())


global bili_ticket_gt_python
bili_ticket_gt_python: Optional[Any] = None
try:
    bili_ticket_gt_python = importlib.import_module("bili_ticket_gt_python")
except Exception as e:
    logger.error(f"本地验证码模块加载失败，错误信息：{e}")
    logger.error("请更换设备")

Endpoint = namedtuple("Endpoint", ["endpoint", "detail", "update_at"])


@dataclass
class GlobalStatus:
    nowTask: str = "none"
    endpoint_details: dict[str, Endpoint] = field(default_factory=dict)

    def available_endpoints(self) -> list[Endpoint]:
        return [
            t
            for endpoint, t in self.endpoint_details.items()
            if time.time() - t.update_at < 4
        ]


GlobalStatusInstance = GlobalStatus()
