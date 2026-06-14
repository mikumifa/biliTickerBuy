import json

import task.buy as buy_module
from task.buy import _build_token_payload
from task.buy import _build_order_token
from task.buy import buy_stream
from task.buy import _format_retry_reason
from task.buy import _format_status_result
from util.error_codes import ErrorCodes
from util.TokenUtil import generate_token


def test_build_token_payload_matches_bhyg_prepare_payload():
    tickets_info = {
        "count": 2,
        "screen_id": 456789,
        "order_type": 1,
        "project_id": 123456,
        "sku_id": 987654321,
        "buyer_info": "[]",
        "_prepare_buyer_info": [],
    }

    payload = _build_token_payload(tickets_info)

    assert payload["token"] == ""
    assert payload["order_type"] == 1
    assert payload["newRisk"] is True
    assert payload["requestSource"] == "neul-next"
    assert payload["ignoreRequestLimit"] is True
    assert payload["ticket_agent"] == ""
    assert payload["buyer_info"] == []


def test_generate_token_uses_new_binary_layout(monkeypatch):
    monkeypatch.setattr("util.TokenUtil.time.time", lambda: 1_700_000_000)

    token = generate_token(
        project_id=123456,
        screen_id=456789,
        order_type=1,
        count=2,
        sku_id=987654321,
    )

    assert token == "wGVT8QAAAeJAAAb4VQEAAjreaLE."


def test_build_token_payload_coerces_string_numbers():
    tickets_info = {
        "count": "2",
        "screen_id": "456789",
        "order_type": "1",
        "project_id": "123456",
        "sku_id": "987654321",
        "buyer_info": "[]",
        "_prepare_buyer_info": [],
    }

    payload = _build_token_payload(tickets_info)

    assert payload["count"] == 2
    assert payload["screen_id"] == 456789
    assert payload["order_type"] == 1
    assert payload["project_id"] == 123456
    assert payload["sku_id"] == 987654321
    assert payload["token"] == ""


def test_build_order_token_matches_generate_token():
    tickets_info = {
        "count": "2",
        "screen_id": "456789",
        "order_type": "1",
        "project_id": "123456",
        "sku_id": "987654321",
    }

    assert _build_order_token(tickets_info) == generate_token(
        project_id=123456,
        screen_id=456789,
        order_type=1,
        count=2,
        sku_id=987654321,
    )


def test_non_hot_buy_stream_uses_prepare(monkeypatch):
    called_urls: list[str] = []

    class DummyResponse:
        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    class DummyRequest:
        def __init__(self, cookies, proxy):
            self.cookies = cookies
            self.proxy = proxy

        def post(self, url, data, isJson=True):
            called_urls.append(url)
            if "order/prepare" in url:
                assert data["token"] == ""
                assert data["requestSource"] == "neul-next"
                return DummyResponse({"errno": 0, "data": {"token": "SERVER_TOKEN"}})
            assert data["token"] == "SERVER_TOKEN"
            return DummyResponse({"errno": 100079, "msg": "duplicate order"})

        def current_proxy_status(self):
            return "直连"

        def proxy_pool_status(self):
            return "直连"

    monkeypatch.setattr(buy_module, "BiliRequest", DummyRequest)
    monkeypatch.setattr(buy_module, "_wait_until_start", lambda _time_start: [])

    tickets_info = json.dumps(
        {
            "detail": "test",
            "cookies": [],
            "count": 2,
            "screen_id": 456789,
            "project_id": 123456,
            "sku_id": 987654321,
            "order_type": 1,
            "buyer_info": [],
            "deliver_info": {},
            "is_hot_project": False,
        }
    )

    list(
        buy_stream(
            tickets_info=tickets_info,
            time_start="",
            interval=0,
            notifier_config=buy_module.NotifierConfig(),
            https_proxys="none",
            show_random_message=False,
            show_qrcode=False,
        )
    )

    assert len(called_urls) == 2
    assert "order/prepare" in called_urls[0]
    assert "order/createV2" in called_urls[1]


