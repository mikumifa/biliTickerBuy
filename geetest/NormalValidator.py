from geetest.Validator import Validator


class NormalValidator(Validator):
    def need_api_key(self) -> bool:
        return False

    def have_gt_ui(self) -> bool:
        return True

    def __init__(self):
        pass

    def validate(self, appkey, gt, challenge, referer="http://www.baidu.com", ip='', host='') -> str:
        raise Exception("No validate")
