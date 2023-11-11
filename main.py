import logging
import sys
import time
import tkinter as tk
import logging
import os
import sys

from menu.TicketOptions import TicketOptionsApp


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


if __name__ == '__main__':
    configure_global_logging()
    root = tk.Tk()
    numberInputApp = TicketOptionsApp(root)
    root.mainloop()
