from threading import RLock
from urllib.parse import SplitResult, quote, unquote_plus, urljoin, urlsplit
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
        volume=10,
        *,
        level: BarkLevel = DEFAULT_BARK_LEVEL,
        notification_id: str | None = None,
    ):
        super().__init__(title, content, interval_seconds, duration_minutes, timeout)
        self.token = token
        self.volume = self._normalize_volume(volume)
        self.level = level
        self._notification_id = notification_id
        self._send_lock = RLock()
        self._delivered = False

    @staticmethod
    def _normalize_volume(value) -> int:
        """Bark critical volume, range 0-10. Invalid input falls back to 10."""
        try:
            parsed = int(float(value))
        except (TypeError, ValueError):
            return 10
        return max(0, min(10, parsed))

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
            data.update(sound="telegraph", volume=str(self.volume))

        token = str(self.token).strip()
        endpoint = urlsplit(token)
        if endpoint.scheme not in {"http", "https"}:
            endpoint = urlsplit(f"https://api.day.app/{token}")
        path = endpoint.path.rstrip("/")
        if endpoint.hostname == "api.day.app":
            # The public server uses /:key. Drop any example title or body.
            path = "/" + path.lstrip("/").partition("/")[0]
        elif "/" in path.lstrip("/"):
            # An extra segment may be example text or part of a proxy prefix.
            # Preserve the legacy route so the last segment is the new body.
            path = f"{path}/{quote(title, safe='')}/{quote(message, safe='')}"

        # The background sender and synchronous fallback share one delivery result.
        with self._send_lock:
            if self._delivered:
                return
            self._post_notification(endpoint._replace(path=path), data)
            self._delivered = self._notification_id is not None

    def _post_notification(self, endpoint: SplitResult, data: dict[str, str]) -> None:
        # Bark gives query parameters priority over JSON fields.
        push_params = data.keys() | {"sound", "soundurl", "volume", "call"}
        for _ in range(5):
            query = "&".join(
                parameter
                for parameter in endpoint.query.split("&")
                if unquote_plus(parameter.partition("=")[0]).lower() not in push_params
            )
            url = endpoint._replace(query=query, fragment="").geturl()
            response = requests.post(
                url, json=data, timeout=self.timeout, allow_redirects=False
            )
            response.raise_for_status()
            if 200 <= response.status_code < 300:
                return

            location = response.headers.get("Location")
            if response.status_code not in {301, 302, 307, 308} or not location:
                break
            target = urlsplit(urljoin(url, location))
            # Keep JSON on HTTP-to-HTTPS redirects that would become GET in Requests.
            if (
                target.scheme not in {"http", "https"}
                or not target.hostname
                or (endpoint.scheme == "https" and target.scheme == "http")
                or (
                    response.status_code in {301, 302}
                    and target.hostname != endpoint.hostname
                )
            ):
                break
            endpoint = target

        raise requests.exceptions.HTTPError(
            "Bark 推送地址无法完成 POST 重定向，请填写最终推送地址",
            response=response,
        )
