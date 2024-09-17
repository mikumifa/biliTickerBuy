import json
import os

import loguru
import playsound
import requests

from config import TEMP_PATH


def send_message(token, desp, title):
    try:
        url = f"https://sctapi.ftqq.com/{token}.send"
        headers = {
            "Content-Type": "application/json"
        }

        data = {
            "desp": desp,
            "title": title
        }
        requests.post(url, headers=headers, data=json.dumps(data))
    except Exception as e:
        loguru.logger.info("ServerChan消息发送失败")


if __name__ == '__main__':
    playsound.playsound(os.path.join(TEMP_PATH, "default.mp3"))
