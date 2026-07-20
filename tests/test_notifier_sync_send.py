"""通知同步发送与重试的单元测试。

覆盖本次修复的核心可靠性逻辑：
- send_message 的 requests.post 带 timeout（避免无限阻塞）
- send_once_sync 在失败（超时/连接错/非2xx）时按指数退避重试
- NotifierManager.send_all_sync 成功/全失败的返回明细
- send_all_sync 复用各渠道 send_message，不依赖 daemon 线程
"""

import requests

from util.notifer.Notifier import NotifierBase, NotifierManager, DEFAULT_HTTP_TIMEOUT
from util.notifer.NtfyUtil import NtfyNotifier
from util.notifer.ServerChanUtil import ServerChanTurboNotifier, ServerChan3Notifier
from util.notifer.BarkUtil import BarkNotifier
from util.proxy.PushPlusUtil import PushPlusNotifier


class _CountingNotifier(NotifierBase):
    """记录 send_message 调用次数；可配置在前 N 次抛异常，模拟网络抖动。"""

    def __init__(self, fail_times: int = 0, always_fail: bool = False):
        super().__init__(title="t", content="c")
        self.calls = 0
        self._fail_times = fail_times
        self._always_fail = always_fail

    def send_message(self, title, message):
        self.calls += 1
        if self._always_fail or self.calls <= self._fail_times:
            raise requests.exceptions.ConnectTimeout("模拟超时")


def test_send_once_sync_succeeds_first_try():
    n = _CountingNotifier(fail_times=0)
    assert n.send_once_sync("t", "m", retries=3, backoff=0) is True
    assert n.calls == 1


def test_send_once_sync_retries_then_succeeds():
    # 前两次失败，第三次成功；backoff=0 避免测试变慢
    n = _CountingNotifier(fail_times=2)
    assert n.send_once_sync("t", "m", retries=3, backoff=0) is True
    assert n.calls == 3


def test_send_once_sync_exhausts_retries_and_fails():
    n = _CountingNotifier(always_fail=True)
    assert n.send_once_sync("t", "m", retries=3, backoff=0) is False
    assert n.calls == 3  # 首发 + 2 次重试


def test_send_all_sync_all_success():
    manager = NotifierManager()
    a = _CountingNotifier(fail_times=0)
    b = _CountingNotifier(fail_times=0)
    manager.register_notifier("a", a)
    manager.register_notifier("b", b)

    results = manager.send_all_sync("标题", "内容", retries=1)
    assert results == {"a": True, "b": True}
    assert a.calls == 1 and b.calls == 1


def test_send_all_sync_all_fail():
    manager = NotifierManager()
    a = _CountingNotifier(always_fail=True)
    b = _CountingNotifier(always_fail=True)
    manager.register_notifier("a", a)
    manager.register_notifier("b", b)

    results = manager.send_all_sync("标题", "内容", retries=2)
    assert results == {"a": False, "b": False}
    # 各渠道穷尽重试
    assert a.calls == 2 and b.calls == 2
    assert not any(results.values())


def test_send_all_sync_partial():
    manager = NotifierManager()
    ok = _CountingNotifier(fail_times=0)
    bad = _CountingNotifier(always_fail=True)
    manager.register_notifier("ok", ok)
    manager.register_notifier("bad", bad)

    results = manager.send_all_sync("标题", "内容", retries=1)
    assert results == {"ok": True, "bad": False}
    assert any(results.values())  # 至少一条成功


def test_send_all_sync_no_notifiers():
    manager = NotifierManager()
    assert manager.send_all_sync("标题", "内容") == {}


# --- 各渠道 send_message 均带 timeout，且失败会抛异常触发重试 ---


class _FakeResp:
    def __init__(self, status_code=200):
        self.status_code = status_code
        self.text = ""

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"status={self.status_code}")

    def json(self):
        return {"status": 200}


