import time

import loguru
import requests
from retry import retry

from config import cookies_config_path, global_cookieManager
from geetest.Validator import Validator
from util.bili_request import BiliRequest


class CapSolverValidator(Validator):
    def __init__(self):
        self.cookieManager = global_cookieManager
        pass

    @retry()
    def validate(self, appkey, gt, challenge, referer="http://127.0.0.1:7860/") -> str:
        if appkey is None or appkey == "":
            appkey = self.cookieManager.get_config_value("appkey", "")
        else:
            self.cookieManager.set_config_value("appkey", appkey)
        payload = {
            "clientKey": appkey,
            "task": {
                "type": 'GeeTestTaskProxyLess',
                "websiteURL": referer,
                "gt": gt,
                "challenge": challenge,
            }}
        res = requests.post("https://api.capsolver.com/createTask", json=payload)
        resp = res.json()
        task_id = resp.get("taskId")
        if not task_id:
            raise ValueError("Failed to create task: " + res.text)
        loguru.logger.info(f"Got taskId: {task_id} / Getting result...")
        while True:
            time.sleep(1)
            payload = {"clientKey": appkey, "taskId": task_id}
            res = requests.post("https://api.capsolver.com/getTaskResult", json=payload)
            resp = res.json()
            status = resp.get("status")
            if status == "ready":
                loguru.logger.info(resp)
                return resp.get("solution")['validate']
            if status == "failed" or resp.get("errorId"):
                loguru.logger.info(resp)
                raise ValueError("Solve failed! response: " + res.text)
            if status == "processing":
                continue


if __name__ == "__main__":
    # 使用示例
    appkey = "xxxxxxxxxxxxxxxxxxx"
    _request = BiliRequest(cookies_config_path=cookies_config_path)
    test_res = _request.get(
        "https://passport.bilibili.com/x/passport-login/captcha?source=main_web"
    ).json()
    challenge = test_res["data"]["geetest"]["challenge"]
    gt = test_res["data"]["geetest"]["gt"]
    loguru.logger.info(challenge)
    loguru.logger.info(gt)
    validator = CapSolverValidator()
    try:
        validate_string = validator.validate(appkey, gt, challenge)
        print(f"Validation String: {validate_string}")
    except Exception as e:
        print(f"Error: {e}")
