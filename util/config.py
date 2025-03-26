import os

import loguru

from const import APP_PATH, BASE_DIR, TEMP_PATH
from util.BiliRequest import BiliRequest
from util.KVDatabase import KVDatabase
from util.TimeService import TimeService

loguru.logger.debug(f"设置路径, APP_PATH={APP_PATH} TEMP_PATH={TEMP_PATH} BASE_DIR={BASE_DIR}")
configDB = KVDatabase(os.path.join(BASE_DIR, "config.json"))
global_cookie_path = os.path.join(BASE_DIR, "cookies.json")
main_request = BiliRequest(cookies_config_path=global_cookie_path)


def set_main_request(request):
    global main_request
    main_request = request


## 时间
time_service = TimeService()
time_service.set_timeoffset(time_service.compute_timeoffset())