def _capture_post(monkeypatch, module, status_code=200):
    """替换某模块的 requests.post，捕获调用参数，返回 captured dict。"""
    captured = {}

    def fake_post(url, *args, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return _FakeResp(status_code)

    monkeypatch.setattr(module.requests, "post", fake_post)
    return captured


def test_ntfy_send_has_timeout(monkeypatch):
    import util.notifer.NtfyUtil as mod

    cap = _capture_post(monkeypatch, mod)
    NtfyNotifier(url="https://ntfy.sh/x").send_message("标题", "消息")
    assert cap["kwargs"].get("timeout") == DEFAULT_HTTP_TIMEOUT


def test_serverchan_turbo_has_timeout(monkeypatch):
    import util.notifer.ServerChanUtil as mod

    cap = _capture_post(monkeypatch, mod)
    ServerChanTurboNotifier(token="tk", title="t", content="c").send_message("标题", "消息")
    assert cap["kwargs"].get("timeout") == DEFAULT_HTTP_TIMEOUT


def test_serverchan3_has_timeout(monkeypatch):
    import util.notifer.ServerChanUtil as mod

    cap = _capture_post(monkeypatch, mod)
    ServerChan3Notifier(api_url="https://x", title="t", content="c").send_message(
        "标题", "消息"
    )
    assert cap["kwargs"].get("timeout") == DEFAULT_HTTP_TIMEOUT


def test_bark_has_timeout(monkeypatch):
    import util.notifer.BarkUtil as mod

    cap = _capture_post(monkeypatch, mod)
    BarkNotifier(token="tk", title="t", content="c").send_message("标题", "消息")
    assert cap["kwargs"].get("timeout") == DEFAULT_HTTP_TIMEOUT


def test_pushplus_has_timeout(monkeypatch):
    import util.proxy.PushPlusUtil as mod

    cap = _capture_post(monkeypatch, mod)
    PushPlusNotifier(token="tk", title="t", content="c").send_message("标题", "消息")
    assert cap["kwargs"].get("timeout") == DEFAULT_HTTP_TIMEOUT


def test_non_2xx_raises_and_triggers_retry(monkeypatch):
    """非 2xx 状态码应经 raise_for_status 抛异常，从而被 send_once_sync 重试。"""
    import util.notifer.NtfyUtil as mod

    _capture_post(monkeypatch, mod, status_code=500)
    notifier = NtfyNotifier(url="https://ntfy.sh/x")
    # 全程 500，穷尽重试后返回 False
    assert notifier.send_once_sync("标题", "消息", retries=2, backoff=0) is False


# ---------- 可配置参数（timeout/retries/backoff）覆盖 ----------

def test_resolve_timeout_from_config():
    """_resolve_timeout 应从 config 的 notify_connect/read_timeout 组成 tuple。"""
    from util.notifer.Notifier import _resolve_timeout

    class _Cfg:
        notify_connect_timeout = 3.0
        notify_read_timeout = 7.0

    assert _resolve_timeout(_Cfg()) == (3.0, 7.0)


def test_resolve_timeout_falls_back_on_invalid():
    """非法/缺失/非正值应逐项回退到 DEFAULT_HTTP_TIMEOUT。"""
    from util.notifer.Notifier import _resolve_timeout

    class _Bad:
        notify_connect_timeout = "x"
        notify_read_timeout = -1

    assert _resolve_timeout(_Bad()) == DEFAULT_HTTP_TIMEOUT

    class _Missing:
        pass

    assert _resolve_timeout(_Missing()) == DEFAULT_HTTP_TIMEOUT


def test_notifier_uses_configured_timeout(monkeypatch):
    """notifier 构造时传入的 timeout 应被 send_message 的 requests.post 使用。"""
    import util.notifer.NtfyUtil as mod

    cap = _capture_post(monkeypatch, mod)
    NtfyNotifier(url="https://ntfy.sh/x", timeout=(2.0, 4.0)).send_message("t", "m")
    assert cap["kwargs"].get("timeout") == (2.0, 4.0)


def test_resolve_notify_retry_params_from_config():
    """buy._resolve_notify_retry_params 从 config 读取 retries/backoff。"""
    from task.buy import _resolve_notify_retry_params

    class _Cfg:
        notify_retries = 5
        notify_backoff = 1.5

    assert _resolve_notify_retry_params(_Cfg()) == (5, 1.5)


def test_resolve_notify_retry_params_fallback():
    """非法/缺失回退 (3, 0.5)，retries 下限 1，backoff 负值回退。"""
    from task.buy import _resolve_notify_retry_params

    class _Bad:
        notify_retries = "nope"
        notify_backoff = -2.0

    assert _resolve_notify_retry_params(_Bad()) == (3, 0.5)

    class _Zero:
        notify_retries = 0
        notify_backoff = 0.0

    retries, backoff = _resolve_notify_retry_params(_Zero())
    assert retries == 1  # 下限 1
    assert backoff == 0.0  # 0 合法（不退避）

    class _Missing:
        pass

    assert _resolve_notify_retry_params(_Missing()) == (3, 0.5)


def test_notifier_config_cli_defaults():
    """NotifierConfig 4 个可配参数的默认值（不传任何配置时）。"""
    from app_cmd.config.NotifierConfig import NotifierConfig

    cfg = NotifierConfig()
    assert cfg.notify_connect_timeout == 5.0
    assert cfg.notify_read_timeout == 10.0
    assert cfg.notify_retries == 3
    assert cfg.notify_backoff == 0.5
