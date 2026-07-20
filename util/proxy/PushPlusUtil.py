import json
import requests

from util.notifer.Notifier import NotifierBase, DEFAULT_HTTP_TIMEOUT


class PushPlusNotifier(NotifierBase):
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
        url = "http://www.pushplus.plus/send"
        headers = {"Content-Type": "application/json"}

        data = {"token": self.token, "content": message, "title": title}
        response = requests.post(
            url, headers=headers, data=json.dumps(data), timeout=self.timeout
        )
        response.raise_for_status()
