import requests

from util.notifer.Notifier import NotifierBase


MEOW_API_BASE = "https://api.chuckfang.com"


class MeoWNotifier(NotifierBase):
    def __init__(
        self,
        nickname,
        title,
        content,
        interval_seconds=10,
        duration_minutes=10,
    ):
        super().__init__(title, content, interval_seconds, duration_minutes)
        self.nickname = str(nickname or "").strip().strip("/")

    def send_message(self, title, message):
        if not self.nickname:
            raise ValueError("MeoW nickname is required")

        response = requests.post(
            f"{MEOW_API_BASE}/{self.nickname}",
            json={"title": title, "msg": message},
            timeout=10,
        )
        response.raise_for_status()

        try:
            data = response.json()
        except ValueError as exc:
            raise RuntimeError(f"MeoW response is not JSON: {response.text}") from exc

        if data.get("status") != 200:
            raise RuntimeError(f"MeoW push failed: {data}")
