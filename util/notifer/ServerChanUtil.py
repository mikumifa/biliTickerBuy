import json
import requests

from util.notifer.Notifier import NotifierBase, DEFAULT_HTTP_TIMEOUT


class ServerChanTurboNotifier(NotifierBase):
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
        url = f"https://sctapi.ftqq.com/{self.token}.send"
        headers = {"Content-Type": "application/json"}

        data = {"desp": message, "title": title}
        response = requests.post(
            url, headers=headers, data=json.dumps(data), timeout=self.timeout
        )
        response.raise_for_status()


class ServerChan3Notifier(NotifierBase):
    def __init__(
        self,
        api_url,
        title,
        content,
        interval_seconds=10,
        duration_minutes=10,
        timeout=DEFAULT_HTTP_TIMEOUT,
    ):
        super().__init__(title, content, interval_seconds, duration_minutes, timeout)
        self.api_url = api_url

    def send_message(self, title, message):
        headers = {"Content-Type": "application/json"}
        data = {"title": title, "desp": message}
        response = requests.post(
            self.api_url,
            headers=headers,
            data=json.dumps(data),
            timeout=self.timeout,
        )
        response.raise_for_status()
