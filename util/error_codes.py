class ErrorCodes:
    MESSAGES = {
        0: "成功",
        3: "下单过于频繁，请稍后再试",
        100001: "暂无可售票或登录状态异常",
        100041: "未到开票时间",
        100044: "需要完成人机验证",
        100003: "重复购买",
        100016: "项目不可售",
        100039: "活动收摊啦,下次要快点哦",
        100048: "已经下单，有尚未完成订单",
        100017: "票种不可售",
        100051: "订单准备过期，重新验证",
        100034: "票价错误",
        100009: "库存不足",
        219: "下单失败，请重试",
        221: "下单请求过多，请稍后再试",
        900001: "下单过快，被系统限制",
        900002: "当前请求较多，请稍后再试",
    }

    SHOW_RESPONSE_MSG = {10003, 100003}

    @classmethod
    def get_message(cls, code: int) -> str | None:
        return cls.MESSAGES.get(code)

    @classmethod
    def get_message_or_unknown(cls, code: int) -> str:
        return cls.MESSAGES.get(code, "未知错误码")

    @classmethod
    def should_show_response_msg(cls, code: int) -> bool:
        return code in cls.SHOW_RESPONSE_MSG


ERRNO_DICT = ErrorCodes.MESSAGES
