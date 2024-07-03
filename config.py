import os
import sys
import time

import loguru
import ntplib

from util.BiliRequest import BiliRequest
from util.KVDatabase import KVDatabase


# 创建通知器实例

# 获取图标文件的路径
def get_application_path():
    if getattr(sys, "frozen", False):
        application_path = sys._MEIPASS
    else:
        application_path = os.path.dirname(os.path.abspath(__file__))

    return application_path


def get_application_tmp_path():
    os.makedirs(os.path.join(get_application_path(), "tmp"), exist_ok=True)
    return os.path.join(get_application_path(), "tmp")


configDB = KVDatabase(os.path.join(get_application_tmp_path(), "config.json"))
if not configDB.contains("cookie_path"):
    configDB.insert("cookie_path", os.path.join(get_application_tmp_path(), "cookies.json"))
main_request = BiliRequest(cookies_config_path=configDB.get("cookie_path"))
global_cookieManager = main_request.cookieManager

## 时间

global_cookieManager.set_config_value("timeoffset", 0)  # 时间补偿初始设置为0


def set_timeoffset(_timeoffset):
    try:
        loguru.logger.info("校准时间完成，使用ntp.aliyun.com时间")
        global_cookieManager.set_config_value("timeoffset", float(_timeoffset))
    except ValueError as e:
        loguru.logger.info("校准时间失败，使用本地时间")
        global_cookieManager.set_config_value("timeoffset", 0)


ntp_server = 'ntp.aliyun.com'
client = ntplib.NTPClient()
response = client.request(ntp_server, version=3)
ntp_time = response.tx_time
device_time = time.time()
time_diff = (device_time - ntp_time) * 1000
set_timeoffset(format(time_diff, '.2f'))