def test_non_hot_buy_stream_can_use_local_token_without_prepare(monkeypatch):
    called_urls: list[str] = []

    class DummyResponse:
        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    class DummyRequest:
        def __init__(self, cookies, proxy):
            self.cookies = cookies
            self.proxy = proxy

        def post(self, url, data, isJson=True):
            called_urls.append(url)
            assert "order/prepare" not in url
            assert data["token"] == generate_token(
                project_id=123456,
                screen_id=456789,
                order_type=1,
                count=2,
                sku_id=987654321,
            )
            return DummyResponse({"errno": 100079, "msg": "duplicate order"})

        def current_proxy_status(self):
            return "直连"

        def proxy_pool_status(self):
            return "直连"

    monkeypatch.setattr(buy_module, "BiliRequest", DummyRequest)
    monkeypatch.setattr(buy_module, "_wait_until_start", lambda _time_start: [])

    tickets_info = json.dumps(
        {
            "detail": "test",
            "cookies": [],
            "count": 2,
            "screen_id": 456789,
            "project_id": 123456,
            "sku_id": 987654321,
            "order_type": 1,
            "buyer_info": [],
            "deliver_info": {},
            "is_hot_project": False,
        }
    )

    events = list(
        buy_stream(
            tickets_info=tickets_info,
            time_start="",
            interval=0,
            notifier_config=buy_module.NotifierConfig(),
            https_proxys="none",
            show_random_message=False,
            show_qrcode=False,
            use_local_token=True,
        )
    )

    assert len(called_urls) == 1
    assert "order/createV2" in called_urls[0]
    assert any(
        event.message == "已启用本地 token 模式，跳过 prepare"
        for event in events
        if getattr(event, "message", None) is not None
    )


def test_hot_buy_stream_ignores_local_ptoken_and_uses_prepare(monkeypatch):
    called_urls: list[str] = []

    class DummyResponse:
        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    class DummyRequest:
        def __init__(self, cookies, proxy):
            self.cookies = cookies
            self.proxy = proxy

        def post(self, url, data, isJson=True):
            called_urls.append(url)
            if "order/prepare" in url:
                assert data["token"] != ""
                return DummyResponse(
                    {
                        "errno": 0,
                        "data": {"token": "SERVER_TOKEN", "ptoken": "SERVER_PTOKEN=="},
                    }
                )
            assert data["token"] == "SERVER_TOKEN"
            assert data["ptoken"] == "SERVER_PTOKEN"
            assert "ctoken" in data
            return DummyResponse({"errno": 100079, "msg": "duplicate order"})

        def current_proxy_status(self):
            return "直连"

        def proxy_pool_status(self):
            return "直连"

    monkeypatch.setattr(buy_module, "BiliRequest", DummyRequest)
    monkeypatch.setattr(buy_module, "_wait_until_start", lambda _time_start: [])

    tickets_info = json.dumps(
        {
            "detail": "test",
            "cookies": [],
            "count": 2,
            "screen_id": 456789,
            "project_id": 123456,
            "sku_id": 987654321,
            "order_type": 1,
            "buyer_info": [],
            "deliver_info": {},
            "is_hot_project": True,
        }
    )

    events = list(
        buy_stream(
            tickets_info=tickets_info,
            time_start="",
            interval=0,
            notifier_config=buy_module.NotifierConfig(),
            https_proxys="none",
            show_random_message=False,
            show_qrcode=False,
            use_local_ptoken=True,
        )
    )

    assert len(called_urls) == 2
    assert "order/prepare" in called_urls[0]
    assert "order/createV2" in called_urls[1]
    assert "&ptoken=SERVER_PTOKEN" in called_urls[1]
    assert any(
        event.message == "本地 ptoken 已暂时禁用，回退到服务端 prepare"
        for event in events
        if getattr(event, "message", None) is not None
    )


def test_formatters_append_msg_for_selected_errno():
    ret = {"errno": 100003, "msg": "请重新完成验证码"}

    assert _format_status_result("订单准备结果", ret).endswith("msg: 请重新完成验证码")
    assert ErrorCodes.format_attempt_result(100003, ret).endswith(
        "msg: 请重新完成验证码"
    )
    assert _format_retry_reason(100003, ret, None).endswith("msg: 请重新完成验证码")


def test_formatters_keep_normal_errno_brief():
    ret = {"errno": 100041, "msg": "未开售"}

    assert (
        _format_status_result("订单准备结果", ret)
        == "订单准备结果: [100041] 未到开票时间"
    )
