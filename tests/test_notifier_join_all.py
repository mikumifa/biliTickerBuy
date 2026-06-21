"""NotifierManager.join_all 的单元测试。

验证抢票成功后退出前等待推送线程完成的修复：
- start_all() 启动 daemon 推送线程后，join_all() 会阻塞到线程结束（推送发完）
- 超时上限保护，避免无限阻塞
- 没有注册推送器时 join_all() 立即返回
背景：推送线程是 daemon，CLI 进程成功后会立刻退出；若不在退出前 join，
飞行中的 HTTP 推送请求会被掐断，导致第三方渠道收不到通知。
"""

import threading
import time

from util.notifer.Notifier import NotifierBase, NotifierManager


class _FakeNotifier(NotifierBase):
    """记一次 send_message 调用并短暂阻塞，模拟一次网络往返。"""

    def __init__(self, delay: float = 0.05):
        super().__init__(title="t", content="c")
        self.sent = threading.Event()
        self.started = threading.Event()
        self._delay = delay

    def send_message(self, title, message):
        self.started.set()
        time.sleep(self._delay)
        self.sent.set()


def _make_manager(*notifiers: _FakeNotifier) -> NotifierManager:
    manager = NotifierManager()
    for i, n in enumerate(notifiers):
        manager.register_notifier(f"n{i}", n)
    return manager


def test_join_all_waits_for_push_to_complete():
    notifier = _FakeNotifier(delay=0.05)
    manager = _make_manager(notifier)

    manager.start_all()
    # 线程刚起，推送尚未发完
    assert notifier.sent.is_set() is False

    manager.join_all(timeout=5)

    assert notifier.sent.is_set() is True


def test_join_all_blocks_until_thread_finishes():
    notifier = _FakeNotifier(delay=0.2)
    manager = _make_manager(notifier)

    manager.start_all()
    started_at = time.monotonic()
    manager.join_all(timeout=5)
    elapsed = time.monotonic() - started_at

    # join 应当至少等到推送完成（~0.2s），而不是立刻返回
    assert notifier.sent.is_set() is True
    assert elapsed >= 0.15


def test_join_all_timeout_does_not_block_forever():
    # 一个永不完成的推送线程：send_message 一直 sleep
    class _Slow(NotifierBase):
        def __init__(self):
            super().__init__(title="t", content="c")
            self.sent = threading.Event()

        def send_message(self, title, message):
            time.sleep(10)
            self.sent.set()

    notifier = _Slow()
    manager = _make_manager(notifier)

    manager.start_all()
    started_at = time.monotonic()
    manager.join_all(timeout=0.3)
    elapsed = time.monotonic() - started_at

    # 超时返回，且大致在��时阈值附近（不会��满 10s）
    assert notifier.sent.is_set() is False
    assert elapsed < 2.0


def test_join_all_no_notifiers_returns_immediately():
    manager = NotifierManager()
    started_at = time.monotonic()
    manager.join_all(timeout=5)
    elapsed = time.monotonic() - started_at
    assert elapsed < 0.5
