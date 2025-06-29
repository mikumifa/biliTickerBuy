import base64
import threading
import time

import loguru
import requests

# 维护所有运行中的通知线程
_active_notification_threads = {}  # type: ignore
_thread_lock = threading.Lock()


class RepeatedNotifier(threading.Thread):
    """
    后台通知发送线程类，用于重复发送ntfy通知
    """

    def __init__(
        self,
        server_url,
        content,
        title=None,
        username=None,
        password=None,
        interval_seconds=10,
        duration_minutes=5,
        thread_id=None,
    ):
        super().__init__()
        self.server_url = server_url
        self.content = content
        self.title = title
        self.username = username
        self.password = password
        self.interval_seconds = interval_seconds
        self.duration_minutes = duration_minutes
        self.daemon = True  # 设置为守护线程，当主程序退出时自动结束
        self.stop_event = threading.Event()
        self.thread_id = thread_id or f"ntfy_{threading.get_ident()}"

    def run(self):
        """线程运行函数，实现间隔发送通知"""
        start_time = time.time()
        end_time = start_time + (self.duration_minutes * 60)
        count = 0

        while time.time() < end_time and not self.stop_event.is_set():
            try:
                count += 1
                # 构建消息内容，包含计数和剩余时间
                remaining_minutes = int((end_time - time.time()) / 60)
                remaining_seconds = int((end_time - time.time()) % 60)
                message = f"{self.content} [#{count}, 剩余 {remaining_minutes}分{remaining_seconds}秒]"

                # 每次使用普通方法发送
                send_message(
                    self.server_url,
                    message,
                    f"{self.title} ({count}/{self.duration_minutes * 60 // self.interval_seconds})"
                    if self.title
                    else None,
                    self.username,
                    self.password,
                )

                # 等待指定的间隔时间或直到收到停止信号
                for _ in range(
                    int(self.interval_seconds * 10)
                ):  # 分成更小的步骤检查停止事件
                    if self.stop_event.is_set():
                        break
                    time.sleep(0.1)

            except Exception as e:
                loguru.logger.error(f"重复通知发送失败: {e}")
                time.sleep(self.interval_seconds)  # 发生错误时仍然等待

        # 线程结束时从活动线程列表中移除
        with _thread_lock:
            if self.thread_id in _active_notification_threads:
                del _active_notification_threads[self.thread_id]

        loguru.logger.info(f"重复通知线程结束，共发送了{count}条通知")


def send_message(server_url, content, title=None, username=None, password=None):
    """
    使用ntfy发送通知

    Args:
        server_url: ntfy服务器URL，如 https://ntfy.sh/mytopic 或 http://selfhosted.ntfy.sh/mytopic
        content: 通知内容
        title: 通知标题，如果为中文将自动编码为ASCII
        username: ntfy用户名，如果为None则不添加认证
        password: ntfy密码，如果为None则不添加认证
    """
    try:
        # 方法1: 不指定Content-Type，让服务器自动判断
        headers = {}

        # 设置最高优先级 (5)
        headers["Priority"] = "5"

        # 如果标题存在，处理中文标题
        if title:
            # 如果标题不是ASCII字符，则使用一个英文标题
            try:
                title.encode("ascii")
                headers["Title"] = title
            except UnicodeEncodeError:
                # 如果标题不是ASCII字符，则使用一个默认标题
                headers["Title"] = "Bili Ticket Notification"

        # 处理认证
        if username and password:
            auth = base64.b64encode(f"{username}:{password}".encode()).decode()
            headers["Authorization"] = f"Basic {auth}"

        # 发送纯文本内容
        response = requests.post(
            server_url, headers=headers, data=content.encode("utf-8")
        )
        loguru.logger.info(f"Ntfy消息发送成功，状态码: {response.status_code}")
        return response
    except Exception as e:
        loguru.logger.error(f"Ntfy消息发送失败: {e}")
        raise


