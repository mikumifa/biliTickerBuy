import requests
import json
from typing import Tuple
import time


class Slide:
    def register(self) -> Tuple[str, str]:
        url = "http://127.0.0.1:5000/pc-geetest/register?t=" + str(int(time.time() * 1000))
        # url = "https://www.geetest.com/demo/gt/register-slide?t=" + str(int(time.time() * 1000))
        res = requests.get(url=url).json()
        print(res)
        return (res['challenge'], res['gt'])

    def get_c_s(self, challenge: str, gt: str, w: str) -> Tuple[list, str]:
        url = "https://api.geetest.com/get.php"
        # url = "https://apiv6.geetest.com/get.php"
        res = requests.get(url=url, params={
            "gt": gt,
            "challenge": challenge,
            "lang": "zh-cn",
            "pt": 0,
            "client_type": "web",
            "w": w,
        }).text
        res = json.loads(res.strip('()'))['data']
        # print(res)
        return (res['c'], res['s'])

    def get_type(self, challenge: str, gt: str, w: str):
        url = "http://api.geevisit.com/ajax.php"
        res = requests.get(url=url, params={
            "gt": gt,
            "challenge": challenge,
            "w": w
        })

    def get_new_c_s_challenge_bg_slice(self, challenge: str, gt: str, ) -> Tuple[str, str, str, str, str]:
        url = "http://api.geevisit.com/get.php"
        res = requests.get(url=url, params={
            "gt": gt,
            "challenge": challenge,
            "is_next": "true",
            "offline": "false",
            "type": "slide3",
            "isPC": "true",
            "product": "embed",
            "autoReset": "true",
            "api_server": "api.geevisit.com",
            "protocol": "http://",
            "width": "100%",
            "callback": "geetest_1715753608245",
        }).text
        res = res.strip('geetest_1715753608245')
        res = res.strip('()')
        res = json.loads(res)
        print(res)
        return (res['c'], res['s'], res['challenge'],
                'https://' + res['static_servers'][0] + res['bg'],
                'https://' + res['static_servers'][0] + res['slice'])

    def ajax(self, challenge: str, gt: str, w: str):
        url = "http://api.geevisit.com/ajax.php"
        res = requests.get(url=url, params={
            "gt": gt,
            "challenge": challenge,
            "w": w,
        }).text
        res = res.strip('()')
        res = json.loads(res)
        print(res)
        return res


class Click:
    def register(self) -> Tuple[str, str]:
        url = "https://account.geetest.com/api/captchademo?captcha_type=click"
        res = requests.get(url=url).json()
        res = res["data"]
        print(res)
        return (res['challenge'], res['gt'])

    def get_c_s(self, challenge: str, gt: str, w: str) -> Tuple[list, str]:
        url = "https://api.geetest.com/get.php"
        # url = "https://apiv6.geetest.com/get.php"
        res = requests.get(url=url, params={
            "gt": gt,
            "challenge": challenge,
            "lang": "zh-cn",
            "pt": 0,
            "client_type": "web",
            "w": w,
        }).text
        res = json.loads(res.strip('()'))['data']
        # print(res)
        return (res['c'], res['s'])

    def get_type(self, challenge: str, gt: str, w: str):
        url = "http://api.geevisit.com/ajax.php"
        res = requests.get(url=url, params={
            "gt": gt,
            "challenge": challenge,
            "w": w
        })

    def get_new_c_s_pic(self, challenge: str, gt: str, ) -> Tuple[str, str, str]:
        url = "http://api.geevisit.com/get.php"
        res = requests.get(url=url, params={
            "gt": gt,
            "challenge": challenge,
            "is_next": "true",
            "offline": "false",
            "type": "slide3",
            "isPC": "true",
            "product": "embed",
            "autoReset": "true",
            "api_server": "api.geevisit.com",
            "protocol": "http://",
            "width": "100%",
            "callback": "geetest_1715753608245",
        }).text
        res = res.strip('geetest_1715753608245')
        res = res.strip('()')
        res = json.loads(res)
        res = res["data"]
        print(res)
        return (res['c'], res['s'],
                'https://' + res['static_servers'][0] + res['pic'],)

    def ajax(self, challenge: str, gt: str, w: str):
        url = "http://api.geevisit.com/ajax.php"
        res = requests.get(url=url, params={
            "gt": gt,
            "challenge": challenge,
            "w": w,
        }).text
        res = res.strip('()')
        res = json.loads(res)
        return res
