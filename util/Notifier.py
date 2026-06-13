from abc import ABC, abstractmethod
from dataclasses import dataclass
import threading
import loguru
import time
from typing import Optional


class NotifierBase(ABC):
    """推送器基类。

    默认实现的 :py:meth:`run` 逻辑 **成功发送一次** 消息便退出；如果需要 *重复推送*（如
    `ntfy` 的持续提醒场景），应当在子类自行覆写 ``run`` 或 ``send_message`` 逻辑。

    Attributes
    ----------
    title : str
        推送标题。
    content : str
        推送正文。
    interval_seconds : int
        默认实现中，当 ``send_message`` 抛异常时的**重试间隔**；
        若子类覆写为循环推送模式，它也可作为每次循环发送的间隔。
    duration_minutes : int
        允许持续推送的总时长，默认 10 分钟。
    """

    def __init__(
        self,
        title: str,
        content: str,
        interval_seconds=10,
        duration_minutes=10,  # B站订单保存上限
    ):
        super().__init__()
        self.title = title
        self.content = content
        self.interval_seconds = interval_seconds
        self.duration_minutes = duration_minutes
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def run(self):
        """线程运行函数，实现间隔发送通知"""
        start_time = time.time()
        end_time = start_time + (self.duration_minutes * 60)
        count = 0

        while time.time() < end_time and not self.stop_event.is_set():
            try:
                # 构建消息内容，包含剩余时间
                remaining_minutes = int((end_time - time.time()) / 60)
                remaining_seconds = int((end_time - time.time()) % 60)
                message = f"{self.content} [#{count}, 剩余 {remaining_minutes}分{remaining_seconds}秒]"

                # 使用send_message方法发送
                self.send_message(self.title, message)
                # 确认发送成功后停止发送
                break

            except Exception as e:
                loguru.logger.error(f"通知发送失败: {e}")
                time.sleep(self.interval_seconds)  # 发生错误时等待重试

        loguru.logger.info("通知发送成功")

    def start(self):
        if not self.thread.is_alive():
            self.stop_event.clear()
            self.thread = threading.Thread(target=self.run, daemon=True)
            self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=3)

    @abstractmethod
    def send_message(self, title, message):
        """用于发送消息，子类必须实现此方法发送推送消息"""
        pass


@dataclass
class NotifierConfig:
    """推送配置统一管理"""

    serverchan_key: Optional[str] = None
    serverchan3_api_url: Optional[str] = None
    pushplus_token: Optional[str] = None
    bark_token: Optional[str] = None
    ntfy_url: Optional[str] = None
    ntfy_username: Optional[str] = None
    ntfy_password: Optional[str] = None
    meow_nickname: Optional[str] = None
    audio_path: Optional[str] = None
    notify_proxy_exhausted: bool = False

    @classmethod
    def from_config_db(cls):
        """从ConfigDB加载配置"""
        from util import ConfigDB

        return cls(
            serverchan_key=ConfigDB.get("serverchanKey"),
            serverchan3_api_url=ConfigDB.get("serverchan3ApiUrl"),
            pushplus_token=ConfigDB.get("pushplusToken"),
            bark_token=ConfigDB.get("barkToken"),
            ntfy_url=ConfigDB.get("ntfyUrl"),
            ntfy_username=ConfigDB.get("ntfyUsername"),
            ntfy_password=ConfigDB.get("ntfyPassword"),
            meow_nickname=ConfigDB.get("meowNickname"),
            audio_path=ConfigDB.get("audioPath"),
            notify_proxy_exhausted=bool(ConfigDB.get("notifyProxyExhausted") or False),
        )


