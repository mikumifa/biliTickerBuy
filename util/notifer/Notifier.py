from abc import ABC, abstractmethod
import threading
import loguru
import time

from app_cmd.config.NotifierConfig import NotifierConfig

# 全渠道统一的 (连接超时, 读取超时)，避免无 timeout 的 POST 无限阻塞
DEFAULT_HTTP_TIMEOUT = (5, 10)


def _resolve_timeout(config) -> tuple:
    """从 NotifierConfig 组装 (连接超时, 读取超时) 元组；缺配置时回退到默认。

    非法或缺失的字段（如无法转 float）逐项回退到 :data:`DEFAULT_HTTP_TIMEOUT`，
    保证任意配置都不会得到 ``None``/非数值 timeout。
    """
    default_connect, default_read = DEFAULT_HTTP_TIMEOUT

    def _coerce(value, fallback):
        try:
            resolved = float(value)
        except (TypeError, ValueError):
            return fallback
        return resolved if resolved > 0 else fallback

    connect = _coerce(getattr(config, "notify_connect_timeout", None), default_connect)
    read = _coerce(getattr(config, "notify_read_timeout", None), default_read)
    return (connect, read)


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
    timeout : float | tuple
        各渠道 HTTP 请求的 (连接超时, 读取超时)，默认 :data:`DEFAULT_HTTP_TIMEOUT`。
        子类的 ``send_message`` 应在 ``requests.post`` 中使用 ``self.timeout``。
    """

    def __init__(
        self,
        title: str,
        content: str,
        interval_seconds=10,
        duration_minutes=10,  # B站订单保存上限
        timeout=DEFAULT_HTTP_TIMEOUT,
    ):
        super().__init__()
        self.title = title
        self.content = content
        self.interval_seconds = interval_seconds
        self.duration_minutes = duration_minutes
        self.timeout = timeout if timeout is not None else DEFAULT_HTTP_TIMEOUT
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

    def send_once_sync(self, title, message, retries: int = 3, backoff: float = 0.5):
        """同步阻塞发送一次消息，失败（超时/连接错/非2xx）时按指数退避重试。

        与 daemon 线程的 :py:meth:`run` 不同，本方法在当前线程内完成，可用于
        进程退出前的"同步确认送达"，不依赖解释器等待 daemon 线程。

        Args:
            title: 推送标题。
            message: 推送正文。
            retries: 最多尝试次数（含首发），默认 3。
            backoff: 首次重试的退避秒数，之后按 2 倍指数增长（0.5→1→2）。

        Returns:
            bool: 是否成功送达（穷尽重试仍失败返回 False）。
        """
        attempts = max(1, int(retries))
        last_error = None
        for attempt in range(1, attempts + 1):
            try:
                self.send_message(title, message)
                loguru.logger.info(
                    f"通知同步发送成功（第 {attempt}/{attempts} 次尝试）"
                )
                return True
            except Exception as e:  # 超时/连接错/非2xx 均由 send_message 抛出
                last_error = e
                loguru.logger.warning(
                    f"通知同步发送失败（第 {attempt}/{attempts} 次尝试）: {e}"
                )
                if attempt < attempts:
                    wait = backoff * (2 ** (attempt - 1))
                    time.sleep(wait)
        loguru.logger.error(f"通知同步发送最终失败，已穷尽 {attempts} 次重试: {last_error}")
        return False


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

    def join_all(self, timeout: float = 15.0):
        """等待所有推送线程结束（或超时）。

        推送线程是 daemon 线程，解释器退出时不会等待它们完成后再退出。
        抢票成功后，如果不在退出前 join，CLI 进程会立刻结束，HTTP 推送请求会被中断，导致 Server酱/Bark/PushPlus 等渠道收不到通知。
        此方法给推送线程一个完成窗口。
        """
        for notifer in self.notifier_dict.values():
            notifer.thread.join(timeout=timeout)

    def send_all_sync(
        self,
        title: str,
        content: str,
        timeout=None,
        retries: int = 3,
        backoff: float = 0.5,
    ) -> dict[str, bool]:
        """在当前线程内对所有已注册推送器做一次同步阻塞发送（带 timeout + 重试）。

        用于抢票成功后、进程退出（含 UI 模式 ``os._exit``）之前的"同步确认送达"，
        不依赖 daemon 线程 :py:meth:`join_all` 的 15 秒窗口。

        Args:
            title: 推送标题。
            content: 推送正文。
            timeout: 兼容参数（各渠道 send_message 已内置 timeout），当前未直接使用。
            retries: 每个渠道的最多尝试次数。
            backoff: 每个渠道首次重试的退避秒数（指数增长）。

        Returns:
            dict[str, bool]: 各渠道名称 -> 是否送达成功。
        """
        results: dict[str, bool] = {}
        if not self.notifier_dict:
            loguru.logger.info("同步发送通知：无已注册推送器，跳过")
            return results

        for name, notifer in self.notifier_dict.items():
            try:
                ok = notifer.send_once_sync(
                    title, content, retries=retries, backoff=backoff
                )
            except Exception as e:
                loguru.logger.error(f"推送器 {name} 同步发送异常: {e}")
                ok = False
            results[name] = ok

        success = [n for n, ok in results.items() if ok]
        failed = [n for n, ok in results.items() if not ok]
        loguru.logger.info(
            f"同步发送通知完成：成功 {len(success)}/{len(results)} "
            f"（成功: {success or '无'}；失败: {failed or '无'}）"
        )
        return results

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
        timeout = _resolve_timeout(config)

        # ServerChan Turbo
        if config.serverchan_key:
            try:
                from util.notifer.ServerChanUtil import ServerChanTurboNotifier

                notifier = ServerChanTurboNotifier(
                    token=config.serverchan_key,
                    title=title,
                    content=content,
                    interval_seconds=interval_seconds,
                    duration_minutes=duration_minutes,
                    timeout=timeout,
                )
                manager.register_notifier("ServerChanTurbo", notifier)
            except ImportError as e:
                loguru.logger.error(f"ServerChanTurbo导入失败: {e}")
            except Exception as e:
                loguru.logger.error(f"ServerChanTurbo创建失败: {e}")

        # ServerChan3
        if config.serverchan3_api_url:
            try:
                from util.notifer.ServerChanUtil import ServerChan3Notifier

                notifier = ServerChan3Notifier(
                    api_url=config.serverchan3_api_url,
                    title=title,
                    content=content,
                    interval_seconds=interval_seconds,
                    duration_minutes=duration_minutes,
                    timeout=timeout,
                )
                manager.register_notifier("ServerChan3", notifier)
            except ImportError as e:
                loguru.logger.error(f"ServerChan3导入失败: {e}")
            except Exception as e:
                loguru.logger.error(f"ServerChan3创建失败: {e}")

        # PushPlus
        if config.pushplus_token:
            try:
                from util.proxy.PushPlusUtil import PushPlusNotifier

                notifier = PushPlusNotifier(
                    token=config.pushplus_token,
                    title=title,
                    content=content,
                    interval_seconds=interval_seconds,
                    duration_minutes=duration_minutes,
                    timeout=timeout,
                )
                manager.register_notifier("PushPlus", notifier)
            except ImportError as e:
                loguru.logger.error(f"PushPlus导入失败: {e}")
            except Exception as e:
                loguru.logger.error(f"PushPlus创建失败: {e}")

        # Bark
        if config.bark_token:
            try:
                from util.notifer.BarkUtil import BarkNotifier

                notifier = BarkNotifier(
                    token=config.bark_token,
                    title=title,
                    content=content,
                    interval_seconds=interval_seconds,
                    duration_minutes=duration_minutes,
                    timeout=timeout,
                )
                manager.register_notifier("Bark", notifier)
            except ImportError as e:
                loguru.logger.error(f"Bark导入失败: {e}")
            except Exception as e:
                loguru.logger.error(f"Bark创建失败: {e}")

        # Ntfy
        if config.ntfy_url:
            try:
                from util.notifer.NtfyUtil import NtfyNotifier

                notifier = NtfyNotifier(
                    url=config.ntfy_url,
                    username=config.ntfy_username,
                    password=config.ntfy_password,
                    title=title,
                    content=content,
                    interval_seconds=interval_seconds,
                    duration_minutes=duration_minutes,
                    timeout=timeout,
                )
                manager.register_notifier("Ntfy", notifier)
            except ImportError as e:
                loguru.logger.error(f"Ntfy导入失败: {e}")
            except Exception as e:
                loguru.logger.error(f"Ntfy创建失败: {e}")

        # MeoW
        if config.meow_nickname:
            try:
                from util.notifer.MeoWUtil import MeoWNotifier

                notifier = MeoWNotifier(
                    nickname=config.meow_nickname,
                    title=title,
                    content=content,
                    interval_seconds=interval_seconds,
                    duration_minutes=duration_minutes,
                    timeout=timeout,
                )
                manager.register_notifier("MeoW", notifier)
            except ImportError as e:
                loguru.logger.error(f"MeoW导入失败: {e}")
            except Exception as e:
                loguru.logger.error(f"MeoW创建失败: {e}")

        # Telegram
        if config.telegram_bot_token and config.telegram_chat_id:
            try:
                from util.notifer.TelegramUtil import TelegramNotifier

                notifier = TelegramNotifier(
                    bot_token=config.telegram_bot_token,
                    chat_id=config.telegram_chat_id,
                    title=title,
                    content=content,
                    interval_seconds=interval_seconds,
                    duration_minutes=duration_minutes,
                    http_proxy=config.telegram_http_proxy,
                    timeout=timeout,
                )
                manager.register_notifier("Telegram", notifier)
            except ImportError as e:
                loguru.logger.error(f"Telegram导入失败: {e}")
            except Exception as e:
                loguru.logger.error(f"Telegram创建失败: {e}")

        # Audio
        if include_audio and config.audio_path:
            try:
                from util.notifer.AudioUtil import AudioNotifier

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
            (
                "Telegram",
                config.telegram_bot_token and config.telegram_chat_id,
                "Telegram",
            ),
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
