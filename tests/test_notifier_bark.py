from unittest.mock import Mock
from urllib.parse import unquote_plus, urlsplit

import pytest
import requests

from app_cmd.config.NotifierConfig import NotifierConfig
from util.notifer.BarkUtil import BarkNotifier
from util.notifer.Notifier import DEFAULT_HTTP_TIMEOUT, NotifierManager


def bark_response(status: int = 200, *, location: str | None = None):
    response = requests.Response()
    response.status_code = status
    if location is not None:
        response.headers["Location"] = location
    return response


@pytest.mark.parametrize(
    ("token", "endpoint"),
    [
        ("device-key", "https://api.day.app/device-key"),
        (
            "https://api.day.app/device-key/标题/副标题/示例?level=critical&badge=1",
            "https://api.day.app/device-key?badge=1",
        ),
        (
            "https://bark.example.test/device-key/?Sound=bell&badge=1",
            "https://bark.example.test/device-key?badge=1",
        ),
    ],
)
def test_bark_uses_the_documented_json_endpoint(monkeypatch, token, endpoint):
    post = Mock(return_value=bark_response())
    monkeypatch.setattr(requests, "post", post)
    notifier = BarkNotifier(
        token, "标题", "正文", level="passive", notification_id="id"
    )

    notifier.send_message("标题", "正文")

    assert post.call_args.args == (endpoint,)
    payload = post.call_args.kwargs["json"]
    assert payload["title"] == "标题"
    assert payload["body"] == "正文"
    assert payload["level"] == "passive"
    assert payload["id"] == "id"
    assert "sound" not in payload
    assert "volume" not in payload


@pytest.mark.parametrize("path", ["/device-key/示例正文", "/prefix/device-key"])
def test_bark_legacy_path_keeps_the_current_body(monkeypatch, path):
    post = Mock(return_value=bark_response())
    monkeypatch.setattr(requests, "post", post)
    title = "抢票成功"
    message = "订单 + 优惠 & 详情 https://example.test/a/b?q=c#d"
    notifier = BarkNotifier(f"https://bark.example.test{path}", title, message)

    notifier.send_message(title, message)

    request_path = urlsplit(post.call_args.args[0]).path
    assert request_path.startswith(f"{path}/")
    sent_title, sent_body = request_path[len(path) + 1 :].split("/")
    assert unquote_plus(sent_title) == title
    assert unquote_plus(sent_body) == message


def test_bark_https_upgrade_keeps_json_and_critical_volume(monkeypatch):
    post = Mock(
        side_effect=[
            bark_response(
                301, location="https://bark.example.test/device-key?level=passive"
            ),
            bark_response(),
        ]
    )
    monkeypatch.setattr(requests, "post", post)
    config = NotifierConfig(
        bark_token="http://bark.example.test/device-key", bark_volume=0
    )
    manager = NotifierManager.create_from_config(
        config, "抢票成功", "请付款", bark_notification_id="order-id"
    )
    notifier = manager.notifier_dict["Bark"]

    notifier.send_message("抢票成功", "请付款")
    assert notifier.send_once_sync("抢票成功", "请付款", retries=1)

    http_call, https_call = post.call_args_list
    assert http_call.args == ("http://bark.example.test/device-key",)
    assert https_call.args == ("https://bark.example.test/device-key",)
    assert http_call.kwargs == https_call.kwargs
    assert https_call.kwargs["allow_redirects"] is False
    assert https_call.kwargs["timeout"] == DEFAULT_HTTP_TIMEOUT
    payload = https_call.kwargs["json"]
    assert payload["title"] == "抢票成功"
    assert payload["body"] == "请付款"
    assert payload["level"] == "critical"
    assert payload["id"] == "order-id"
    assert payload["volume"] == "0"


def test_bark_unhandled_redirect_allows_retry(monkeypatch):
    post = Mock(
        side_effect=[
            bark_response(302, location="https://other.example.test/device-key"),
            bark_response(),
        ]
    )
    monkeypatch.setattr(requests, "post", post)
    endpoint = "https://bark.example.test/device-key"
    notifier = BarkNotifier(endpoint, "标题", "正文", notification_id="id")

    assert notifier.send_once_sync("标题", "正文", retries=2, backoff=0)
    assert [call.args for call in post.call_args_list] == [(endpoint,), (endpoint,)]
    assert [call.kwargs["json"]["id"] for call in post.call_args_list] == ["id", "id"]
