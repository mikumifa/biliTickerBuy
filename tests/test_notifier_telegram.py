"""Telegram 通知器的单元测试。

覆盖合并上游 Telegram 渠道后接入本次可靠性改造的部分：
- TelegramNotifier 默认使用 DEFAULT_HTTP_TIMEOUT
- 构造时传入的 timeout 被 send_message 的 requests.post 使用（不再硬编码 15）
- create_from_config 配了 telegram 时 manager 里存在 "Telegram"，且其 timeout 等于全局配置值
- ntfy + telegram 同时配置时两者都在 manager 且都会被 send_all_sync 遍历到
"""

import requests

from app_cmd.config.NotifierConfig import NotifierConfig
from util.notifer.Notifier import DEFAULT_HTTP_TIMEOUT, NotifierManager
from util.notifer.TelegramUtil import TelegramNotifier


class _FakeResp:
    def __init__(self, status_code=200):
        self.status_code = status_code
        self.text = ""

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"status={self.status_code}")


def _capture_post(monkeypatch, status_code=200):
    """替换 TelegramUtil 的 requests.post，捕获调用参数。"""
    import util.notifer.TelegramUtil as mod

    captured = {}

    def fake_post(url, *args, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return _FakeResp(status_code)

    monkeypatch.setattr(mod.requests, "post", fake_post)
    return captured


def test_telegram_default_timeout(monkeypatch):
    """不传 timeout 时使用 DEFAULT_HTTP_TIMEOUT，而非硬编码 15。"""
    cap = _capture_post(monkeypatch)
    TelegramNotifier(
        bot_token="123:ABC", chat_id="42", title="t", content="c"
    ).send_message("标题", "消息")
    assert cap["kwargs"].get("timeout") == DEFAULT_HTTP_TIMEOUT


def test_telegram_uses_configured_timeout(monkeypatch):
    """构造时传入的 timeout 应被 send_message 的 requests.post 使用。"""
    cap = _capture_post(monkeypatch)
    notifier = TelegramNotifier(
        bot_token="123:ABC",
        chat_id="42",
        title="t",
        content="c",
        timeout=(2.0, 4.0),
    )
    assert notifier.timeout == (2.0, 4.0)
    notifier.send_message("标题", "消息")
    assert cap["kwargs"].get("timeout") == (2.0, 4.0)


def test_telegram_http_proxy_passed(monkeypatch):
    """保留上游 http_proxy 逻辑：配置代理时传给 requests.post。"""
    cap = _capture_post(monkeypatch)
    TelegramNotifier(
        bot_token="123:ABC",
        chat_id="42",
        title="t",
        content="c",
        http_proxy="http://127.0.0.1:7890",
    ).send_message("标题", "消息")
    assert cap["kwargs"].get("proxies") == {
        "http": "http://127.0.0.1:7890",
        "https": "http://127.0.0.1:7890",
    }


def test_create_from_config_registers_telegram_with_global_timeout():
    """配了 telegram_bot_token + telegram_chat_id 时 manager 含 Telegram，
    且其 timeout == 全局配置的 (connect, read)。"""
    config = NotifierConfig(
        telegram_bot_token="123:ABC",
        telegram_chat_id="42",
        notify_connect_timeout=3.0,
        notify_read_timeout=7.0,
    )
    manager = NotifierManager.create_from_config(
        config=config, title="抢票提醒", content="测试", include_audio=False
    )
    assert "Telegram" in manager.notifier_dict
    assert manager.notifier_dict["Telegram"].timeout == (3.0, 7.0)


def test_ntfy_and_telegram_both_registered_and_covered_by_send_all_sync():
    """同时配 ntfy + telegram：两者都在 manager，且 send_all_sync 遍历到二者。"""
    config = NotifierConfig(
        ntfy_url="https://ntfy.sh/topic",
        telegram_bot_token="123:ABC",
        telegram_chat_id="42",
    )
    manager = NotifierManager.create_from_config(
        config=config, title="抢票提醒", content="测试", include_audio=False
    )
    assert "Ntfy" in manager.notifier_dict
    assert "Telegram" in manager.notifier_dict

    # 替换各渠道 send_message，记录被 send_all_sync 遍历/调用的渠道
    called = set()

    def _make_stub(name):
        def _stub(title, message):
            called.add(name)

        return _stub

    for name, notifier in manager.notifier_dict.items():
        notifier.send_message = _make_stub(name)

    results = manager.send_all_sync("标题", "内容", retries=1)
    assert set(results.keys()) == {"Ntfy", "Telegram"}
    assert results == {"Ntfy": True, "Telegram": True}
    assert called == {"Ntfy", "Telegram"}
