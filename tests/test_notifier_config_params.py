"""第二轮：通知超时/重试参数可配置化的单元测试。

覆盖：
- env 变量能覆盖 4 个新参数（float/int 从字符串正确解析）
- CLI 参数往返（to_cli_args -> from_mapping runtime）能覆盖默认值
- create_from_config 把 connect/read timeout 组成 tuple 传到各 notifier.timeout
- send_message 的 requests.post 使用配置的 timeout
- send_all_sync 使用配置解析出的 retries/backoff
- 不传任何配置时行为与第一轮一致（默认 (5,10)/3/0.5）
"""

import requests

from app_cmd.config.NotifierConfig import NotifierConfig
from util.notifer.Notifier import (
    NotifierBase,
    NotifierManager,
    DEFAULT_HTTP_TIMEOUT,
    _resolve_timeout,
)
from util.notifer.ServerChanUtil import ServerChanTurboNotifier


# --- 默认值：不传配置时与第一轮一致 ---


def test_defaults_match_first_round():
    config = NotifierConfig()
    assert config.notify_connect_timeout == 5.0
    assert config.notify_read_timeout == 10.0
    assert config.notify_retries == 3
    assert config.notify_backoff == 0.5
    # 组装出的 tuple 与旧的模块默认一致
    assert _resolve_timeout(config) == (5.0, 10.0)


# --- env 覆盖（float/int 从字符串解析）---


def test_env_overrides_numeric_params(monkeypatch):
    monkeypatch.setenv("BTB_NOTIFY_CONNECT_TIMEOUT", "2.5")
    monkeypatch.setenv("BTB_NOTIFY_READ_TIMEOUT", "7")
    monkeypatch.setenv("BTB_NOTIFY_RETRIES", "5")
    monkeypatch.setenv("BTB_NOTIFY_BACKOFF", "1.25")

    config = NotifierConfig.from_env()
    assert config.notify_connect_timeout == 2.5
    assert isinstance(config.notify_connect_timeout, float)
    assert config.notify_read_timeout == 7.0
    assert config.notify_retries == 5
    assert isinstance(config.notify_retries, int)
    assert config.notify_backoff == 1.25
    assert _resolve_timeout(config) == (2.5, 7.0)


def test_env_invalid_value_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("BTB_NOTIFY_RETRIES", "not-a-number")
    config = NotifierConfig.from_env()
    # cast 失败时回退到字段默认值
    assert config.notify_retries == 3


# --- CLI 往返：to_cli_args 产出 flag，再从 runtime 解析回来 ---


def test_cli_args_roundtrip_overrides():
    config = NotifierConfig(
        notify_connect_timeout=3.0,
        notify_read_timeout=8.0,
        notify_retries=4,
        notify_backoff=0.75,
    )
    args = config.to_cli_args()
    assert "--notifier-config.notify-connect-timeout" in args
    assert args[args.index("--notifier-config.notify-connect-timeout") + 1] == "3.0"
    assert "--notifier-config.notify-read-timeout" in args
    assert "--notifier-config.notify-retries" in args
    assert args[args.index("--notifier-config.notify-retries") + 1] == "4"
    assert "--notifier-config.notify-backoff" in args


def test_runtime_mapping_overrides():
    parsed = NotifierConfig.from_mapping(
        {
            "notify_connect_timeout": "3.0",
            "notify_read_timeout": "8.0",
            "notify_retries": "4",
            "notify_backoff": "0.75",
        },
        source_name="runtime",
    )
    assert parsed.notify_connect_timeout == 3.0
    assert parsed.notify_read_timeout == 8.0
    assert parsed.notify_retries == 4
    assert parsed.notify_backoff == 0.75


# --- timeout tuple 正确传到 notifier 实例与 send_message ---


def test_create_from_config_passes_timeout_tuple():
    config = NotifierConfig(
        serverchan_key="tk",
        notify_connect_timeout=2.0,
        notify_read_timeout=6.0,
    )
    manager = NotifierManager.create_from_config(
        config=config,
        title="t",
        content="c",
        include_audio=False,
    )
    notifier = manager.notifier_dict["ServerChanTurbo"]
    assert notifier.timeout == (2.0, 6.0)


class _FakeResp:
    status_code = 200
    text = ""

    def raise_for_status(self):
        pass

    def json(self):
        return {"status": 200}


def test_send_message_uses_configured_timeout(monkeypatch):
    import util.notifer.ServerChanUtil as mod

    captured = {}

    def fake_post(url, *args, **kwargs):
        captured["timeout"] = kwargs.get("timeout")
        return _FakeResp()

    monkeypatch.setattr(mod.requests, "post", fake_post)

    notifier = ServerChanTurboNotifier(
        token="tk", title="t", content="c", timeout=(2.0, 6.0)
    )
    notifier.send_message("标题", "消息")
    assert captured["timeout"] == (2.0, 6.0)


def test_notifier_base_default_timeout_is_module_default():
    class _N(NotifierBase):
        def send_message(self, title, message):
            pass

    assert _N(title="t", content="c").timeout == DEFAULT_HTTP_TIMEOUT


# --- send_all_sync 使用配置的 retries/backoff ---


class _CountingNotifier(NotifierBase):
    def __init__(self, always_fail=False):
        super().__init__(title="t", content="c")
        self.calls = 0
        self._always_fail = always_fail

    def send_message(self, title, message):
        self.calls += 1
        if self._always_fail:
            raise requests.exceptions.ConnectTimeout("模拟超时")


def test_send_all_sync_honors_configured_retries():
    manager = NotifierManager()
    bad = _CountingNotifier(always_fail=True)
    manager.register_notifier("bad", bad)

    # backoff=0 避免测试变慢；retries=4 应导致 4 次调用
    results = manager.send_all_sync("t", "c", retries=4, backoff=0)
    assert results == {"bad": False}
    assert bad.calls == 4


def test_buy_resolves_notify_params_from_config():
    from task.buy import _resolve_notify_retry_params

    config = NotifierConfig(notify_retries=6, notify_backoff=1.5)
    retries, backoff = _resolve_notify_retry_params(config)
    assert retries == 6
    assert backoff == 1.5

    # 默认配置回退到第一轮参数
    retries, backoff = _resolve_notify_retry_params(NotifierConfig())
    assert retries == 3
    assert backoff == 0.5
