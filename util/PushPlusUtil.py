import json
import requests

from util.Notifier import NotifierBase

class PushPlusNotifier(NotifierBase):
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
        url = "http://www.pushplus.plus/send"
        headers = {"Content-Type": "application/json"}

        data = {"token": self.token, "content": message, "title": title}
        requests.post(url, headers=headers, data=json.dumps(data))