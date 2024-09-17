import os
import sys

import loguru

from util.BiliRequest import BiliRequest
from util.KVDatabase import KVDatabase
from util.TimeService import TimeService


# 创建通知器实例

# 获取图标文件的路径
def get_application_path():
    if getattr(sys, "frozen", False):
        application_path = getattr(sys, '_MEIPASS', os.path.abspath(os.path.dirname(__file__)))
    else:
        application_path = os.path.dirname(os.path.abspath(__file__))

    return application_path


APP_PATH = get_application_path()


def get_application_tmp_path():
    os.makedirs(os.path.join(APP_PATH, "tmp"), exist_ok=True)
    return os.path.join(APP_PATH, "tmp")


TEMP_PATH = get_application_tmp_path()
BASE_DIR = os.path.dirname(os.path.realpath(sys.executable))

loguru.logger.info(f"设置路径, APP_PATH={APP_PATH} TEMP_PATH={TEMP_PATH} BASE_DIR={BASE_DIR}")
configDB = KVDatabase(os.path.join(BASE_DIR, "config.json"))
if not configDB.contains("cookie_path"):
    configDB.insert("cookie_path", os.path.join(BASE_DIR, "cookies.json"))
main_request = BiliRequest(cookies_config_path=configDB.get("cookie_path"))
global_cookieManager = main_request.cookieManager

## 时间
time_service = TimeService()
time_service.set_timeoffset(time_service.compute_timeoffset())
