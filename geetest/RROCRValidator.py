from urllib import parse

import loguru
import requests
from retry import retry

from config import global_cookieManager, main_request
from geetest.Validator import Validator


class RROCRValidator(Validator):
    def need_api_key(self) -> bool:
        return True

    def have_gt_ui(self) -> bool:
        return True

    def __init__(self):
        self.url = "http://api.rrocr.com/api/recognize.html"
        self.headers = {
            "User-Agent": "Mozilla/5.0 Chrome/77.0.3865.120 Safari/537.36",
            "Accept": "text/html",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        self.cookieManager = global_cookieManager

    @retry(tries=10)
    def validate(self, appkey, gt, challenge, referer="http://www.baidu.com", ip='', host='') -> str:
        loguru.logger.info("start rrocr validate")
        if appkey is None or appkey == "":
            appkey = self.cookieManager.get_config_value("appkey", "")
        else:
            self.cookieManager.set_config_value("appkey", appkey)
        data = {
            "appkey": appkey,
            "gt": gt,
            "challenge": challenge,
            "referer": referer,
            "ip": ip,
            "host": host
        }
        data = parse.urlencode(data)
        response = requests.post(self.url, headers=self.headers, data=data)
        if response.status_code == 200:
            result = response.json()
            loguru.logger.info(result)
            if result.get("status") == 0:
                return result['data']['validate']
            else:
                raise ValueError(f"识别失败: {result.get('msg')}")
        else:
            raise ConnectionError(f"Request failed with status code: {response.status_code}")


if __name__ == "__main__":
    # 使用示例
    appkey = "e1db1bc497a8471c9479f600527ef56f"
    _request = main_request
    test_res = _request.get(
        "https://passport.bilibili.com/x/passport-login/captcha?source=main_web"
    ).json()
    challenge = test_res["data"]["geetest"]["challenge"]
    gt = test_res["data"]["geetest"]["gt"]
    loguru.logger.info(challenge)
    loguru.logger.info(gt)
    validator = RROCRValidator()
    try:
        validate_string = validator.validate(appkey, gt, challenge)
        print(f"Validation String: {validate_string}")
    except Exception as e:
        print(f"Error: {e}")
