import requests

from util.configUtil import CookieManager


class BiliRequest:
    def __init__(self, headers=None, cookies=None, cookies_config_path=""):
        self.session = requests.Session()
        self.cookieManager = CookieManager(cookies_config_path)
        self._cookies = self.cookieManager.get_cookies_str()
        self.headers = headers or {
            'authority': 'show.bilibili.com',
            'accept': '*/*',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6,zh-TW;q=0.5,ja;q=0.4',
            'cookie': self._cookies,
            'referer': "https://show.bilibili.com/",
            'content-type': 'application/x-www-form-urlencoded',
            'sec-ch-ua': '"Microsoft Edge";v="119", "Chromium";v="119", "Not?A_Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0'
        }

    def get(self, url, data=None):
        response = self.session.get(url, data=data, headers=self.headers)
        response.raise_for_status()
        if response.json()["msg"] == "请先登录":
            self.headers['cookies'] = self.cookieManager.get_cookies_str_force()
            self.get(url, data)
        return response

    def post(self, url, data=None):
        response = self.session.post(url, data=data, headers=self.headers)
        response.raise_for_status()
        if response.json()["msg"] == "请先登录":
            self.headers['cookies'] = self.cookieManager.get_cookies_str_force()
            self.post(url, data)
        return response


if __name__ == '__main__':
    payload = {}
    _request = BiliRequest(cookies_config_path="../config/cookies.json")
    res = _request.get(url="https://show.bilibili.com/api/ticket/project/get?version=134&id=77938&project_id=77938")
    print(res.json()["data"])
