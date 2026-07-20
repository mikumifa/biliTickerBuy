"""验证抢票成功后"同步确认送达"发生在进程退出（os._exit）之前。

UI 模式下 buy_cmd 在生成器耗尽、Buy().buy() 返回后才调用
exit_immediately_if_child_process() → os._exit(0)。os._exit 会硬杀 daemon 线程，
所以必须保证同步发送 (send_all_sync) 在此之前完成。

这里复刻 app_cmd/buy.py 的控制流骨架：驱动一个"抢票成功后调用 send_all_sync"
的生成器，再走 exit_immediately_if_child_process，断言事件顺序。
"""

from util.notifer.Notifier import NotifierBase, NotifierManager


class _RecordingNotifier(NotifierBase):
    def __init__(self, events, name):
        super().__init__(title="t", content="c")
        self._events = events
        self._name = name

    def send_message(self, title, message):
        self._events.append(f"send:{self._name}")


def test_sync_send_runs_before_os_exit():
    events = []

    manager = NotifierManager()
    manager.register_notifier("A", _RecordingNotifier(events, "A"))

    def buy_stream_like():
        """模拟 task/buy.py errno==0 分支：yield 完成后同步确认送达。"""
        yield "抢票成功，弹出付款二维码"
        # 关键：break 之前的同步阻塞发送
        manager.send_all_sync("抢票成功", "请尽快付款", retries=1)

    def buy_like():
        # 相当于 Buy().buy() —— 耗尽生成器
        for _ in buy_stream_like():
            pass

    child_process_mode = True

    def exit_immediately_if_child_process():
        if child_process_mode:
            events.append("os._exit")  # 用记录代替真正的 os._exit(0)

    # 复刻 buy_cmd 的顺序：先跑 buy()，返回后才 exit
    buy_like()
    exit_immediately_if_child_process()

    # 同步发送必须在 os._exit 之前
    assert events == ["send:A", "os._exit"]
    assert events.index("send:A") < events.index("os._exit")


def test_sync_send_completes_even_when_daemon_would_be_killed():
    """send_all_sync 在当前线程内同步完成，不依赖 daemon 线程被 join。"""
    events = []
    manager = NotifierManager()
    manager.register_notifier("A", _RecordingNotifier(events, "A"))
    manager.register_notifier("B", _RecordingNotifier(events, "B"))

    # 注意：不调用 start_all()/join_all()，纯同步路径也应把两条都发出去
    results = manager.send_all_sync("t", "c", retries=1)
    assert results == {"A": True, "B": True}
    assert sorted(events) == ["send:A", "send:B"]
