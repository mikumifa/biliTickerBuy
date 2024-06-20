import time

from loguru import logger
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.microsoft import EdgeChromiumDriverManager
from win10toast import ToastNotifier

from util.KVDatabase import KVDatabase

global_toaster = ToastNotifier()


class CookieManager:
    def __init__(self, config_file_path):
        self.db = KVDatabase(config_file_path)

    @logger.catch
    def _login_and_save_cookies(
            self, login_url="https://show.bilibili.com/platform/home.html"
    ):
        global_toaster.show_toast("BiliTickerBuy", "在浏览器内登录", duration=3, icon_path='')
        logger.info("启动浏览器中.....")
        try:
            self.driver = webdriver.Edge(service=EdgeService(EdgeChromiumDriverManager().install()))
        except Exception:
            try:
                self.driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()))
            except Exception:
                raise Exception(
                    "没有找到浏览器驱动\n"
                    "请直接升级系统到最新的windows系统（专业版\n"
                    "或者使用下面的替代方式： https://github.com/mikumifa/biliTickerBuy/discussions/119\n"
                )
        self.wait = WebDriverWait(self.driver, 0.5)
        self.driver.get(login_url)
        self.driver.maximize_window()
        time.sleep(1)
        self.driver.find_element(By.CLASS_NAME, "nav-header-register").click()
        logger.info("浏览器启动, 进行登录.")
        while True:
            try:
                self.driver.find_element(By.CLASS_NAME, "nav-header-register")
            except Exception as _:
                break
        time.sleep(1)
        self.db.insert("cookie", self.driver.get_cookies())
        self.driver.quit()
        logger.info("登录成功, 浏览器退出.")
        return self.db.get("cookie")

    def get_cookies(self, force=False):
        if force:
            return self.db.get("cookie")
        if not self.db.contains("cookie"):
            return self._login_and_save_cookies()
        else:
            return self.db.get("cookie")

    def have_cookies(self):
        return self.db.contains("cookie")

    def get_cookies_str(self):
        cookies = self.get_cookies()
        cookies_str = ""
        for cookie in cookies:
            cookies_str += cookie["name"] + "=" + cookie["value"] + "; "
        return cookies_str

    def get_cookies_value(self, name):
        cookies = self.get_cookies()
        for cookie in cookies:
            if cookie["name"] == name:
                return cookie["value"]
        return None

    def get_config_value(self, name, default=None):
        if self.db.contains(name):
            return self.db.get(name)
        else:
            return default

    def set_config_value(self, name, value):
        self.db.insert(name, value)

    def get_cookies_str_force(self):
        self._login_and_save_cookies()
        return self.get_cookies_str()
