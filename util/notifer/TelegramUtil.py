import requests

from util.notifer.Notifier import NotifierBase


class TelegramNotifier(NotifierBase):
    """Telegram Bot 通知器。

    使用 Telegram Bot API 发送通知消息。
    需要提前通过 @BotFather 创建 Bot 并获取 token，
    以及获取目标 chat_id（可以是用户 ID、群组 ID 或频道 ID）。
    """

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        title: str,
        content: str,
        interval_seconds: int = 10,
        duration_minutes: int = 10,
        http_proxy: str = "",
    ):
        super().__init__(title, content, interval_seconds, duration_minutes)
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.http_proxy = http_proxy

    def send_message(self, title: str, message: str) -> None:
        """发送 Telegram 消息，使用 HTML 格式以支持富文本。"""
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        text = f"<b>{title}</b>\n\n{message}"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
        }
        proxies = None
        if self.http_proxy:
            proxies = {"http": self.http_proxy, "https": self.http_proxy}
        response = requests.post(url, json=payload, timeout=15, proxies=proxies)
        response.raise_for_status()
