import ntplib
import time
from loguru import logger


class TimeService:
    # NTP服务器默认为ntp.aliyun.com, 可根据实际情况修改
    def __init__(self, _ntp_server="ntp.aliyun.com") -> None:
        self.ntp_server = _ntp_server
        self.client = ntplib.NTPClient()
        self.timeoffset: float = 0

    def compute_timeoffset(self) -> str:
        # NTP时间请求有可能会超时失败, 设定三次重试机会
        for i in range(0, 3):
            try:
                response = self.client.request(self.ntp_server, version=3)
                break
            except Exception as e:
                logger.warning("第" + str(i + 1) + "次获取NTP时间失败, 尝试重新获取")
                if i == 2:
                    logger.warning("NTP时间同步失败, 使用本地时间")
                    return "error"
                time.sleep(0.5)
        ntp_time = response.tx_time
        device_time = time.time()
        time_diff = device_time - ntp_time
        logger.info(
            "时间同步成功, 使用"
            + self.ntp_server
            + "时间"
        )
        return format(time_diff,'.5f')

    def set_timeoffset(self, _timeoffset) -> None:
        """
        存储时注意set_timeoffset单位为秒
        """
        if _timeoffset == "error":
            self.timeoffset = 0
        else:
            self.timeoffset = float(_timeoffset)
        logger.info("设置时间偏差为: " + str(self.timeoffset) + "秒")

    def get_timeoffset(self) -> float:
        """
        获取到的timeoffset单位为秒, 使用时可根据实际情况进行转换
        """
        return self.timeoffset
