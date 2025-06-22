import json
import requests

from util.Notifier import NotifierBase

class ServerChanNotifier(NotifierBase):
    def __init__(
        self,
        token,
        title,
        content,
        interval_seconds=10,
        duration_minutes=10
    ):
        super().__init__(title, content, interval_seconds, duration_minutes)
        self.token = token

    def send_message(self, title, message):
        url = f"https://sctapi.ftqq.com/{self.token}.send"
        headers = {"Content-Type": "application/json"}

        data = {"desp": message, "title": title}
        requests.post(url, headers=headers, data=json.dumps(data))
