# 创建通知器实例
import os
import sys


# 获取图标文件的路径
def get_application_path() -> str:
    if getattr(sys, "frozen", False):
        application_path = getattr(sys, '_MEIPASS', os.path.abspath(os.path.dirname(__file__)))
    else:
        application_path = os.path.dirname(os.path.abspath(__file__))

    return application_path


APP_PATH: str = get_application_path()


def get_application_tmp_path() -> str:
    os.makedirs(os.path.join(APP_PATH, "tmp"), exist_ok=True)
    return os.path.join(APP_PATH, "tmp")


TEMP_PATH: str = get_application_tmp_path()
BASE_DIR: str = os.path.dirname(os.path.realpath(sys.executable))
