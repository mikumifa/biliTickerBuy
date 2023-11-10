import logging
import os
import sys


def configure_global_logging():
    # 获取打包后可执行文件的路径
    if getattr(sys, 'frozen', False):
        application_path = sys._MEIPASS
    else:
        application_path = os.path.dirname(os.path.abspath(__file__))

    global_logger = logging.getLogger()
    global_logger.setLevel(logging.DEBUG)
    log_file_path = os.path.join(application_path, 'log', 'log.txt')
    file_handler = logging.FileHandler(log_file_path)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    global_logger.addHandler(file_handler)


# 获取图标文件的路径
def get_application_path():
    if getattr(sys, 'frozen', False):
        application_path = sys._MEIPASS
    else:
        application_path = os.path.dirname(os.path.abspath(__file__))

    return application_path


cookies_config_path = os.path.join(get_application_path(), 'config', 'cookies.json')
issue_please_text = " (如果还无法解决, 请提交issue到仓库, 十分感谢)"
sleep_seconds = 0.5
