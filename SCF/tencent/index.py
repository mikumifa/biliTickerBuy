# -*- coding: utf8 -*-
import json
import time

import requests
from urllib.parse import urlencode, quote


class BiliRequest:
    def __init__(self, cookies_str=""):
        self.session = requests.Session()
        self.headers = {
            'accept': '*/*',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6,zh-TW;q=0.5,ja;q=0.4',
            'content-type': 'application/x-www-form-urlencoded',
            "cookie": cookies_str,
            "referer": "https://show.bilibili.com/",
            'priority': 'u=1, i',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0',
        }

    def get(self, url, data=None):
        response = self.session.get(url, data=data, headers=self.headers)
        response.raise_for_status()
        return response

    def post(self, url, data=None):
        response = self.session.post(url, data=data, headers=self.headers)
        response.raise_for_status()
        return response


def main_handler(event, context):
    ok, err = requestByConfig(event)
    return {
        "ok": ok,
        "err": err
    }


def format_dictionary_to_string(data):
    formatted_string_parts = []
    for key, value in data.items():
        if isinstance(value, list) or isinstance(value, dict):
            formatted_string_parts.append(
                f"{quote(key)}={quote(json.dumps(value, separators=(',', ':'), ensure_ascii=False))}"
            )
        else:
            formatted_string_parts.append(f"{quote(key)}={quote(str(value))}")

    formatted_string = "&".join(formatted_string_parts)
    return formatted_string


def requestByConfig(data):
    _request = BiliRequest(data["cookieStr"])
    payload = data["payload"]
    ret = _request.post(
        url=f"https://show.bilibili.com/api/ticket/order/createV2?project_id={data['project_id']}",
        data=payload,
    ).json()
    errno = int(ret["errno"])
    print(
        f'状态码: {errno}, 请求体: {ret}'
    )
    if errno == 0:
        return True, ret["data"]["orderId"]
