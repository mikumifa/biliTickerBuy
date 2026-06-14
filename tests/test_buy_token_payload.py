import json

import task.buy as buy_module
from task.buy import _build_token_payload
from task.buy import _build_order_token
from task.buy import buy_stream
from task.buy import _format_attempt_result
from task.buy import _format_retry_reason
from task.buy import _format_status_result
from util.TokenUtil import generate_token


def test_build_token_payload_uses_generate_token():
    tickets_info = {
        "count": 2,
        "screen_id": 456789,
        "order_type": 1,
        "project_id": 123456,
        "sku_id": 987654321,
    }

    payload = _build_token_payload(tickets_info)

    assert payload["token"] == generate_token(
        project_id=123456,
        screen_id=456789,
        order_type=1,
        count=2,
        sku_id=987654321,
    )
    assert payload["order_type"] == 1
    assert payload["newRisk"] is True


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
    }

    payload = _build_token_payload(tickets_info)

    assert payload["count"] == 2
    assert payload["screen_id"] == 456789
    assert payload["order_type"] == 1
    assert payload["project_id"] == 123456
    assert payload["sku_id"] == 987654321
    assert payload["token"] == generate_token(
        project_id=123456,
        screen_id=456789,
        order_type=1,
        count=2,
        sku_id=987654321,
    )


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


def test_non_hot_buy_stream_skips_prepare(monkeypatch):
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

    list(
        buy_stream(
            tickets_info=tickets_info,
            time_start="",
            interval=0,
            notifier_config=buy_module.NotifierConfig(),
            https_proxys="none",
            show_random_message=False,
            show_qrcode=False,
            readable=True,
        )
    )

    assert len(called_urls) == 1
    assert "order/createV2" in called_urls[0]


def test_hot_buy_stream_can_use_local_ptoken_without_prepare(monkeypatch):
    called_urls: list[str] = []
    generated_ctokens: list[bool] = []
    generated_ptokens: list[dict] = []

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
            assert data["ptoken"] == "LOCAL_PTOKEN"
            assert (
                data["orderCreateUrl"]
                == "https://show.bilibili.com/api/ticket/order/createV2"
            )
            assert "ctoken" in data
            return DummyResponse({"errno": 100079, "msg": "duplicate order"})

        def current_proxy_status(self):
            return "直连"

        def proxy_pool_status(self):
            return "直连"

    class DummyCTokenGenerator:
        def __init__(self, ticket_collection_t, time_offset, stay_time):
            self.ticket_collection_t = ticket_collection_t
            self.time_offset = time_offset
            self.stay_time = stay_time

        def generate_ctoken(self, for_create_stage: bool) -> str:
            generated_ctokens.append(for_create_stage)
            return "LOCAL_CREATE_CTOKEN"

    def fake_generate_inferred_ptoken_without_prepare(**kwargs):
        generated_ptokens.append(kwargs)
        return {
            "collection_second": 1781440220,
            "current_second": 1781441544,
            "prepare_ctoken": "LOCAL_PREPARE_CTOKEN",
            "ptoken": "LOCAL_PTOKEN",
            "ptoken_prefix_u8": [17, 1, 8, 1, 1, 99, 1, 4, 1, 1, 1, 1],
            "ptoken_u8": [17, 1, 8, 1, 1, 99, 1, 4, 1, 1, 1, 1, 4, 1, 5, 44],
        }

    monkeypatch.setattr(buy_module, "BiliRequest", DummyRequest)
    monkeypatch.setattr(buy_module, "_wait_until_start", lambda _time_start: [])
    monkeypatch.setattr(buy_module, "CTokenGenerator", DummyCTokenGenerator)
    monkeypatch.setattr(
        buy_module,
        "generate_inferred_ptoken_without_prepare",
        fake_generate_inferred_ptoken_without_prepare,
    )

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
            readable=True,
            use_local_ptoken=True,
        )
    )

    assert len(called_urls) == 1
    assert "order/createV2" in called_urls[0]
    assert "&ptoken=LOCAL_PTOKEN" in called_urls[0]
    assert generated_ctokens == [True]
    assert len(generated_ptokens) == 1
    assert any(
        event.message == "已启用本地 ptoken 模式，跳过 prepare"
        for event in events
        if getattr(event, "message", None) is not None
    )


def test_formatters_append_msg_for_selected_errno():
    ret = {"errno": 100003, "msg": "请重新完成验证码"}

    assert _format_status_result("订单准备结果", ret).endswith("msg: 请重新完成验证码")
    assert _format_attempt_result(1, 100003, ret).endswith("msg: 请重新完成验证码")
    assert _format_retry_reason(100003, ret, None).endswith("msg: 请重新完成验证码")


def test_formatters_keep_normal_errno_brief():
    ret = {"errno": 100041, "msg": "未开售"}

    assert (
        _format_status_result("订单准备结果", ret)
        == "订单准备结果: [100041] 未到开票时间"
    )