def send_repeat_message(
    server_url,
    content,
    title=None,
    username=None,
    password=None,
    interval_seconds=10,
    duration_minutes=5,
    thread_id=None,
):
    """
    在后台线程中重复发送ntfy通知

    Args:
        server_url: ntfy服务器URL
        content: 通知内容
        title: 通知标题
        username: ntfy用户名
        password: ntfy密码
        interval_seconds: 发送间隔（秒）
        duration_minutes: 持续时间（分钟）
        thread_id: 线程ID，用于后续停止，如果为None则自动生成

    Returns:
        str: 线程ID，可用于后续停止通知
    """
    thread_id = thread_id or f"ntfy_{time.time()}"

    # 如果已存在同ID的线程，先停止它
    stop_notification(thread_id)

    # 创建新的通知线程
    notifier = RepeatedNotifier(
        server_url,
        content,
        title,
        username,
        password,
        interval_seconds,
        duration_minutes,
        thread_id,
    )

    # 存储线程引用
    with _thread_lock:
        _active_notification_threads[thread_id] = notifier

    # 启动线程
    notifier.start()
    loguru.logger.info(
        f"启动重复通知线程 {thread_id}，间隔{interval_seconds}秒，持续{duration_minutes}分钟"
    )

    return thread_id


def stop_notification(thread_id):
    """
    停止指定的通知线程

    Args:
        thread_id: 要停止的线程ID

    Returns:
        bool: 是否成功停止
    """
    with _thread_lock:
        if thread_id in _active_notification_threads:
            _active_notification_threads[thread_id].stop_event.set()
            loguru.logger.info(f"已发送停止信号到通知线程 {thread_id}")
            return True
    return False


def test_connection(server_url, username=None, password=None):
    """
    测试ntfy连接是否正常

    Args:
        server_url: ntfy服务器URL
        username: ntfy用户名，如果为None则不添加认证
        password: ntfy密码，如果为None则不添加认证

    Returns:
        tuple: (是否成功, 消息)
    """
    try:
        headers = {
            "Title": "Test Connection",
        }

        # 处理认证
        if username and password:
            auth = base64.b64encode(f"{username}:{password}".encode()).decode()
            headers["Authorization"] = f"Basic {auth}"

        # 方法1: 直接发送纯文本，不指定Content-Type
        response = requests.post(
            server_url,
            headers=headers,
            data="这是一个测试连接消息，如果收到说明连接正常。".encode("utf-8"),
            timeout=10,
        )

        if response.status_code in [200, 201, 202]:
            return True, "测试连接成功，已发送测试消息"
        else:
            return (
                False,
                f"测试连接失败，状态码: {response.status_code}, 响应: {response.text}",
            )

    except requests.RequestException as e:
        return False, f"连接失败: {str(e)}"
    except Exception as e:
        return False, f"测试过程中发生错误: {str(e)}"


# 添加NtfyNotifier类，和其他推送渠道一样的静态类
from util.Notifier import NotifierBase


class NtfyNotifier(NotifierBase):
    """Ntfy通知器，继承自NotifierBase，实现统一接口"""
    def __init__(
        self,
        url,
        username=None,
        password=None,
        title="",
        content="",
        interval_seconds=15,
        duration_minutes=5
    ):
        super().__init__(title, content, interval_seconds, duration_minutes)
        self.url = url
        self.username = username
        self.password = password
    
    def send_message(self, title, message):
        """使用send_message函数发送单次通知"""
        send_message(self.url, message, title, self.username, self.password)

    def run(self):
        """重写run方法，实现Ntfy特有的重复通知逻辑"""
        start_time = time.time()
        end_time = start_time + (self.duration_minutes * 60)
        count = 0

        while time.time() < end_time and not self.stop_event.is_set():
            try:
                count += 1
                # 构建消息内容，包含计数和剩余时间
                remaining_minutes = int((end_time - time.time()) / 60)
                remaining_seconds = int((end_time - time.time()) % 60)
                message = f"{self.content} [#{count}, 剩余 {remaining_minutes}分{remaining_seconds}秒]"

                # 使用send_message方法发送
                self.send_message(
                    f"{self.title} ({count}/{self.duration_minutes * 60 // self.interval_seconds})" if self.title else "Bili Ticket Notification",
                    message
                )

                # 等待指定的间隔时间或直到收到停止信号
                for _ in range(int(self.interval_seconds * 10)):  # 分成更小的步骤检查停止事件
                    if self.stop_event.is_set():
                        break
                    time.sleep(0.1)

            except Exception as e:
                loguru.logger.error(f"Ntfy重复通知发送失败: {e}")
                time.sleep(self.interval_seconds)  # 发生错误时仍然等待

        loguru.logger.info(f"Ntfy重复通知完成，共发送了{count}条通知")
