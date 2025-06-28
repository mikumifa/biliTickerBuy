import json
import requests

from util.Notifier import NotifierBase


class BarkNotifier(NotifierBase):
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
        headers = {"Content-Type": "application/json"}
        data = {
            "icon": "https://raw.githubusercontent.com/mikumifa/biliTickerBuy/refs/heads/main/assets/icon.ico", # 推送LOGO
            "group": "biliTickerBuy",
            "url": f"https://mall.bilibili.com/neul/index.html?page=box_me&noTitleBar=1",  # 跳转会员购链接
            "sound": "telegraph",  # 警告铃声
            "level": "critical",  # 重要警告
            "volume": "10",
        }
        url = f"https://api.day.app/{self.token}/{title}/{message}"

        requests.post(url, headers=headers, data=json.dumps(data))


"""if __name__ == "__main__":

    my_bark_token = "jmGYKWhdpjJ89KxqZYJzzj"

    notifier = BarkNotifier(
        token=my_bark_token,
        title="商品监控",
        content="正在监控商品价格",
        interval_seconds=30,
        duration_minutes=60
    )

    notification_title_for_bark = "特价提醒"
    notification_message_content = "Nintendo Switch OLED 价格降至历史新低！赶紧去看看！"

    notifier.send_message(notification_title_for_bark, notification_message_content)
"""