class NotifierManager:
    def __init__(self):
        self.notifier_dict: dict[str, NotifierBase] = {}

    def register_notifier(self, name: str, notifier: NotifierBase):
        """注册推送器到管理器中。

        Args:
            name (str): 推送器名称（唯一键）。
            notifier (NotifierBase): 推送器实例。

        注意：如果 *name* 已存在，将记录错误并忽略本次注册。
        """
        if name in self.notifier_dict:
            loguru.logger.error(f"推送器添加失败: 已存在名为{name}的推送器")
        else:
            self.notifier_dict[name] = notifier
            loguru.logger.info(f"成功添加推送器: {name}")

    def remove_notifier(self, name: str):
        """从管理器中移除指定名称的推送器。"""
        if name not in self.notifier_dict:
            loguru.logger.error(f"推送器删除失败: 不存在名为{name}的推送器")
        else:
            self.notifier_dict.pop(name)
            loguru.logger.info(f"成功删除推送器: {name}")

    def start_all(self):
        for notifer in self.notifier_dict.values():
            notifer.start()

    def stop_all(self):
        for notifer in self.notifier_dict.values():
            notifer.stop()

    def start_notifier(self, name: str):
        notifer = self.notifier_dict.get(name)
        if notifer:
            notifer.start()
        else:
            loguru.logger.error(f"推送器启动失败: 不存在名为{name}的推送器")

    def stop_notifier(self, name: str):
        notifer = self.notifier_dict.get(name)
        if notifer:
            notifer.stop()
        else:
            loguru.logger.error(f"推送器停止失败: 不存在名为{name}的推送器")

    def list_notifiers(self):
        """返回当前已注册的推送器名称列表。"""
        return list(self.notifier_dict.keys())

    @staticmethod
    def create_from_config(
        config: NotifierConfig,
        title: str,
        content: str,
        interval_seconds: int = 10,
        duration_minutes: int = 10,
        include_audio: bool = True,
    ) -> "NotifierManager":
        """通过配置创建NotifierManager，统一的工厂方法"""
        manager = NotifierManager()

        # ServerChan Turbo
        if config.serverchan_key:
            try:
                from util.ServerChanUtil import ServerChanTurboNotifier

                notifier = ServerChanTurboNotifier(
                    token=config.serverchan_key,
                    title=title,
                    content=content,
                    interval_seconds=interval_seconds,
                    duration_minutes=duration_minutes,
                )
                manager.register_notifier("ServerChanTurbo", notifier)
            except ImportError as e:
                loguru.logger.error(f"ServerChanTurbo导入失败: {e}")
            except Exception as e:
                loguru.logger.error(f"ServerChanTurbo创建失败: {e}")

        # ServerChan3
        if config.serverchan3_api_url:
            try:
                from util.ServerChanUtil import ServerChan3Notifier

                notifier = ServerChan3Notifier(
                    api_url=config.serverchan3_api_url,
                    title=title,
                    content=content,
                    interval_seconds=interval_seconds,
                    duration_minutes=duration_minutes,
                )
                manager.register_notifier("ServerChan3", notifier)
            except ImportError as e:
                loguru.logger.error(f"ServerChan3导入失败: {e}")
            except Exception as e:
                loguru.logger.error(f"ServerChan3创建失败: {e}")

        # PushPlus
        if config.pushplus_token:
            try:
                from util.PushPlusUtil import PushPlusNotifier

                notifier = PushPlusNotifier(
                    token=config.pushplus_token,
                    title=title,
                    content=content,
                    interval_seconds=interval_seconds,
                    duration_minutes=duration_minutes,
                )
                manager.register_notifier("PushPlus", notifier)
            except ImportError as e:
                loguru.logger.error(f"PushPlus导入失败: {e}")
            except Exception as e:
                loguru.logger.error(f"PushPlus创建失败: {e}")

        # Bark
        if config.bark_token:
            try:
                from util.BarkUtil import BarkNotifier

                notifier = BarkNotifier(
                    token=config.bark_token,
                    title=title,
                    content=content,
                    interval_seconds=interval_seconds,
                    duration_minutes=duration_minutes,
                )
                manager.register_notifier("Bark", notifier)
            except ImportError as e:
                loguru.logger.error(f"Bark导入失败: {e}")
            except Exception as e:
                loguru.logger.error(f"Bark创建失败: {e}")

        # Ntfy
        if config.ntfy_url:
            try:
                from util.NtfyUtil import NtfyNotifier

                notifier = NtfyNotifier(
                    url=config.ntfy_url,
                    username=config.ntfy_username,
                    password=config.ntfy_password,
                    title=title,
                    content=content,
                    interval_seconds=interval_seconds,
                    duration_minutes=duration_minutes,
                )
                manager.register_notifier("Ntfy", notifier)
            except ImportError as e:
                loguru.logger.error(f"Ntfy导入失败: {e}")
            except Exception as e:
                loguru.logger.error(f"Ntfy创建失败: {e}")

        # MeoW
        if config.meow_nickname:
            try:
                from util.MeoWUtil import MeoWNotifier

                notifier = MeoWNotifier(
                    nickname=config.meow_nickname,
                    title=title,
                    content=content,
                    interval_seconds=interval_seconds,
                    duration_minutes=duration_minutes,
                )
                manager.register_notifier("MeoW", notifier)
            except ImportError as e:
                loguru.logger.error(f"MeoW导入失败: {e}")
            except Exception as e:
                loguru.logger.error(f"MeoW创建失败: {e}")

        # Audio
        if include_audio and config.audio_path:
            try:
                from util.AudioUtil import AudioNotifier

                notifier = AudioNotifier(
                    audio_path=config.audio_path,
                    title=title,
                    content=content,
                    interval_seconds=interval_seconds,
                    duration_minutes=duration_minutes,
                )
                manager.register_notifier("Audio", notifier)
            except ImportError as e:
                loguru.logger.error(f"Audio导入失败: {e}")
            except Exception as e:
                loguru.logger.error(f"Audio创建失败: {e}")

        return manager

    @staticmethod
    def test_all_notifiers(include_audio: bool = True) -> str:
        """测试所有已配置的推送渠道"""
        config = NotifierConfig.from_config_db()
        results = []

        # 使用统一的工厂方法创建测试管理器
        test_manager = NotifierManager.create_from_config(
            config=config,
            title="抢票提醒",
            content="测试推送",
            include_audio=include_audio,
        )

        # 测试每个已配置的推送渠道
        test_cases = [
            ("ServerChanTurbo", config.serverchan_key, "Server酱ᵀᵘʳᵇᵒ"),
            ("ServerChan3", config.serverchan3_api_url, "Server酱³"),
            ("PushPlus", config.pushplus_token, "PushPlus"),
            ("Bark", config.bark_token, "Bark"),
            ("Ntfy", config.ntfy_url, "Ntfy"),
            ("MeoW", config.meow_nickname, "MeoW"),
        ]
        if include_audio:
            test_cases.append(("Audio", config.audio_path, "音频通知"))

        for notifier_name, config_value, display_name in test_cases:
            if not config_value:
                results.append(f"⚠️ {display_name}: 未配置")
                continue

            if notifier_name in test_manager.notifier_dict:
                try:
                    notifier = test_manager.notifier_dict[notifier_name]
                    notifier.send_message(
                        "🎫 抢票测试", f"这是一条{display_name}测试推送消息"
                    )
                    results.append(f"✅ {display_name}: 测试推送已发送")
                except Exception as e:
                    results.append(f"❌ {display_name}: 推送失败 - {str(e)}")
            else:
                results.append(f"❌ {display_name}: 创建失败")

        return "\n".join(results)
