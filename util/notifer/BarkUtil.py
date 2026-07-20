import json
import requests

from urllib.parse import urlparse
from util.notifer.Notifier import NotifierBase, DEFAULT_HTTP_TIMEOUT


class BarkNotifier(NotifierBase):
    def __init__(
        self,
        token,
        title,
        content,
        interval_seconds=10,
        duration_minutes=10,
        timeout=DEFAULT_HTTP_TIMEOUT,
    ):
        super().__init__(title, content, interval_seconds, duration_minutes, timeout)
        self.token = token

    def send_message(self, title, message):
        headers = {"Content-Type": "application/json"}
        data = {
            "icon": "https://raw.githubusercontent.com/mikumifa/biliTickerBuy/refs/heads/main/assets/icon.ico",  # 推送LOGO
            "group": "biliTickerBuy",
            "url": "https://mall.bilibili.com/neul/index.html?page=box_me&noTitleBar=1",  # 跳转会员购链接
            "sound": "telegraph",  # 警告铃声
            "level": "critical",  # 重要警告
            "volume": "10",
        }
        if isinstance(self.token, str) and urlparse(self.token).scheme in {
            "http",
            "https",
        }:
            url = f"{self.token.rstrip('/')}/{title}/{message}"
        else:
            url = f"https://api.day.app/{self.token}/{title}/{message}"

        response = requests.post(
            url, headers=headers, data=json.dumps(data), timeout=self.timeout
        )
        response.raise_for_status()
