import time

import bili_ticket_gt_python
import loguru
from retry import retry

from config import cookies_config_path
from geetest.Validator import Validator
from util.bili_request import BiliRequest


class AmorterValidator(Validator):
    def __init__(self):
        self.click = bili_ticket_gt_python.ClickPy()
        pass

    @retry()
    def validate(self, appkey, gt, challenge, referer="http://127.0.0.1:7860/") -> str:
        try:
            (_, _) = self.click.get_c_s(gt, challenge)
            _type = self.click.get_type(gt, challenge)
            if _type != "click":
                raise Exception("验证码类型错误")
            (c, s, args) = self.click.get_new_c_s_args(gt, challenge)
            before_calculate_key = time.time()
            key = self.click.calculate_key(args)
            # rt固定即可
            # 此函数是使用项目目录下的click.exe生成w参数，如果文件不存在会报错，你也可以自己接入生成w的逻辑函数
            w = self.click.generate_w(key, gt, challenge, str(c), s, "abcdefghijklmnop")
            # 点选验证码生成w后需要等待2秒提交
            w_use_time = time.time() - before_calculate_key
            loguru.logger.info(f"w生成时间：{w_use_time}")
            if w_use_time < 2:
                time.sleep(2 - w_use_time)
            (msg, validate) = self.click.verify(gt, challenge, w)
            loguru.logger.info(f"msg: {msg} ; validate: {validate}")
            return validate
        except Exception as e:
            loguru.logger.warning(e)
            raise e


if __name__ == "__main__":
    # 使用示例
    appkey = "xxxxxxxxxxxxxxxxxxx"
    _request = BiliRequest(cookies_config_path=cookies_config_path)
    test_res = _request.get(
        "https://passport.bilibili.com/x/passport-login/captcha?source=main_web"
    ).json()
    challenge = test_res["data"]["geetest"]["challenge"]
    gt = test_res["data"]["geetest"]["gt"]

    validator = AmorterValidator()
    try:
        validate_string = validator.validate(appkey, gt, challenge)
        print(f"Validation String: {validate_string}")
    except Exception as e:
        print(f"Error: {e}")
