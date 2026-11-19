from threading import RLock
from urllib.parse import unquote_plus, urlsplit
from uuid import uuid4

import requests
from loguru import logger

from app_cmd.config.NotifierConfig import BarkLevel, DEFAULT_BARK_LEVEL
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
        *,
        level: BarkLevel = DEFAULT_BARK_LEVEL,
        notification_id: str | None = None,
    ):
        super().__init__(title, content, interval_seconds, duration_minutes, timeout)
        self.token = token
        self.level = level
        self._notification_id = notification_id
        self._send_lock = RLock()
        self._delivered = False

    def send_once_sync(
        self, title, message, retries: int = 3, backoff: float = 0.5
    ) -> bool:
        with self._send_lock:
            if self._delivered:
                logger.info("Bark 通知已确认送达")
                return True
            return super().send_once_sync(
                title, message, retries=retries, backoff=backoff
            )

    def send_message(self, title, message):
        data = {
            "title": title,
            "body": message,
            "icon": "https://raw.githubusercontent.com/mikumifa/biliTickerBuy/refs/heads/main/assets/icon.ico",  # 推送LOGO
            "group": "biliTickerBuy",
            "url": "https://mall.bilibili.com/neul/index.html?page=box_me&noTitleBar=1",  # 跳转会员购链接
            "level": self.level,
            "id": self._notification_id or uuid4().hex,
        }
        if self.level == "critical":
            data.update(sound="telegraph", volume="10")
        token = str(self.token).strip()
        endpoint = urlsplit(token)
        if endpoint.scheme in {"http", "https"}:
            # Bark gives query parameters priority over JSON fields.
            push_params = data.keys() | {"sound", "soundurl", "volume", "call"}
            query = "&".join(
                parameter
                for parameter in endpoint.query.split("&")
                if unquote_plus(parameter.partition("=")[0]).lower() not in push_params
            )
            url = endpoint._replace(
                path=endpoint.path.rstrip("/"), query=query, fragment=""
            ).geturl()
        else:
            url = f"https://api.day.app/{token}"

        # The background sender and synchronous fallback share one delivery result.
        with self._send_lock:
            if self._delivered:
                return
            response = requests.post(url, json=data, timeout=self.timeout)
            response.raise_for_status()
            self._delivered = self._notification_id is not None
