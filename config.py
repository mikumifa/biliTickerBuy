import os

import loguru

from path import APP_PATH, BASE_DIR, TEMP_PATH
from util.BiliRequest import BiliRequest
from util.KVDatabase import KVDatabase
from util.TimeService import TimeService

loguru.logger.info(f"设置路径, APP_PATH={APP_PATH} TEMP_PATH={TEMP_PATH} BASE_DIR={BASE_DIR}")
configDB = KVDatabase(os.path.join(BASE_DIR, "config.json"))
if not configDB.contains("cookie_path"):
    configDB.insert("cookie_path", os.path.join(BASE_DIR, "cookies.json"))
main_request = BiliRequest(cookies_config_path=configDB.get("cookie_path"))
global_cookieManager = main_request.cookieManager

## 时间
time_service = TimeService()
time_service.set_timeoffset(time_service.compute_timeoffset())
