import loguru

from geetest.Validator import Validator, test_validator
from util.dynimport import bili_ticket_gt_python


class AmorterValidator(Validator):
    def need_api_key(self) -> bool:
        return False

    def have_gt_ui(self) -> bool:
        return False

    def __init__(self):
        self.click = bili_ticket_gt_python.ClickPy()
        pass

    def validate(self, gt, challenge) -> str:
        try:
            loguru.logger.debug(f"AmorterValidator gt: {gt} ; challenge: {challenge}")
            validate = self.click.simple_match_retry(gt, challenge)
            loguru.logger.info(f"本地验证码过码成功")
            return validate

        except Exception as e:
            loguru.logger.warning(e)
            raise e


if __name__ == "__main__":
    # 使用示例
    validator = AmorterValidator()
    test_validator(validator)
