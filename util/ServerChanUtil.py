import json

import loguru
import requests


def send_message(token, desp, title):
    try:
        url = f"https://sctapi.ftqq.com/{token}.send"
        headers = {"Content-Type": "application/json"}

        data = {"desp": desp, "title": title}
        requests.post(url, headers=headers, data=json.dumps(data))
    except Exception as e:
        loguru.logger.info("ServerChan消息发送失败")
