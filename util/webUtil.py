import json
import logging
import threading
import time

from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait


class WebUtil:
    def __init__(self, cookie_dict):
        self.initialized_event = threading.Event()

        initialization_thread = threading.Thread(target=self.initialize, args=(cookie_dict,))
        initialization_thread.start()

    def initialize(self, cookie_dict):
        self.driver = webdriver.Edge()
        self.driver.get("https://show.bilibili.com/platform/home.html")

        for cookie in cookie_dict["bilibili_cookies"]:
            self.driver.add_cookie(cookie)
        self.driver.refresh()
        self.wait = WebDriverWait(self.driver, 0.5)
        self.initialized_event.set()
