from util.Notifier import NotifierBase
import loguru


class AudioNotifier(NotifierBase):
    """音频通知器，播放本地音频文件"""
    def __init__(
        self,
        audio_path,
        title="",
        content="",
        interval_seconds=10,
        duration_minutes=10
    ):
        super().__init__(title, content, interval_seconds, duration_minutes)
        self.audio_path = audio_path

    def send_message(self, title, message):
        """播放音频文件作为通知"""
        try:
            from playsound3 import playsound
            playsound(self.audio_path)
            loguru.logger.info(f"音频通知已播放: {self.audio_path}")
        except Exception as e:
            loguru.logger.error(f"音频播放失败: {e}")
            raise

    def run(self):
        """重写run方法，音频只播放一次，不需要循环"""
        try:
            self.send_message(self.title, self.content)
            loguru.logger.info("音频通知播放完成")
        except Exception as e:
            loguru.logger.error(f"音频通知播放失败: {e}") 