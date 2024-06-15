import bili_ticket_gt_python
import loguru
import threading

from config import cookies_config_path
from geetest.Validator import Validator
from util.bili_request import BiliRequest


class AmorterValidator(Validator):
    def need_api_key(self) -> bool:
        return False

    def have_gt_ui(self) -> bool:
        return False

    def __init__(self):
        self.click = bili_ticket_gt_python.ClickPy()
        pass

    def validate(self, appkey, gt, challenge, referer="http://127.0.0.1:7860/") -> str:
        try:
            loguru.logger.info(f"AmorterValidator gt: {gt} ; challenge: {challenge}")
            validate = self.click.simple_match_retry(gt, challenge)
            loguru.logger.info(f"AmorterValidator: {validate}")
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

    try:
        def validate_task():
            validator = AmorterValidator()
            validate_string = validator.validate(appkey, gt, challenge)
            print(f"Validation result: {validate_string}")

        # 创建一个线程来运行验证函数
        validation_thread = threading.Thread(target=validate_task)
        # 启动线程
        validation_thread.start()
        validation_thread.join()
    except Exception as e:
        print(f"Error: {e}")
