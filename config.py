import os
import sys


# 获取图标文件的路径
def get_application_path():
    if getattr(sys, "frozen", False):
        application_path = sys._MEIPASS
    else:
        application_path = os.path.dirname(os.path.abspath(__file__))

    return application_path


cookies_config_path = os.path.join(get_application_path(), "cookies.json")
issue_please_text = " (如果还无法解决, 请提交issue到仓库, 十分感谢)"
sleep_seconds = 1
